from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from .config import settings
from .data_source import _meta
from .resilient_data_source import ResilientAkshareDataSource


class BackgroundRefreshingDataSource(ResilientAkshareDataSource):
    """已有缓存时立即响应，把较慢的全市场刷新放到后台线程。"""

    def __init__(self) -> None:
        super().__init__()
        self._refreshing = False
        self._refresh_state_lock = threading.Lock()

    def get_spot_quotes(
        self,
        *,
        force: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if force:
            return super().get_spot_quotes(force=True)

        if not self._spot_cache:
            cached, fetched_at = self._load_cached_quotes()
            if cached and fetched_at:
                self._spot_cache = cached
                self._spot_fetched_at = fetched_at
                self._last_provider = "database"
                self._start_background_refresh()
                return cached, _meta(
                    fetched_at,
                    cached=True,
                    source="本地 SQLite（后台正在刷新）",
                )

        if self._spot_cache and self._spot_fetched_at:
            now = datetime.now()
            ttl = settings.quote_cache_seconds if self._last_provider == "eastmoney" else 60
            age = (now - self._spot_fetched_at).total_seconds()
            if age >= ttl:
                self._start_background_refresh()
            return self._spot_cache, _meta(
                self._spot_fetched_at,
                cached=age > 0,
                source=self._cache_source_name()
                + ("；后台刷新中" if self._refreshing else ""),
            )

        return super().get_spot_quotes(force=False)

    def _start_background_refresh(self) -> None:
        with self._refresh_state_lock:
            if self._refreshing:
                return
            self._refreshing = True
        thread = threading.Thread(
            target=self._background_refresh,
            name="quote-background-refresh",
            daemon=True,
        )
        thread.start()

    def _background_refresh(self) -> None:
        try:
            super().get_spot_quotes(force=True)
        except Exception:
            # 请求端继续使用上一次有效缓存，具体失败会在手动刷新时明确返回。
            pass
        finally:
            with self._refresh_state_lock:
                self._refreshing = False


data_source = BackgroundRefreshingDataSource()
