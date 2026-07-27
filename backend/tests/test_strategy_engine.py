from datetime import date

import numpy as np
import pandas as pd

from app.financial_service import _conservative_available_date, enrich_price_frame
from app.strategy_engine import evaluate_strategy, prepare_indicators


def sample_frame(rows: int = 100) -> pd.DataFrame:
    close = np.linspace(10, 20, rows)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": np.linspace(1000, 2000, rows),
        }
    )


def test_rule_strategy_can_compare_two_indicators():
    frame = prepare_indicators(sample_frame())
    strategy = {
        "id": "test_ma",
        "category": "rule",
        "config": {
            "entry_logic": "all",
            "entry_conditions": [
                {
                    "left": "ma5",
                    "operator": "gt",
                    "right_type": "indicator",
                    "right": "ma20",
                }
            ],
            "exit_logic": "any",
            "exit_conditions": [],
        },
    }
    signals = evaluate_strategy(frame, strategy)
    assert bool(signals.entry.iloc[-1])
    assert not bool(signals.exit.iloc[-1])


def test_financial_report_only_appears_after_available_date():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-04-29", "2024-04-30"]),
            "close": [10, 10],
        }
    )
    periods = [
        {
            "available_date": "2024-04-30",
            "roe": 12,
            "revenue_growth": 15,
            "profit_growth": 18,
            "eps_annualized": 1,
            "book_value_per_share": 5,
        }
    ]
    result = enrich_price_frame(frame, periods)
    assert pd.isna(result.loc[0, "roe"])
    assert result.loc[1, "roe"] == 12
    assert result.loc[1, "pe"] == 10


def test_conservative_financial_available_dates():
    assert _conservative_available_date(date(2024, 3, 31)) == date(2024, 4, 30)
    assert _conservative_available_date(date(2024, 6, 30)) == date(2024, 8, 31)
    assert _conservative_available_date(date(2024, 12, 31)) == date(2025, 4, 30)
