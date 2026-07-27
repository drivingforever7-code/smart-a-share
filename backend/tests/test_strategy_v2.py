from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategy_catalog_v2 import BUILTIN_STRATEGIES, LEGACY_BUILTIN_IDS
from app.strategy_engine import prepare_indicators
from app.strategy_lab_service import _aggregate


def test_new_catalog_replaces_legacy_strategies():
    ids = {item["id"] for item in BUILTIN_STRATEGIES}
    assert len(ids) == 9
    assert ids.isdisjoint(LEGACY_BUILTIN_IDS)
    assert {"multifactor_resonance", "risk_balanced_short", "risk_balanced_swing"} <= ids


def test_factor_indicators_are_computed_without_future_data():
    rows = 120
    close = np.linspace(10, 18, rows)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.25,
            "close": close,
            "volume": np.linspace(1_000_000, 1_800_000, rows),
        }
    )
    enriched = prepare_indicators(frame)
    expected = {
        "adx14",
        "atr_pct",
        "momentum20",
        "momentum60",
        "mfi14",
        "obv_slope20",
        "factor_score",
    }
    assert expected <= set(enriched.columns)
    assert 0 <= enriched["factor_score"].iloc[-1] <= 100


def test_strategy_lab_aggregation_prioritizes_robust_metrics():
    summary = _aggregate(
        [
            {
                "trades": [{"return_pct": value} for value in [2, 2, 2, 1, 1, 1, -1, -1, -1, -1]],
                "total_return": 12,
                "max_drawdown": 8,
                "sharpe_ratio": 1.1,
            },
            {
                "trades": [{"return_pct": value} for value in [1] * 6 + [-1] * 14],
                "total_return": -3,
                "max_drawdown": 15,
                "sharpe_ratio": -0.1,
            },
        ]
    )
    assert summary["trade_count"] == 30
    assert summary["win_rate"] == 40
    assert summary["profit_factor"] == 0.833
    assert summary["median_total_return"] == 4.5
