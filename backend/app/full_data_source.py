from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from .background_data_source import BackgroundRefreshingDataSource
from .data_source import MarketDataError, _meta, ak, infer_market, safe_float


class FullMarketDataSource(BackgroundRefreshingDataSource):
    """在实时双数据源基础上，为日周月 K 线增加腾讯备用接口。"""

    def get_bars(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if timeframe.endswith("m"):
            return super().get_bars(code, timeframe, limit)

        cached_result: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
        primary_failure: MarketDataError | None = None
        # 东方财富偶尔会单次断连；先快速重试，再落到腾讯。基础类在失败时
        # 会返回 SQLite，因此必须显式检查 is_cached，不能把它当成主源成功。
        for _attempt in range(4):
            try:
                bars, meta = super().get_bars(code, timeframe, limit)
                if not meta.get("is_cached"):
                    return bars, meta
                if not cached_result or str(bars[-1]["time"]) > str(cached_result[0][-1]["time"]):
                    cached_result = (bars, meta)
                primary_failure = MarketDataError("东方财富失败，当前仅取得本地 K 线缓存")
            except MarketDataError as exc:
                primary_failure = exc

        if ak is None:
            if cached_result:
                return cached_result
            raise primary_failure or MarketDataError("K 线主数据源不可用")

        try:
            fetched_at = datetime.now()
            prefix = infer_market(code).lower()
            frame = ak.stock_zh_a_hist_tx(
                symbol=f"{prefix}{code}",
                start_date=(fetched_at - timedelta(days=3650)).strftime("%Y%m%d"),
                end_date=fetched_at.strftime("%Y%m%d"),
                adjust="qfq",
                timeout=25,
            )
            bars = self._normalize_tx_bars(frame, timeframe)
            if not bars:
                raise MarketDataError("腾讯证券没有返回可用 K 线")
            bars = bars[-max(1, min(limit, 2000)) :]
            if cached_result and str(bars[-1]["time"]) < str(cached_result[0][-1]["time"]):
                return cached_result
            self._persist_bars(code, timeframe, bars, fetched_at)
            return bars, _meta(
                fetched_at,
                cached=False,
                source="AKShare / 腾讯证券（K 线备用）",
                trade_date=str(bars[-1]["time"])[:10],
            )
        except Exception as fallback_error:
            if cached_result:
                return cached_result
            raise MarketDataError(
                f"K 线两个免费数据源均失败：{primary_failure}；腾讯证券：{fallback_error}"
            ) from fallback_error

    @staticmethod
    def _normalize_tx_bars(
        frame: pd.DataFrame | None,
        timeframe: str,
    ) -> list[dict[str, Any]]:
        if frame is None or frame.empty:
            return []
        required = {"date", "open", "close", "high", "low", "volume"}
        if not required.issubset(frame.columns):
            return []

        normalized = frame.copy()
        normalized["date"] = pd.to_datetime(normalized["date"])
        for column in ["open", "close", "high", "low", "volume", "amount"]:
            if column in normalized:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        normalized = normalized.dropna(subset=["open", "close", "high", "low", "volume"])

        if timeframe in {"week", "month"}:
            frequency = "W-FRI" if timeframe == "week" else "ME"
            normalized = (
                normalized.set_index("date")
                .resample(frequency)
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                        **({"amount": "sum"} if "amount" in normalized.columns else {}),
                    }
                )
                .dropna(subset=["open", "close", "high", "low"])
                .reset_index()
            )

        result: list[dict[str, Any]] = []
        for raw in normalized.to_dict(orient="records"):
            result.append(
                {
                    "time": pd.Timestamp(raw["date"]).strftime("%Y-%m-%d"),
                    "open": float(raw["open"]),
                    "high": float(raw["high"]),
                    "low": float(raw["low"]),
                    "close": float(raw["close"]),
                    "volume": float(raw["volume"]),
                    "amount": safe_float(raw.get("amount")),
                }
            )
        return result


data_source = FullMarketDataSource()
