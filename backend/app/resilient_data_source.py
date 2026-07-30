from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any

import pandas as pd

from .config import settings
from .data_source import MarketDataError, _meta, ak, infer_board, infer_market, is_st_name, safe_float
from .optimized_data_source import OptimizedAkshareDataSource


class ResilientAkshareDataSource(OptimizedAkshareDataSource):
    """东方财富优先、腾讯备用，并对慢速备用源延长缓存。"""

    def __init__(self) -> None:
        super().__init__()
        self._last_provider = "eastmoney"
        self._spot_trade_date: str | None = None
        self._calendar_checked_on: str | None = None
        self._calendar_trade_date: str | None = None

    def get_spot_quotes(
        self,
        *,
        force: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        now = datetime.now()
        ttl = settings.quote_cache_seconds if self._last_provider == "eastmoney" else 60
        if (
            not force
            and self._spot_cache
            and self._spot_fetched_at
            and (now - self._spot_fetched_at).total_seconds() < ttl
        ):
            return self._spot_cache, _meta(
                self._spot_fetched_at,
                cached=True,
                source=self._cache_source_name(),
                trade_date=self._spot_trade_date,
            )

        with self._lock:
            now = datetime.now()
            ttl = settings.quote_cache_seconds if self._last_provider == "eastmoney" else 60
            if (
                not force
                and self._spot_cache
                and self._spot_fetched_at
                and (now - self._spot_fetched_at).total_seconds() < ttl
            ):
                return self._spot_cache, _meta(
                    self._spot_fetched_at,
                    cached=True,
                    source=self._cache_source_name(),
                    trade_date=self._spot_trade_date,
                )

            errors: list[str] = []
            if ak is None:
                raise MarketDataError("AKShare 尚未安装，请先安装后端依赖")

            try:
                frame = ak.stock_zh_a_spot_em()
                records = self._normalize_spot_frame(frame, now)
                if not records:
                    raise MarketDataError("东方财富返回空数据")
                trade_date = self._resolve_trade_date(now)
                self._save_success(records, now, "eastmoney", trade_date)
                return records, _meta(
                    now,
                    cached=False,
                    source="AKShare / 东方财富",
                    trade_date=trade_date,
                )
            except Exception as exc:
                errors.append(f"东方财富：{exc}")

            try:
                frame = ak.stock_zh_a_spot_tx()
                records = self._normalize_tx_frame(frame, now)
                if not records:
                    raise MarketDataError("腾讯行情返回空数据")
                trade_date = self._resolve_trade_date(now)
                self._save_success(records, now, "tencent", trade_date)
                return records, _meta(
                    now,
                    cached=False,
                    source="AKShare / 腾讯证券（备用）",
                    trade_date=trade_date,
                )
            except Exception as exc:
                errors.append(f"腾讯证券：{exc}")

            cached, fetched_at = self._load_cached_quotes()
            if cached and fetched_at:
                self._spot_cache = cached
                self._spot_fetched_at = fetched_at
                self._last_provider = "database"
                cache_age = max(0, (now - fetched_at).total_seconds())
                verified_date = self._resolve_trade_date(fetched_at)
                self._spot_trade_date = (
                    verified_date
                    if verified_date == fetched_at.date().isoformat() and cache_age <= 1800
                    else None
                )
                return cached, _meta(
                    fetched_at,
                    cached=True,
                    source="本地 SQLite（两个免费行情源均失败）",
                    trade_date=self._spot_trade_date,
                )
            raise MarketDataError("实时行情获取失败；" + "；".join(errors))

    def _save_success(
        self,
        records: list[dict[str, Any]],
        fetched_at: datetime,
        provider: str,
        trade_date: str | None,
    ) -> None:
        self._persist_quotes(records, fetched_at)
        self._spot_cache = records
        self._spot_fetched_at = fetched_at
        self._last_provider = provider
        self._spot_trade_date = trade_date

    def _resolve_trade_date(self, fetched_at: datetime) -> str | None:
        """用独立交易日历确认快照所属交易日；校验失败就不允许入榜。"""
        checked_on = fetched_at.date().isoformat()
        if self._calendar_checked_on == checked_on:
            return self._calendar_trade_date
        self._calendar_checked_on = checked_on
        self._calendar_trade_date = None
        try:
            frame = ak.tool_trade_date_hist_sina()
            if frame is None or frame.empty:
                return None
            column = "trade_date" if "trade_date" in frame.columns else frame.columns[0]
            dates = pd.to_datetime(frame[column], errors="coerce").dropna().dt.date
            candidates = [value for value in dates if value <= fetched_at.date()]
            if not candidates:
                return None
            latest = max(candidates)
            if latest == fetched_at.date() and fetched_at.time() < time(9, 30):
                earlier = [value for value in candidates if value < latest]
                if earlier:
                    latest = max(earlier)
            self._calendar_trade_date = latest.isoformat()
        except Exception:
            self._calendar_trade_date = None
        return self._calendar_trade_date

    def _cache_source_name(self) -> str:
        if self._last_provider == "tencent":
            return "AKShare / 腾讯证券（60 秒缓存）"
        if self._last_provider == "database":
            return "本地 SQLite 缓存"
        return "AKShare / 东方财富（内存缓存）"

    @staticmethod
    def _normalize_tx_frame(
        frame: pd.DataFrame | None,
        fetched_at: datetime,
    ) -> list[dict[str, Any]]:
        if frame is None or frame.empty:
            return []
        result: list[dict[str, Any]] = []
        for raw in frame.to_dict(orient="records"):
            raw_code = str(raw.get("code", "")).strip().lower()
            code = raw_code[-6:]
            name = str(raw.get("name", "")).strip()
            if len(code) != 6 or not code.isdigit() or not name:
                continue
            price = safe_float(raw.get("zxj"))
            amount_wan = safe_float(raw.get("turnover"))
            volume_hand = safe_float(raw.get("volume"))
            total_cap_yi = safe_float(raw.get("zsz"))
            float_cap_yi = safe_float(raw.get("ltsz"))
            result.append(
                {
                    "code": code,
                    "name": name,
                    "market": infer_market(code),
                    "board": infer_board(code),
                    "industry": None,
                    "is_st": is_st_name(name),
                    "status": "停牌" if price is None or price <= 0 else "正常",
                    "price": price,
                    "change": safe_float(raw.get("zd")),
                    "change_pct": safe_float(raw.get("zdf")),
                    "open": None,
                    "high": None,
                    "low": None,
                    "previous_close": (
                        price / (1 + safe_float(raw.get("zdf")) / 100)
                        if price and safe_float(raw.get("zdf")) not in {None, -100}
                        else None
                    ),
                    "volume": volume_hand * 100 if volume_hand is not None else None,
                    "amount": amount_wan * 10_000 if amount_wan is not None else None,
                    "amplitude": safe_float(raw.get("zf")),
                    "turnover_rate": safe_float(raw.get("hsl")),
                    "volume_ratio": safe_float(raw.get("lb")),
                    "speed": safe_float(raw.get("speed")),
                    "change_5m": None,
                    "change_60d": safe_float(raw.get("zdf_d60")),
                    "change_ytd": safe_float(raw.get("zdf_y")),
                    "pe": safe_float(raw.get("pe_ttm")),
                    "pb": safe_float(raw.get("pn")),
                    "total_market_cap": total_cap_yi * 1e8 if total_cap_yi is not None else None,
                    "circulating_market_cap": float_cap_yi * 1e8 if float_cap_yi is not None else None,
                    "quote_time": None,
                    "fetched_at": fetched_at,
                    "source": "AKShare / 腾讯证券",
                }
            )
        return result


data_source = ResilientAkshareDataSource()
