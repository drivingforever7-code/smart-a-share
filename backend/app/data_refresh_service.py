from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable

from .auto_backtest_service import auto_backtest
from .board_pool_service import board_pool_research
from .limit_break_service import limit_break_research
from .reliable_data_source import data_source


_REFRESH_COOLDOWN = timedelta(seconds=60)
_refresh_lock = Lock()
_last_completed_at: datetime | None = None
_last_result: dict[str, Any] | None = None


def _component(
    result: dict[str, Any],
    name: str,
    operation: Callable[[], dict[str, Any]],
) -> None:
    try:
        result["components"][name] = {"ok": True, **operation()}
    except Exception as exc:
        result["components"][name] = {"ok": False, "error": str(exc)}
        result["warnings"].append(f"{name}: {exc}")


def refresh_all_data() -> dict[str, Any]:
    """统一刷新相关数据；并发请求串行化，冷却期内直接复用结果。"""
    global _last_completed_at, _last_result

    with _refresh_lock:
        now = datetime.now().astimezone()
        if (
            _last_completed_at is not None
            and _last_result is not None
            and now - _last_completed_at < _REFRESH_COOLDOWN
        ):
            return {**_last_result, "cached": True, "checked_at": now.isoformat()}

        result: dict[str, Any] = {
            "cached": False,
            "started_at": now.isoformat(),
            "components": {},
            "warnings": [],
        }

        def quotes() -> dict[str, Any]:
            rows, meta = data_source.get_spot_quotes()
            return {"count": len(rows), "meta": meta}

        def limit_breaks() -> dict[str, Any]:
            data = limit_break_research(10, True)
            return {
                "display_date": data.get("display_date"),
                "count": len(data.get("items", [])),
                "capture": data.get("capture"),
                "warning": data.get("warning"),
            }

        def board_pools() -> dict[str, Any]:
            data = board_pool_research(10, True)
            return {
                "display_date": (data.get("available_dates") or [None])[0],
                "count": len(data.get("items", [])),
                "capture": data.get("capture"),
                "warning": data.get("warning"),
            }

        def rankings() -> dict[str, Any]:
            data = auto_backtest(10)
            return {
                "available_dates": data.get("available_dates", []),
                "count": len(data.get("items", [])),
            }

        _component(result, "quotes", quotes)
        _component(result, "limit_breaks", limit_breaks)
        _component(result, "board_pools", board_pools)
        _component(result, "auto_backtest", rankings)

        completed_at = datetime.now().astimezone()
        result["completed_at"] = completed_at.isoformat()
        _last_completed_at = completed_at
        _last_result = result
        return result
