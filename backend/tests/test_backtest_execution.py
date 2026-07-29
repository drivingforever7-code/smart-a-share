from __future__ import annotations

import pandas as pd
import pytest

from app.strategy_backtest_service import _equity_curve, _simulate_trades


def _frame(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-02", periods=len(rows), freq="B"),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": [row[4] for row in rows],
        }
    )


def _series(values: list[bool | float]) -> pd.Series:
    return pd.Series(values)


def _risk(**overrides: float | int) -> dict[str, float | int]:
    return {
        "stop_loss_pct": 20,
        "take_profit_pct": 50,
        "max_holding_days": 20,
        "commission_pct": 0,
        "slippage_pct": 0,
        "stamp_duty_pct": 0,
        **overrides,
    }


def test_close_exit_signal_executes_at_next_open():
    frame = _frame(
        [
            (10.0, 10.3, 9.8, 10.1, 1000),
            (10.2, 10.6, 10.0, 10.4, 1000),
            (10.5, 10.9, 10.3, 10.7, 1000),
            (10.6, 10.8, 10.2, 10.4, 1000),
            (10.4, 10.7, 10.1, 10.5, 1000),
        ]
    )
    trades = _simulate_trades(
        frame,
        _series([True, False, False, False, False]),
        _series([False, False, True, False, False]),
        _series([80.0, 0, 0, 0, 0]),
        _series([0, 0, 65.0, 0, 0]),
        0,
        4,
        _risk(),
    )

    assert len(trades) == 1
    assert trades[0]["entry_date"] == "2024-01-03"
    assert trades[0]["exit_date"] == "2024-01-05"
    assert trades[0]["exit_price"] == 10.6
    assert trades[0]["exit_reason"] == "策略卖出信号·次日开盘"
    assert trades[0]["exit_score"] == 65


def test_gap_stop_uses_actual_open_instead_of_stop_price():
    frame = _frame(
        [
            (10.0, 10.2, 9.9, 10.0, 1000),
            (10.0, 10.3, 9.8, 10.1, 1000),
            (8.5, 8.8, 8.2, 8.6, 1000),
            (8.6, 8.9, 8.4, 8.7, 1000),
        ]
    )
    trades = _simulate_trades(
        frame,
        _series([True, False, False, False]),
        _series([False, False, False, False]),
        _series([80.0, 0, 0, 0]),
        _series([0.0, 0, 0, 0]),
        0,
        3,
        _risk(stop_loss_pct=10),
    )

    assert trades[0]["exit_price"] == 8.5
    assert trades[0]["exit_reason"] == "跳空触发止损"
    assert trades[0]["return_pct"] == -15


def test_locked_limit_up_does_not_create_fictitious_entry():
    frame = _frame(
        [
            (10.0, 10.2, 9.8, 10.0, 1000),
            (11.0, 11.0, 11.0, 11.0, 5000),
            (11.2, 11.5, 11.0, 11.3, 5000),
        ]
    )
    trades = _simulate_trades(
        frame,
        _series([True, False, False]),
        _series([False, False, False]),
        _series([80.0, 0, 0]),
        _series([0.0, 0, 0]),
        0,
        2,
        _risk(),
        "000001",
    )

    assert trades == []


def test_fees_slippage_and_sell_stamp_duty_are_all_deducted():
    frame = _frame(
        [
            (10.0, 10.2, 9.8, 10.0, 1000),
            (10.0, 10.2, 9.8, 10.0, 1000),
            (10.0, 10.2, 9.8, 10.0, 1000),
        ]
    )
    trades = _simulate_trades(
        frame,
        _series([True, False, False]),
        _series([False, False, False]),
        _series([80.0, 0, 0]),
        _series([0.0, 0, 0]),
        0,
        2,
        _risk(
            max_holding_days=2,
            commission_pct=0.1,
            slippage_pct=0.05,
            stamp_duty_pct=0.05,
        ),
    )

    expected = (9.995 / 10.005) * (1 - 0.0015) / (1 + 0.001) - 1
    assert trades[0]["return_pct"] == pytest.approx(expected * 100, abs=0.001)
    assert trades[0]["return_pct"] < -0.3


def test_equity_curve_marks_open_position_to_market_each_day():
    frame = _frame(
        [
            (10.0, 10.2, 9.8, 10.0, 1000),
            (10.0, 10.2, 9.8, 10.0, 1000),
            (10.5, 11.2, 10.4, 11.0, 1000),
            (11.0, 11.2, 10.8, 11.0, 1000),
        ]
    )
    trades = [
        {
            "entry_price": 10.0,
            "return_pct": 10.0,
            "_entry_index": 1,
            "_exit_index": 3,
            "_buy_cost_rate": 0.0,
        }
    ]

    curve = _equity_curve(frame, trades)

    assert curve[0]["strategy"] == 0
    assert curve[1]["strategy"] == 0
    assert curve[2]["strategy"] == 10
    assert curve[3]["strategy"] == 10


def test_execution_is_deterministic_for_identical_input():
    frame = _frame(
        [
            (10.0, 10.2, 9.8, 10.0, 1000),
            (10.1, 10.4, 9.9, 10.2, 1000),
            (10.3, 10.6, 10.1, 10.4, 1000),
            (10.5, 10.8, 10.3, 10.6, 1000),
        ]
    )
    args = (
        frame,
        _series([True, False, False, False]),
        _series([False, False, True, False]),
        _series([80.0, 0, 0, 0]),
        _series([0.0, 0, 60.0, 0]),
        0,
        3,
        _risk(),
    )

    assert _simulate_trades(*args) == _simulate_trades(*args)
