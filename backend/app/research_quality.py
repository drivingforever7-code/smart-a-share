"""研究共用的数据时间、回撤与时间隔离规则。"""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from zoneinfo import ZoneInfo

LABEL_VERSION = 'verified_close_peak_v2'
SHANGHAI = ZoneInfo('Asia/Shanghai')


def verified_quote_date(meta: dict, *, close: bool = False, allow_post_close: bool = False) -> date | None:
    """只接受实际行情时间；拒绝日期替身、周末、未来和未收盘观察。"""
    value = str(meta.get('quote_time') or '').strip()
    if len(value) < 16:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        stamp = stamp.replace(tzinfo=SHANGHAI) if stamp.tzinfo is None else stamp.astimezone(SHANGHAI)
    except ValueError:
        return None
    if stamp.weekday() >= 5 or stamp > datetime.now(SHANGHAI):
        return None
    if meta.get('trade_date') and str(meta['trade_date'])[:10] != stamp.date().isoformat():
        return None
    # 行情时间必须落在交易时段；盘后抓取的时间不算行情时间。
    minutes = stamp.hour * 60 + stamp.minute
    if allow_post_close and minutes >= 900:
        return stamp.date()
    if close:
        if minutes != 15 * 60:
            return None
    elif not (570 <= minutes <= 690 or 780 <= minutes <= 900):
        return None
    return stamp.date()


def peak_drawdown(prices: list[float]) -> float:
    """计算离散价格路径的峰谷回撤，负数表示回撤。"""
    if not prices or any(not isfinite(p) or p <= 0 for p in prices):
        raise ValueError('回撤需要有效正价格')
    peak = prices[0]
    result = 0.0
    for price in prices:
        peak = max(peak, price)
        result = min(result, (price / peak - 1) * 100)
    return result


def purged_date_split(samples, label_end: dict[int, str], fraction: float = .75):
    """验证开始前尚未结束的训练标签剔除；同一天绝不拆成训练和验证。"""
    dates = sorted({s.sample_date for s in samples})
    if len(dates) < 2:
        return [], [], list(samples)
    boundary = dates[min(len(dates)-1, max(1, int(len(dates)*fraction)))]
    train = [s for s in samples if s.sample_date < boundary and label_end.get(s.id, '9999') < boundary]
    validation = [s for s in samples if s.sample_date >= boundary]
    kept = {s.id for s in train + validation}
    return train, validation, [s for s in samples if s.id not in kept]
