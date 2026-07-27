from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from .data_source import MarketDataError, ak, safe_float
from .database import SessionLocal
from .research_models import MarketIndexBar


BENCHMARK_SYMBOL = "sh000300"


def enrich_market_regime(frame: pd.DataFrame) -> pd.DataFrame:
    benchmark = get_benchmark_history()
    result = frame.copy().sort_values("date")
    if benchmark.empty:
        result["market_close"] = float("nan")
        result["market_ma20"] = float("nan")
        result["market_ma60"] = float("nan")
        result["market_momentum20"] = float("nan")
        result["market_regime_up"] = False
        return result

    market = benchmark.copy()
    market["date"] = pd.to_datetime(market["date"])
    market["market_ma20"] = market["close"].rolling(20, min_periods=20).mean()
    market["market_ma60"] = market["close"].rolling(60, min_periods=60).mean()
    market["market_momentum20"] = market["close"].pct_change(20) * 100
    market["market_regime_up"] = (
        (market["close"] > market["market_ma60"])
        & (market["market_ma20"] > market["market_ma60"])
        & (market["market_momentum20"] > -2)
    )
    market = market.rename(columns={"close": "market_close"})
    return pd.merge_asof(
        result.sort_values("date"),
        market[
            [
                "date",
                "market_close",
                "market_ma20",
                "market_ma60",
                "market_momentum20",
                "market_regime_up",
            ]
        ].sort_values("date"),
        on="date",
        direction="backward",
    )


def get_benchmark_history(force: bool = False) -> pd.DataFrame:
    cached, fetched_at = _load_cached()
    is_fresh = fetched_at and datetime.now() - fetched_at < timedelta(hours=12)
    if not force and not cached.empty and is_fresh:
        return cached
    try:
        if ak is None:
            raise MarketDataError("AKShare 尚未安装")
        raw = ak.stock_zh_index_daily(symbol=BENCHMARK_SYMBOL)
        normalized = _normalize(raw)
        if normalized.empty:
            raise MarketDataError("沪深300历史接口没有返回可用数据")
        _persist(normalized)
        return normalized
    except Exception:
        if not cached.empty:
            return cached
        raise MarketDataError("无法取得沪深300历史数据，市场环境策略暂不可回测")


def market_regime_status() -> dict[str, object]:
    cached, fetched_at = _load_cached()
    latest = cached["date"].iloc[-1] if not cached.empty else None
    return {
        "symbol": BENCHMARK_SYMBOL,
        "records": len(cached),
        "latest_date": latest,
        "fetched_at": fetched_at.isoformat(timespec="seconds") if fetched_at else None,
    }


def _normalize(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    result = frame[list(required)].copy()
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    for column in ["open", "high", "low", "close", "volume"]:
        result[column] = result[column].map(safe_float)
    result = result.dropna().sort_values("date").drop_duplicates("date")
    return result.reset_index(drop=True)


def _persist(frame: pd.DataFrame) -> None:
    fetched_at = datetime.now()
    values = [
        {
            "symbol": BENCHMARK_SYMBOL,
            "date": row["date"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "fetched_at": fetched_at,
            "source": "AKShare / 新浪指数",
        }
        for row in frame.to_dict(orient="records")
    ]
    with SessionLocal.begin() as session:
        for start in range(0, len(values), 500):
            batch = values[start : start + 500]
            stmt = insert(MarketIndexBar).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[MarketIndexBar.symbol, MarketIndexBar.date],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in batch[0]
                    if key not in {"symbol", "date"}
                },
            )
            session.execute(stmt)


def _load_cached() -> tuple[pd.DataFrame, datetime | None]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(MarketIndexBar)
            .where(MarketIndexBar.symbol == BENCHMARK_SYMBOL)
            .order_by(MarketIndexBar.date.asc())
        ).all()
        fetched_at = session.scalar(
            select(func.max(MarketIndexBar.fetched_at)).where(
                MarketIndexBar.symbol == BENCHMARK_SYMBOL
            )
        )
    return (
        pd.DataFrame(
            [
                {
                    "date": row.date,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                for row in rows
            ]
        ),
        fetched_at,
    )
