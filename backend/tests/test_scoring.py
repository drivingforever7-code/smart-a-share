from __future__ import annotations

from datetime import datetime, timedelta

from app.scoring import analyze, recommendation


def make_bars(count: int = 100):
    start = datetime(2026, 1, 1)
    bars = []
    for index in range(count):
        close = 10 + index * 0.05
        bars.append(
            {
                "time": (start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "open": close - 0.02,
                "high": close + 0.08,
                "low": close - 0.08,
                "close": close,
                "volume": 1_000_000 + index * 3_000,
                "amount": close * (1_000_000 + index * 3_000),
            }
        )
    return bars


def make_quote():
    return {
        "code": "600000",
        "name": "测试股票",
        "market": "SH",
        "board": "主板",
        "industry": "银行",
        "price": 15.0,
        "change_pct": 2.3,
        "amount": 800_000_000,
        "turnover_rate": 4.5,
        "volume_ratio": 1.6,
        "amplitude": 3.2,
        "speed": 0.3,
        "change_5m": 0.2,
        "change_60d": 18.0,
        "change_ytd": 12.0,
        "open": 14.7,
        "high": 15.1,
        "low": 14.6,
        "pe": 18.0,
        "pb": 1.8,
        "total_market_cap": 100_000_000_000,
        "is_st": False,
        "status": "正常",
    }


def test_short_analysis_has_explanation_and_risk_plan():
    result = analyze(
        make_quote(),
        "short",
        bars=make_bars(),
        meta={
            "source": "test",
            "quote_time": None,
            "fetched_at": "2026-07-27T10:00:00",
            "is_cached": False,
        },
    )

    assert 0 <= result["score"] <= 100
    assert len(result["dimensions"]) == 6
    assert result["reasons"]
    assert result["entry_low"] is not None
    assert result["stop_loss"] < result["price"]
    assert result["invalidation"]


def test_st_stock_is_never_a_buy_recommendation():
    quote = make_quote()
    quote["is_st"] = True
    quote["name"] = "ST测试"
    result = analyze(
        quote,
        "short",
        bars=make_bars(),
        meta={
            "source": "test",
            "quote_time": None,
            "fetched_at": "2026-07-27T10:00:00",
            "is_cached": False,
        },
    )
    assert result["recommendation"] == "建议回避"
    assert any("ST" in risk for risk in result["risks"])


def test_low_confidence_cannot_be_direct_buy():
    assert recommendation(92, 50, []) == "建议观察"


def test_blocking_risk_has_highest_priority():
    assert recommendation(95, 95, ["停牌"]) == "建议回避"
