from __future__ import annotations

from typing import Any

from .reliable_data_source import data_source


def get_intraday(code: str) -> dict[str, Any]:
    bars, meta = data_source.get_bars(code, "1m", 500)
    if not bars:
        return {"code": code, "date": None, "points": [], "meta": meta}
    latest_date = str(bars[-1]["time"])[:10]
    current = [item for item in bars if str(item["time"])[:10] == latest_date]
    cumulative_value = 0.0
    cumulative_volume = 0.0
    points: list[dict[str, Any]] = []
    for item in current:
        volume = float(item.get("volume") or 0)
        price = float(item["close"])
        amount = item.get("amount")
        if amount is not None and float(amount) > 0:
            cumulative_value += float(amount)
        else:
            typical = (
                float(item["high"]) + float(item["low"]) + float(item["close"])
            ) / 3
            cumulative_value += typical * volume
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
