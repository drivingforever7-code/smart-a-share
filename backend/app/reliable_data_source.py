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
        try:
            return super().get_bars(code, timeframe, limit)
        except MarketDataError as primary_error:
            if timeframe != "1m" or ak is None:
                raise primary_error
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
                self._persist_bars(code, timeframe, bars, fetched_at)
                return bars, _meta(
                    fetched_at,
                    cached=False,
                    source="AKShare / 新浪财经分时",
                )
            except Exception as exc:
                cached, fetched_at = self._load_cached_bars(code, timeframe, limit)
                if cached and fetched_at:
                    return cached, _meta(
                        fetched_at,
                        cached=True,
                        source="本地 SQLite（分时源暂不可用）",
                    )
                raise MarketDataError(f"分时数据获取失败：{exc}") from exc


data_source = ReliableDataSource()
