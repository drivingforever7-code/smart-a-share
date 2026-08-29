from __future__ import annotations

from datetime import datetime
from typing import Any

from .data_source import MarketDataError, _meta, ak, infer_market, safe_float
from .production_data_source import ProductionDataSource


class ReliableDataSource(ProductionDataSource):
    """在原行情链路上补充分时备用源。"""

    def get_bars(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if timeframe != "1m":
            return super().get_bars(code, timeframe, limit)

        cached_result: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
        primary_failure: MarketDataError | None = None
        for _attempt in range(4):
            try:
                bars, meta = super().get_bars(code, timeframe, limit)
                if not meta.get("is_cached"):
                    return bars, meta
                if not cached_result or str(bars[-1]["time"]) > str(cached_result[0][-1]["time"]):
                    cached_result = (bars, meta)
                primary_failure = MarketDataError("东方财富失败，当前仅取得本地分时缓存")
            except MarketDataError as exc:
                primary_failure = exc

        if ak is None:
            if cached_result:
                return cached_result
            raise primary_failure or MarketDataError("分时主数据源不可用")

        try:
            fetched_at = datetime.now()
            market = infer_market(code).lower()
            frame = ak.stock_zh_a_minute(
                symbol=f"{market}{code}",
                period="1",
                adjust="qfq",
            )
            bars: list[dict[str, Any]] = []
            if frame is not None:
                for raw in frame.to_dict(orient="records"):
                    open_price = safe_float(raw.get("open"))
                    close = safe_float(raw.get("close"))
                    high = safe_float(raw.get("high"))
                    low = safe_float(raw.get("low"))
                    volume = safe_float(raw.get("volume"))
                    if None in {open_price, close, high, low, volume}:
                        continue
                    bars.append(
                        {
                            "time": str(raw.get("day", "")),
                            "open": open_price,
                            "high": high,
                            "low": low,
                            "close": close,
                            "volume": volume,
                            "amount": safe_float(raw.get("amount")),
                        }
                    )
            if not bars:
                raise MarketDataError("备用分时源没有返回可用数据")
            bars = bars[-max(1, min(limit, 2000)) :]
            if cached_result and str(bars[-1]["time"]) < str(cached_result[0][-1]["time"]):
                return cached_result
            self._persist_bars(code, timeframe, bars, fetched_at)
            return bars, _meta(
                fetched_at,
                cached=False,
                source="AKShare / 新浪财经分时",
                quote_time=str(bars[-1]["time"]),
                trade_date=str(bars[-1]["time"])[:10],
            )
        except Exception as exc:
            if cached_result:
                return cached_result
            cached, fetched_at = self._load_cached_bars(code, timeframe, limit)
            if cached and fetched_at:
                return cached, _meta(
                    fetched_at,
                    cached=True,
                    source="本地 SQLite（分时源暂不可用）",
                    quote_time=str(cached[-1]["time"]),
                    trade_date=str(cached[-1]["time"])[:10],
                )
            raise MarketDataError(
                f"分时数据两个免费源均失败：{primary_failure}；新浪财经：{exc}"
            ) from exc


data_source = ReliableDataSource()
