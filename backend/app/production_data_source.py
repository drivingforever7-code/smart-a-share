from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .data_source import MarketDataError, _meta, ak, infer_market
from .full_data_source import FullMarketDataSource


class ProductionDataSource(FullMarketDataSource):
    """根据调用需要补齐历史缓存，避免详情的短缓存限制回测范围。"""

    def get_bars(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        bars, meta = super().get_bars(code, timeframe, limit)
        if timeframe.endswith("m") or not meta.get("is_cached"):
            return bars, meta

        expected_cap = {"day": 2000, "week": 520, "month": 120}.get(timeframe, limit)
        expected = min(limit, expected_cap)
        if len(bars) >= expected * 0.9:
            return bars, meta

        try:
            return self._fetch_complete_tx_history(code, timeframe, limit)
        except Exception:
            # 补齐失败时继续返回已有缓存，并如实保留缓存标记。
            return bars, meta

    def _fetch_complete_tx_history(
        self,
        code: str,
        timeframe: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if ak is None:
            raise MarketDataError("AKShare 尚未安装")
        fetched_at = datetime.now()
        prefix = infer_market(code).lower()
        frame = ak.stock_zh_a_hist_tx(
            symbol=f"{prefix}{code}",
            start_date=(fetched_at - timedelta(days=3650)).strftime("%Y%m%d"),
            end_date=fetched_at.strftime("%Y%m%d"),
            adjust="qfq",
            timeout=25,
        )
        all_bars = self._normalize_tx_bars(frame, timeframe)
        if not all_bars:
            raise MarketDataError("腾讯证券没有返回可用 K 线")
        self._persist_bars(code, timeframe, all_bars, fetched_at)
        return all_bars[-max(1, min(limit, 2000)) :], _meta(
            fetched_at,
            cached=False,
            source="AKShare / 腾讯证券（补齐历史）",
        )


data_source = ProductionDataSource()
