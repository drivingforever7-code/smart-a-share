from __future__ import annotations

import math
import threading
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert

from .config import settings
from .database import Bar, Quote, SessionLocal, Stock

try:
    import akshare as ak
except ImportError:  # 安装依赖前仍允许服务启动并报告明确状态
    ak = None


class MarketDataError(RuntimeError):
    """免费行情源无法提供有效数据。"""


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or value == "-":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def infer_board(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "北交所"
    if code.startswith("68"):
        return "科创板"
    if code.startswith("30"):
        return "创业板"
    return "主板"


def infer_market(code: str) -> str:
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith(("6", "68")):
        return "SH"
    return "SZ"


def is_st_name(name: str) -> bool:
    upper = name.upper()
    return "ST" in upper or "退" in name


def _meta(
    fetched_at: datetime,
    *,
    cached: bool,
    source: str = "AKShare / 东方财富",
    quote_time: str | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    age = max(0, int((datetime.now() - fetched_at).total_seconds()))
    return {
        "source": source,
        "quote_time": quote_time,
        "trade_date": trade_date,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "is_cached": cached,
        "cache_age_seconds": age if cached else 0,
    }


class AkshareDataSource:
    """集中管理 AKShare 访问、缓存和数据库降级。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spot_cache: list[dict[str, Any]] = []
        self._spot_fetched_at: datetime | None = None

    @property
    def available(self) -> bool:
        return ak is not None

    def get_spot_quotes(
        self,
        *,
        force: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        now = datetime.now()
        if (
            not force
            and self._spot_cache
            and self._spot_fetched_at
            and (now - self._spot_fetched_at).total_seconds() < settings.quote_cache_seconds
        ):
            return self._spot_cache, _meta(
                self._spot_fetched_at,
                cached=True,
                source="AKShare / 东方财富（内存缓存）",
            )

        with self._lock:
            now = datetime.now()
            if (
                not force
                and self._spot_cache
                and self._spot_fetched_at
                and (now - self._spot_fetched_at).total_seconds()
                < settings.quote_cache_seconds
            ):
                return self._spot_cache, _meta(
                    self._spot_fetched_at,
                    cached=True,
                    source="AKShare / 东方财富（内存缓存）",
                )

            try:
                if ak is None:
                    raise MarketDataError("AKShare 尚未安装，请先安装后端依赖")
                frame = ak.stock_zh_a_spot_em()
                if frame is None or frame.empty:
                    raise MarketDataError("免费行情源返回了空数据")
                records = self._normalize_spot_frame(frame, now)
                if not records:
                    raise MarketDataError("行情数据格式异常，没有可用股票")
                self._persist_quotes(records, now)
                self._spot_cache = records
                self._spot_fetched_at = now
                return records, _meta(now, cached=False)
            except Exception as exc:
                cached, fetched_at = self._load_cached_quotes()
                if cached and fetched_at:
                    self._spot_cache = cached
                    self._spot_fetched_at = fetched_at
                    return cached, _meta(
                        fetched_at,
                        cached=True,
                        source="本地 SQLite（AKShare 获取失败）",
                    )
                if isinstance(exc, MarketDataError):
                    raise
                raise MarketDataError(f"实时行情获取失败：{exc}") from exc

    def get_bars(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if timeframe not in {"1m", "5m", "15m", "30m", "60m", "day", "week", "month"}:
            raise MarketDataError("不支持的 K 线周期")

        try:
            if ak is None:
                raise MarketDataError("AKShare 尚未安装，请先安装后端依赖")

            fetched_at = datetime.now()
            if timeframe.endswith("m"):
                period = timeframe.removesuffix("m")
                frame = ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    period=period,
                    adjust="qfq",
                )
            else:
                period_map = {"day": "daily", "week": "weekly", "month": "monthly"}
                start = (fetched_at - timedelta(days=3650)).strftime("%Y%m%d")
                frame = ak.stock_zh_a_hist(
                    symbol=code,
                    period=period_map[timeframe],
                    start_date=start,
                    end_date=fetched_at.strftime("%Y%m%d"),
                    adjust="qfq",
                )

            bars = self._normalize_bar_frame(frame, timeframe)
            if not bars:
                raise MarketDataError("数据源没有返回这个周期的 K 线")
            bars = bars[-max(1, min(limit, 2000)) :]
            self._persist_bars(code, timeframe, bars, fetched_at)
            return bars, _meta(
                fetched_at,
                cached=False,
                source="AKShare / 东方财富",
            )
        except Exception as exc:
            cached, fetched_at = self._load_cached_bars(code, timeframe, limit)
            if cached and fetched_at:
                return cached, _meta(
                    fetched_at,
                    cached=True,
                    source="本地 SQLite（AKShare 获取失败）",
                )
            if isinstance(exc, MarketDataError):
                raise
            raise MarketDataError(f"K 线获取失败：{exc}") from exc

    def cached_counts(self) -> dict[str, tuple[int, datetime | None]]:
        with SessionLocal() as session:
            quote_count = session.scalar(select(func.count()).select_from(Quote)) or 0
            quote_time = session.scalar(select(func.max(Quote.fetched_at)))
            bar_count = session.scalar(select(func.count()).select_from(Bar)) or 0
            bar_time = session.scalar(select(func.max(Bar.fetched_at)))
            stock_count = session.scalar(select(func.count()).select_from(Stock)) or 0
            stock_time = session.scalar(select(func.max(Stock.updated_at)))
        return {
            "stocks": (stock_count, stock_time),
            "quotes": (quote_count, quote_time),
            "bars": (bar_count, bar_time),
        }

    @staticmethod
    def _normalize_spot_frame(
        frame: pd.DataFrame,
        fetched_at: datetime,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for raw in frame.to_dict(orient="records"):
            code = str(raw.get("代码", "")).strip().zfill(6)
            name = str(raw.get("名称", "")).strip()
            if len(code) != 6 or not code.isdigit() or not name:
                continue
            result.append(
                {
                    "code": code,
                    "name": name,
                    "market": infer_market(code),
                    "board": infer_board(code),
                    "industry": None,
                    "is_st": is_st_name(name),
                    "status": "停牌" if safe_float(raw.get("最新价")) is None else "正常",
                    "price": safe_float(raw.get("最新价")),
                    "change": safe_float(raw.get("涨跌额")),
                    "change_pct": safe_float(raw.get("涨跌幅")),
                    "open": safe_float(raw.get("今开")),
                    "high": safe_float(raw.get("最高")),
                    "low": safe_float(raw.get("最低")),
                    "previous_close": safe_float(raw.get("昨收")),
                    "volume": safe_float(raw.get("成交量")),
                    "amount": safe_float(raw.get("成交额")),
                    "amplitude": safe_float(raw.get("振幅")),
                    "turnover_rate": safe_float(raw.get("换手率")),
                    "volume_ratio": safe_float(raw.get("量比")),
                    "speed": safe_float(raw.get("涨速")),
                    "change_5m": safe_float(raw.get("5分钟涨跌")),
                    "change_60d": safe_float(raw.get("60日涨跌幅")),
                    "change_ytd": safe_float(raw.get("年初至今涨跌幅")),
                    "pe": safe_float(raw.get("市盈率-动态")),
                    "pb": safe_float(raw.get("市净率")),
                    "total_market_cap": safe_float(raw.get("总市值")),
                    "circulating_market_cap": safe_float(raw.get("流通市值")),
                    "quote_time": None,
                    "fetched_at": fetched_at,
                    "source": "AKShare / 东方财富",
                }
            )
        return result

    @staticmethod
    def _normalize_bar_frame(frame: pd.DataFrame | None, timeframe: str) -> list[dict[str, Any]]:
        if frame is None or frame.empty:
            return []
        time_column = "时间" if "时间" in frame.columns else "日期"
        required = {time_column, "开盘", "收盘", "最高", "最低", "成交量"}
        if not required.issubset(set(frame.columns)):
            return []

        result: list[dict[str, Any]] = []
        for raw in frame.to_dict(orient="records"):
            open_price = safe_float(raw.get("开盘"))
            close = safe_float(raw.get("收盘"))
            high = safe_float(raw.get("最高"))
            low = safe_float(raw.get("最低"))
            volume = safe_float(raw.get("成交量"))
            if None in {open_price, close, high, low, volume}:
                continue
            time_value = raw.get(time_column)
            if hasattr(time_value, "isoformat"):
                time_text = time_value.isoformat()
            else:
                time_text = str(time_value)
            result.append(
                {
                    "time": time_text,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": safe_float(raw.get("成交额")),
                }
            )
        return result

    @staticmethod
    def _persist_quotes(records: list[dict[str, Any]], fetched_at: datetime) -> None:
        quote_columns = {
            column.name
            for column in Quote.__table__.columns
            if column.name != "code"
        }
        with SessionLocal.begin() as session:
            for record in records:
                stock_values = {
                    "code": record["code"],
                    "name": record["name"],
                    "market": record["market"],
                    "board": record["board"],
                    "industry": record["industry"],
                    "is_st": record["is_st"],
                    "status": record["status"],
                    "updated_at": fetched_at,
                }
                stock_stmt = insert(Stock).values(**stock_values)
                stock_stmt = stock_stmt.on_conflict_do_update(
                    index_elements=[Stock.code],
                    set_={key: value for key, value in stock_values.items() if key != "code"},
                )
                session.execute(stock_stmt)

                quote_values = {
                    key: value
                    for key, value in record.items()
                    if key == "code" or key in quote_columns
                }
                quote_stmt = insert(Quote).values(**quote_values)
                quote_stmt = quote_stmt.on_conflict_do_update(
                    index_elements=[Quote.code],
                    set_={key: value for key, value in quote_values.items() if key != "code"},
                )
                session.execute(quote_stmt)

    @staticmethod
    def _persist_bars(
        code: str,
        timeframe: str,
        bars: list[dict[str, Any]],
        fetched_at: datetime,
    ) -> None:
        with SessionLocal.begin() as session:
            # 分钟数据只保留当前接口返回范围，避免本地数据库无限增长。
            if timeframe.endswith("m"):
                session.execute(
                    delete(Bar).where(Bar.code == code, Bar.timeframe == timeframe)
                )
            for item in bars:
                values = {
                    "code": code,
                    "timeframe": timeframe,
                    **item,
                    "fetched_at": fetched_at,
                    "source": "AKShare / 东方财富",
                }
                stmt = insert(Bar).values(**values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_bar",
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in {"code", "timeframe", "time"}
                    },
                )
                session.execute(stmt)

    @staticmethod
    def _load_cached_quotes() -> tuple[list[dict[str, Any]], datetime | None]:
        with SessionLocal() as session:
            rows = session.execute(
                select(Quote, Stock).join(Stock, Stock.code == Quote.code)
            ).all()
            fetched_at = session.scalar(select(func.max(Quote.fetched_at)))
            records = []
            for quote, stock in rows:
                records.append(
                    {
                        "code": quote.code,
                        "name": quote.name or stock.name,
                        "market": stock.market,
                        "board": stock.board,
                        "industry": stock.industry,
                        "is_st": stock.is_st,
                        "status": stock.status,
                        **{
                            key: getattr(quote, key)
                            for key in (
                                "price",
                                "change",
                                "change_pct",
                                "open",
                                "high",
                                "low",
                                "previous_close",
                                "volume",
                                "amount",
                                "amplitude",
                                "turnover_rate",
                                "volume_ratio",
                                "speed",
                                "change_5m",
                                "change_60d",
                                "change_ytd",
                                "pe",
                                "pb",
                                "total_market_cap",
                                "circulating_market_cap",
                                "quote_time",
                                "fetched_at",
                                "source",
                            )
                        },
                    }
                )
        return records, fetched_at

    @staticmethod
    def _load_cached_bars(
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        with SessionLocal() as session:
            rows = (
                session.scalars(
                    select(Bar)
                    .where(Bar.code == code, Bar.timeframe == timeframe)
                    .order_by(Bar.time.desc())
                    .limit(limit)
                )
                .all()
            )
            rows.reverse()
            fetched_at = max((row.fetched_at for row in rows), default=None)
            records = [
                {
                    "time": row.time,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "amount": row.amount,
                }
                for row in rows
            ]
        return records, fetched_at


data_source = AkshareDataSource()
