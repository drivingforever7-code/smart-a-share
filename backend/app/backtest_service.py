from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .data_source import MarketDataError
from .production_data_source import data_source
from .schemas import BacktestRequest


SUPPORTED_PRESETS = {
    "volume_breakout": "放量突破",
    "low_volume_pullback": "缩量回调",
    "ma_bull": "均线多头",
    "oversold_rebound": "超跌反弹",
    "macd_cross": "MACD 金叉",
    "strong_pullback": "强势股回踩",
}


def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    if request.preset not in SUPPORTED_PRESETS:
        raise MarketDataError("这个方案依赖当期财务数据，暂不支持历史回测")

    bars, meta = data_source.get_bars(request.code, "day", 2000)
    frame = pd.DataFrame(bars)
    if frame.empty or len(frame) < 80:
        raise MarketDataError("历史 K 线不足 80 个交易日，无法可靠验证")

    frame["date"] = pd.to_datetime(frame["time"])
    frame = frame.sort_values("date").reset_index(drop=True)
    if request.start_date:
        frame = frame[frame["date"] >= pd.Timestamp(request.start_date)]
    if request.end_date:
        frame = frame[frame["date"] <= pd.Timestamp(request.end_date)]
    frame = frame.reset_index(drop=True)
    if len(frame) < 80:
        raise MarketDataError("所选日期范围的数据不足 80 个交易日")

    signal = _build_signal(frame, request.preset)
    trades = _simulate_trades(frame, signal, request)
    curve = _equity_curve(frame, trades)
    metrics = _metrics(frame, curve, trades)

    name = request.code
    try:
        quotes, _ = data_source.get_spot_quotes()
        quote = next((item for item in quotes if item["code"] == request.code), None)
        if quote:
            name = quote["name"]
    except MarketDataError:
        pass

    return {
        "code": request.code,
        "name": name,
        "preset": SUPPORTED_PRESETS[request.preset],
        "start_date": frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        **metrics,
        "equity_curve": curve,
        "trades": trades,
        "meta": meta,
    }


def _build_signal(frame: pd.DataFrame, preset: str) -> pd.Series:
    close = frame["close"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    volume_ma20 = volume.rolling(20).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    if preset == "volume_breakout":
        previous_high = frame["high"].shift(1).rolling(20).max()
        condition = (close > previous_high) & (volume > volume_ma20.shift(1) * 1.5)
    elif preset == "low_volume_pullback":
        condition = (
            (ma20 > ma60)
            & (close >= ma20 * 0.98)
            & (close <= ma10 * 1.02)
            & (volume < volume_ma20)
        )
    elif preset == "ma_bull":
        aligned = (close > ma5) & (ma5 > ma10) & (ma10 > ma20)
        condition = aligned & ~aligned.shift(1, fill_value=False)
    elif preset == "oversold_rebound":
        condition = (rsi > 30) & (rsi.shift(1) <= 30) & (close > close.shift(1))
    elif preset == "macd_cross":
        condition = (dif > dea) & (dif.shift(1) <= dea.shift(1)) & (close > ma20)
    elif preset == "strong_pullback":
        condition = (
            (ma20 > ma60)
            & (close > ma10)
            & (low <= ma10 * 1.01)
            & (close.shift(1) < ma10.shift(1))
        )
    else:
        condition = pd.Series(False, index=frame.index)
    return condition.fillna(False)


def _simulate_trades(
    frame: pd.DataFrame,
    signal: pd.Series,
    request: BacktestRequest,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    next_available = 0
    cost = request.commission_pct / 100

    for signal_index in np.flatnonzero(signal.to_numpy()):
        if signal_index < next_available or signal_index + 1 >= len(frame):
            continue
        entry_index = signal_index + 1
        entry_price = float(frame.loc[entry_index, "open"])
        if not math.isfinite(entry_price) or entry_price <= 0:
            continue

        stop_price = entry_price * (1 - request.stop_loss_pct / 100)
        take_price = entry_price * (1 + request.take_profit_pct / 100)
        last_index = min(entry_index + request.holding_days - 1, len(frame) - 1)
        exit_index = last_index
        exit_price = float(frame.loc[last_index, "close"])
        exit_reason = "到期卖出"

        for index in range(entry_index, last_index + 1):
            day_low = float(frame.loc[index, "low"])
            day_high = float(frame.loc[index, "high"])
            # 同一天同时触发时采用先止损的保守假设。
            if day_low <= stop_price:
                exit_index = index
                exit_price = stop_price
                exit_reason = "触发止损"
                break
            if day_high >= take_price:
                exit_index = index
                exit_price = take_price
                exit_reason = "触发止盈"
                break

        return_pct = (exit_price / entry_price - 1 - cost * 2) * 100
        trades.append(
            {
                "signal_date": frame.loc[signal_index, "date"].strftime("%Y-%m-%d"),
                "entry_date": frame.loc[entry_index, "date"].strftime("%Y-%m-%d"),
                "exit_date": frame.loc[exit_index, "date"].strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 3),
                "exit_price": round(exit_price, 3),
                "return_pct": round(return_pct, 3),
                "exit_reason": exit_reason,
                "_exit_index": int(exit_index),
            }
        )
        next_available = exit_index + 1
    return trades


def _equity_curve(
    frame: pd.DataFrame,
    trades: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    exit_returns = {
        trade["_exit_index"]: trade["return_pct"] / 100
        for trade in trades
    }
    strategy_factor = 1.0
    benchmark_start = float(frame["close"].iloc[0])
    curve: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        if index in exit_returns:
            strategy_factor *= 1 + exit_returns[index]
        benchmark = (float(row["close"]) / benchmark_start - 1) * 100
        curve.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "strategy": round((strategy_factor - 1) * 100, 3),
                "benchmark": round(benchmark, 3),
            }
        )
    for trade in trades:
        trade.pop("_exit_index", None)
    return curve


def _metrics(
    frame: pd.DataFrame,
    curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    if not curve:
        raise MarketDataError("无法生成收益曲线")
    strategy = pd.Series([item["strategy"] / 100 + 1 for item in curve])
    daily_returns = strategy.pct_change().fillna(0)
    total_return = (strategy.iloc[-1] - 1) * 100
    calendar_days = max(1, (frame["date"].iloc[-1] - frame["date"].iloc[0]).days)
    years = calendar_days / 365.25
    annual_return = ((strategy.iloc[-1] ** (1 / years)) - 1) * 100 if years > 0 else 0
    running_max = strategy.cummax()
    drawdown = strategy / running_max - 1
    max_drawdown = abs(float(drawdown.min())) * 100
    volatility = float(daily_returns.std())
    sharpe = (
        float(daily_returns.mean() / volatility * math.sqrt(252))
        if volatility > 0
        else 0
    )
    wins = sum(trade["return_pct"] > 0 for trade in trades)
    return {
        "total_return": round(total_return, 3),
        "annual_return": round(annual_return, 3),
        "max_drawdown": round(max_drawdown, 3),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0,
        "trade_count": len(trades),
        "benchmark_return": curve[-1]["benchmark"],
    }
