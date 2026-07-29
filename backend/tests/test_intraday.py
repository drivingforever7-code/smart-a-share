from __future__ import annotations

import pytest

from app import intraday_service
from app.intraday_service import _normalized_turnover


def test_turnover_normalizes_eastmoney_hand_and_yuan_units():
    assert _normalized_turnover(111_000, 100, 11.1, 11.1) == 1110


def test_turnover_preserves_share_based_source_units():
    assert _normalized_turnover(111_000, 10_000, 11.1, 11.1) == 111_000


def test_abnormal_amount_falls_back_to_typical_price():
    assert _normalized_turnover(999_999_999, 100, 11.1, 11.2) == pytest.approx(1120)


def test_intraday_is_sorted_deduplicated_and_average_price_is_reasonable(monkeypatch):
    bars = [
        {
            "time": "2024-01-03 09:31:00",
            "open": 11.1,
            "high": 11.3,
            "low": 11.0,
            "close": 11.2,
            "volume": 200,
            "amount": 224_000,
        },
        {
            "time": "2024-01-02 15:00:00",
            "open": 10,
            "high": 10,
            "low": 10,
            "close": 10,
            "volume": 100,
            "amount": 100_000,
        },
        {
            "time": "2024-01-03 09:30:00",
            "open": 11,
            "high": 11.2,
            "low": 10.9,
            "close": 11.1,
            "volume": 100,
            "amount": 111_000,
        },
        {
            "time": "2024-01-03 09:31:00",
            "open": 11.1,
            "high": 11.3,
            "low": 11.0,
            "close": 11.2,
            "volume": 200,
            "amount": 224_000,
        },
    ]
    monkeypatch.setattr(
        intraday_service.data_source,
        "get_bars",
        lambda *_args: (bars, {"source": "test", "is_cached": False}),
    )

    result = intraday_service.get_intraday("000001")

    assert result["date"] == "2024-01-03"
    assert [point["time"] for point in result["points"]] == [
        "2024-01-03 09:30:00",
        "2024-01-03 09:31:00",
    ]
    assert result["points"][0]["average_price"] == 11.1
    assert result["points"][1]["average_price"] == pytest.approx(11.1667)
