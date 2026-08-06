from __future__ import annotations

from datetime import date, datetime, timedelta
from threading import Lock

import akshare as ak


_calendar_lock = Lock()
_calendar_loaded_on: date | None = None
_calendar_dates: list[date] = []


def latest_available_trade_date(moment: datetime) -> str:
    """返回当前时点已经开始交易的最近交易日，盘前不会冒充当天。"""
    global _calendar_loaded_on, _calendar_dates

    cutoff = moment.date()
    if moment.hour * 60 + moment.minute < 9 * 60 + 25:
        cutoff -= timedelta(days=1)

    with _calendar_lock:
        if _calendar_loaded_on != moment.date() or not _calendar_dates:
            frame = ak.tool_trade_date_hist_sina()
            if frame is None or frame.empty:
                raise RuntimeError("交易日历暂时不可用")
            parsed: list[date] = []
            for value in frame.iloc[:, 0]:
                try:
                    parsed.append(datetime.fromisoformat(str(value)[:10]).date())
                except ValueError:
                    continue
            if not parsed:
                raise RuntimeError("交易日历没有可用日期")
            _calendar_dates = sorted(set(parsed))
            _calendar_loaded_on = moment.date()

        eligible = [value for value in _calendar_dates if value <= cutoff]
        if not eligible:
            raise RuntimeError("找不到当前时点之前的有效交易日")
        return eligible[-1].isoformat()
