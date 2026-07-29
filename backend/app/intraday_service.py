from __future__ import annotations

from typing import Any

from .reliable_data_source import data_source


def _normalized_turnover(
    amount: Any,
    volume: float,
    reference_price: float,
    typical_price: float,
) -> float:
    """把不同数据源的成交额统一成“价格 × 当前成交量单位”后再累计。"""
    if volume <= 0:
        return 0.0
    try:
        raw_amount = float(amount)
    except (TypeError, ValueError):
        return typical_price * volume
    if raw_amount <= 0:
        return typical_price * volume

    implied_price = raw_amount / volume
    ratio = implied_price / reference_price if reference_price > 0 else 0
    if 50 <= ratio <= 150:
        # 东方财富分钟成交量以“手”返回，而成交额以“元”返回。
        return raw_amount / 100
    if 0.5 <= ratio <= 1.5:
        return raw_amount
    # 单位关系异常时不用错误成交额污染整日均价。
    return typical_price * volume


def get_intraday(code: str) -> dict[str, Any]:
    bars, meta = data_source.get_bars(code, "1m", 500)
    if not bars:
        return {"code": code, "date": None, "points": [], "meta": meta}

    latest_date = max(str(item["time"])[:10] for item in bars)
    current_by_time = {
        str(item["time"]): item
        for item in bars
        if str(item["time"])[:10] == latest_date
    }
    current = [current_by_time[key] for key in sorted(current_by_time)]
    cumulative_value = 0.0
    cumulative_volume = 0.0
    points: list[dict[str, Any]] = []
    for item in current:
        volume = float(item.get("volume") or 0)
        price = float(item["close"])
        typical = (
            float(item["high"]) + float(item["low"]) + float(item["close"])
        ) / 3
        cumulative_value += _normalized_turnover(
            item.get("amount"),
            volume,
            price,
            typical,
        )
        cumulative_volume += volume
        average_price = (
            cumulative_value / cumulative_volume if cumulative_volume > 0 else price
        )
        points.append(
            {
                "time": str(item["time"]),
                "price": round(price, 4),
                "average_price": round(average_price, 4),
                "volume": volume,
            }
        )
    return {"code": code, "date": latest_date, "points": points, "meta": meta}
