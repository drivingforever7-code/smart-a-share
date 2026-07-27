from __future__ import annotations

import pandas as pd

from app.backtest_service import _build_signal


def test_signal_uses_history_only_and_returns_boolean_series():
    frame = pd.DataFrame(
        {
            "close": [10 + index * 0.1 for index in range(100)],
            "open": [9.98 + index * 0.1 for index in range(100)],
            "high": [10.1 + index * 0.1 for index in range(100)],
            "low": [9.9 + index * 0.1 for index in range(100)],
            "volume": [1_000_000 + index * 1_000 for index in range(100)],
        }
    )
    signal = _build_signal(frame, "ma_bull")
    assert len(signal) == len(frame)
    assert signal.dtype == bool
    assert not signal.iloc[:19].any()
