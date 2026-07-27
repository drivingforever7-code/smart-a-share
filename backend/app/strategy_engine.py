from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .strategy_service import get_strategy


@dataclass
class StrategySignals:
    entry: pd.Series
    exit: pd.Series
    entry_score: pd.Series
    exit_score: pd.Series


def prepare_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """只用当日及更早的数据计算指标，避免回测偷看未来。"""
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    result = result.sort_values("date").reset_index(drop=True)
    for column in ["open", "high", "low", "close", "volume", "amount", "turnover_rate"]:
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")

    close = result["close"]
    high = result["high"]
    low = result["low"]
    volume = result["volume"]

    result["change_pct"] = close.pct_change() * 100
    for days in [5, 10, 20, 60]:
        result[f"ma{days}"] = close.rolling(days, min_periods=days).mean()

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    result["macd_diff"] = ema12 - ema26
    result["macd_signal"] = result["macd_diff"].ewm(
        span=9, adjust=False, min_periods=9
    ).mean()
    result["macd_hist"] = (result["macd_diff"] - result["macd_signal"]) * 2

    delta = close.diff()
    average_gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    average_loss = -delta.clip(upper=0).ewm(alpha=1 / 14, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    result["rsi14"] = 100 - 100 / (1 + relative_strength)

    lowest_9 = low.rolling(9, min_periods=9).min()
    highest_9 = high.rolling(9, min_periods=9).max()
    rsv = (close - lowest_9) / (highest_9 - lowest_9).replace(0, np.nan) * 100
    result["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()

    result["boll_mid"] = close.rolling(20, min_periods=20).mean()
    boll_std = close.rolling(20, min_periods=20).std(ddof=0)
    result["boll_upper"] = result["boll_mid"] + boll_std * 2
    result["boll_lower"] = result["boll_mid"] - boll_std * 2
    result["volume_ratio_20"] = volume / volume.rolling(
        20, min_periods=20
    ).mean().replace(0, np.nan)
    result["high_breakout_20"] = close > high.shift(1).rolling(
        20, min_periods=20
    ).max()
    result["close_to_ma10_pct"] = (close / result["ma10"] - 1) * 100
    result["close_to_ma20_pct"] = (close / result["ma20"] - 1) * 100

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    result["atr_pct"] = atr14 / close.replace(0, np.nan) * 100
    result["volatility20"] = close.pct_change().rolling(20, min_periods=20).std() * np.sqrt(252) * 100

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    smoothed_tr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / smoothed_tr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / smoothed_tr.replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    result["adx14"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    result["momentum20"] = close.pct_change(20) * 100
    result["momentum60"] = close.pct_change(60) * 100
    result["ma20_slope"] = result["ma20"].pct_change(5) * 100
    result["ma60_slope"] = result["ma60"].pct_change(10) * 100
    result["donchian_low10"] = low.shift(1).rolling(10, min_periods=10).min()

    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume.fillna(0)).cumsum()
    volume_scale = volume.rolling(20, min_periods=20).sum().replace(0, np.nan)
    result["obv_slope20"] = (obv - obv.shift(20)) / volume_scale * 100

    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * volume
    positive_flow = raw_money_flow.where(typical_price.diff() > 0, 0.0)
    negative_flow = raw_money_flow.where(typical_price.diff() < 0, 0.0)
    positive_sum = positive_flow.rolling(14, min_periods=14).sum()
    negative_sum = negative_flow.rolling(14, min_periods=14).sum()
    money_ratio = positive_sum / negative_sum.replace(0, np.nan)
    result["mfi14"] = 100 - 100 / (1 + money_ratio)

    trend_part = (
        (close > result["ma20"]).astype(float) * 12
        + (result["ma20"] > result["ma60"]).astype(float) * 13
        + (result["ma20_slope"] > 0).astype(float) * 10
    )
    momentum_part = ((result["momentum20"].clip(-10, 20) + 10) / 30 * 25).fillna(0)
    low_vol_part = ((8 - result["atr_pct"]).clip(0, 6) / 6 * 15).fillna(0)
    money_part = ((result["mfi14"].clip(30, 75) - 30) / 45 * 15).fillna(0)
    obv_part = ((result["obv_slope20"].clip(-10, 20) + 10) / 30 * 10).fillna(0)
    result["factor_score"] = (
        trend_part + momentum_part + low_vol_part + money_part + obv_part
    ).clip(0, 100)
    return result


def evaluate_strategy(
    frame: pd.DataFrame,
    strategy: dict[str, Any],
    *,
    visited: set[str] | None = None,
) -> StrategySignals:
    visited = set(visited or set())
    strategy_id = strategy["id"]
    if strategy_id in visited:
        raise ValueError("组合策略存在循环引用")
    visited.add(strategy_id)

    if strategy["category"] == "rule":
        config = strategy["config"]
        entry = _combine_conditions(
            frame,
            config.get("entry_conditions", []),
            config.get("entry_logic", "all"),
        )
        exit_signal = _combine_conditions(
            frame,
            config.get("exit_conditions", []),
            config.get("exit_logic", "any"),
            empty_value=False,
        )
        return StrategySignals(
            entry=entry,
            exit=exit_signal,
            entry_score=entry.astype(float) * 100,
            exit_score=exit_signal.astype(float) * 100,
        )

    config = strategy["config"]
    entry_score = pd.Series(0.0, index=frame.index)
    exit_score = pd.Series(0.0, index=frame.index)
    for component in config.get("components", []):
        child = get_strategy(component["strategy_id"])
        child_signals = evaluate_strategy(frame, child, visited=visited)
        weight = float(component["weight"])
        entry_score = entry_score + child_signals.entry.astype(float) * weight
        exit_score = exit_score + child_signals.exit.astype(float) * weight
    return StrategySignals(
        entry=(entry_score >= float(config.get("trigger_score", 50))).fillna(False),
        exit=(exit_score >= float(config.get("exit_score", 50))).fillna(False),
        entry_score=entry_score,
        exit_score=exit_score,
    )


def _combine_conditions(
    frame: pd.DataFrame,
    conditions: list[dict[str, Any]],
    logic: str,
    *,
    empty_value: bool = False,
) -> pd.Series:
    if not conditions:
        return pd.Series(empty_value, index=frame.index, dtype=bool)
    evaluated = [_evaluate_condition(frame, item) for item in conditions]
    result = evaluated[0]
    for current in evaluated[1:]:
        result = result & current if logic == "all" else result | current
    return result.fillna(False).astype(bool)


def _evaluate_condition(
    frame: pd.DataFrame,
    condition: dict[str, Any],
) -> pd.Series:
    left_name = condition["left"]
    if left_name not in frame:
        return pd.Series(False, index=frame.index)
    left = frame[left_name]
    operator = condition["operator"]
    if operator == "is_true":
        return left.fillna(False).astype(bool)

    right_raw = condition.get("right")
    if operator == "between":
        if not isinstance(right_raw, list) or len(right_raw) != 2:
            return pd.Series(False, index=frame.index)
        lower, upper = sorted(float(item) for item in right_raw)
        return left.between(lower, upper, inclusive="both")

    if condition.get("right_type") == "indicator":
        if not isinstance(right_raw, str) or right_raw not in frame:
            return pd.Series(False, index=frame.index)
        right: pd.Series | float = frame[right_raw]
    else:
        try:
            right = float(right_raw)
        except (TypeError, ValueError):
            return pd.Series(False, index=frame.index)

    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "cross_above":
        return (left > right) & (left.shift(1) <= _shift(right))
    if operator == "cross_below":
        return (left < right) & (left.shift(1) >= _shift(right))
    return pd.Series(False, index=frame.index)


def _shift(value: pd.Series | float) -> pd.Series | float:
    return value.shift(1) if isinstance(value, pd.Series) else value
