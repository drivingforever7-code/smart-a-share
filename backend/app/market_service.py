from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from statistics import median
from typing import Any

from pypinyin import Style, lazy_pinyin

from .config import DATA_DIR
from .data_source import MarketDataError
from .reliable_data_source import data_source
from .schemas import ScreenerRequest
from .scoring import PRESETS, analyze, matches_preset, number
from .ranking_optimizer_service import apply_active_version


@lru_cache(maxsize=10000)
def _stock_search_terms(name: str) -> tuple[str, str]:
    """缓存股票名称的完整拼音与首字母，避免每次搜索重复转换。"""
    full = "".join(lazy_pinyin(name, style=Style.NORMAL)).lower()
    initials = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower()
    return full, initials


class MarketService:
    def __init__(self) -> None:
        self._analysis_cache_key: str | None = None
        self._short_cache: list[dict[str, Any]] = []
        self._swing_cache: list[dict[str, Any]] = []

    def overview(self) -> dict[str, Any]:
        quotes, meta = data_source.get_spot_quotes()
        changes = [
            number(item.get("change_pct"))
            for item in quotes
            if item.get("change_pct") is not None
        ]
        rising = sum(value > 0 for value in changes)
        falling = sum(value < 0 for value in changes)
        flat = len(changes) - rising - falling
        return {
            "quote_count": len(quotes),
            "rising": rising,
            "falling": falling,
            "flat": flat,
            "limit_up": sum(value >= 9.7 for value in changes),
            "limit_down": sum(value <= -9.7 for value in changes),
            "average_change_pct": round(sum(changes) / len(changes), 2) if changes else 0,
            "median_change_pct": round(median(changes), 2) if changes else 0,
            "meta": meta,
        }

    def opportunities(
        self,
        mode: str,
        *,
        limit: int,
        preset: str | None = None,
        include_st: bool = False,
    ) -> list[dict[str, Any]]:
        items, _ = self._analyzed_market(mode)
        filtered = [
            item
            for item in items
            if (include_st or not item.get("_is_st"))
            and item.get("_status") == "正常"
            and matches_preset(item, preset)
        ]
        filtered = apply_active_version(mode, filtered)
        filtered.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
        return [self._public(item) for item in filtered[: max(1, min(limit, 500))]]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        query = query.strip().lower().replace(" ", "")
        if not query:
            return []
        items, _ = self._analyzed_market("short")
        ranked: list[tuple[int, dict[str, Any]]] = []
        for item in items:
            code = item["code"]
            name = item["name"].lower()
            full_pinyin, initials = _stock_search_terms(name)
            terms = (code, name, full_pinyin, initials)
            if query in terms:
                rank = 0
            elif any(term.startswith(query) for term in terms):
                rank = 1
            elif any(query in term for term in terms):
                rank = 2
            else:
                continue
            ranked.append((rank, item))
        ranked.sort(key=lambda pair: (pair[0], pair[1]["code"]))
        return [self._public(item) for _, item in ranked[:limit]]

    def stock_analysis(self, code: str, mode: str) -> dict[str, Any]:
        quotes, meta = data_source.get_spot_quotes()
        quote = next((item for item in quotes if item["code"] == code), None)
        if quote is None:
            raise MarketDataError(f"没有找到股票代码 {code}")
        bar_warning: str | None = None
        try:
            bars, _ = data_source.get_bars(code, "day", 300)
        except MarketDataError as exc:
            bars = []
            bar_warning = str(exc)
        result = analyze(quote, mode, meta=meta, bars=bars)
        if bar_warning:
            result["risks"] = list(
                dict.fromkeys([*result["risks"], "日 K 数据暂未补齐，评分主要依据实时快照"])
            )[:3]
            result["confidence"] = min(result["confidence"], 68)
            if result["recommendation"] == "建议买入":
                result["recommendation"] = "建议小仓位试买"
        return self._public(apply_active_version(mode, [result])[0])

    def screen(self, filters: ScreenerRequest) -> dict[str, Any]:
        items, meta = self._analyzed_market(filters.mode)
        items = apply_active_version(filters.mode, items)
        result = []
        for item in items:
            if not filters.include_st and item.get("_is_st"):
                continue
            if item.get("_status") != "正常":
                continue
            if filters.boards and item.get("board") not in filters.boards:
                continue
            if filters.industries and item.get("industry") not in filters.industries:
                continue
            if filters.preset and not matches_preset(item, filters.preset):
                continue
            if not self._within(item.get("score"), filters.min_score, None):
                continue
            if not self._within(item.get("change_pct"), filters.min_change_pct, filters.max_change_pct):
                continue
            if not self._within(item.get("turnover_rate"), filters.min_turnover_rate, None):
                continue
            if not self._within(item.get("volume_ratio"), filters.min_volume_ratio, None):
                continue
            if not self._within(item.get("pe"), filters.min_pe, filters.max_pe):
                continue
            if not self._within(item.get("pb"), filters.min_pb, filters.max_pb):
                continue
            if not self._within(
                item.get("total_market_cap"),
                filters.min_market_cap,
                filters.max_market_cap,
            ):
                continue
            result.append(item)

        reverse = filters.sort_order == "desc"
        allowed_sort = {
            "score",
            "change_pct",
            "turnover_rate",
            "volume_ratio",
            "pe",
            "pb",
            "total_market_cap",
        }
        sort_key = filters.sort_by if filters.sort_by in allowed_sort else "score"
        result.sort(
            key=lambda item: (
                item.get(sort_key) is not None,
                number(item.get(sort_key), -1e30),
            ),
            reverse=reverse,
        )
        total = len(result)
        start = (filters.page - 1) * filters.page_size
        page_items = result[start : start + filters.page_size]
        industries = sorted(
            {
                str(item["industry"])
                for item in items
                if item.get("industry")
            }
        )
        return {
            "total": total,
            "page": filters.page,
            "page_size": filters.page_size,
            "items": [self._public(item) for item in page_items],
            "industries": industries,
            "meta": meta,
        }

    def refresh_quotes(self) -> dict[str, Any]:
        quotes, meta = data_source.get_spot_quotes(force=True)
        self._analysis_cache_key = None
        return {
            "message": "实时行情更新完成",
            "count": len(quotes),
            "fetched_at": meta["fetched_at"],
        }

    def data_status(self) -> dict[str, Any]:
        counts = data_source.cached_counts()
        now = datetime.now()

        def status_item(
            key: str,
            name: str,
            description: str,
            stale_after_hours: int,
        ) -> dict[str, Any]:
            count, updated = counts[key]
            if count == 0:
                state = "empty"
            elif updated and (now - updated).total_seconds() > stale_after_hours * 3600:
                state = "stale"
            else:
                state = "ready"
            return {
                "key": key,
                "name": name,
                "status": state,
                "records": count,
                "updated_at": updated.isoformat(timespec="seconds") if updated else None,
                "description": description,
            }

        return {
            "service": "智选 A 股本地数据服务",
            "database_path": str(DATA_DIR / "smart_a_share.db"),
            "akshare_available": data_source.available,
            "items": [
                status_item("stocks", "股票基础信息", "代码、名称、市场和交易状态", 24),
                status_item("quotes", "实时行情缓存", "最新价格、涨跌幅、量比和换手率", 1),
                status_item("bars", "K 线缓存", "访问股票详情或回测后逐步积累", 48),
            ],
        }

    def _analyzed_market(
        self,
        mode: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        quotes, meta = data_source.get_spot_quotes()
        cache_key = meta["fetched_at"]
        if cache_key != self._analysis_cache_key:
            self._short_cache = [
                self._decorate(analyze(quote, "short", meta=meta), quote)
                for quote in quotes
            ]
            self._swing_cache = [
                self._decorate(analyze(quote, "swing", meta=meta), quote)
                for quote in quotes
            ]
            self._analysis_cache_key = cache_key
        return (self._short_cache if mode == "short" else self._swing_cache), meta

    @staticmethod
    def _decorate(result: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        result["_is_st"] = quote.get("is_st", False)
        result["_status"] = quote.get("status", "正常")
        return result

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if not key.startswith("_")}

    @staticmethod
    def _within(value: Any, minimum: float | None, maximum: float | None) -> bool:
        if minimum is None and maximum is None:
            return True
        if value is None:
            return False
        current = number(value)
        if minimum is not None and current < minimum:
            return False
        if maximum is not None and current > maximum:
            return False
        return True


market_service = MarketService()


def presets() -> list[dict[str, str]]:
    return PRESETS
