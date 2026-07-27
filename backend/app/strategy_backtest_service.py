from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .data_source import MarketDataError
from .financial_service import enrich_price_frame, get_financial_history
from .market_regime_service import enrich_market_regime
from .reliable_data_source import data_source
from .strategy_engine import evaluate_strategy, prepare_indicators
from .strategy_schemas import StrategyBacktestRequest
from .strategy_service import (
    get_strategy,
    strategy_requires_fundamentals,
    strategy_requires_market_regime,
)


def run_strategy_backtest(request: StrategyBacktestRequest) -> dict[str, Any]:
    strategy = get_strategy(request.resolved_strategy_id)
    bars, meta = data_source.get_bars(request.code, "day", 2000)
    frame = pd.DataFrame(bars)
    if frame.empty or len(frame) < 80:
        raise MarketDataError("历史 K 线不足 80 个交易日，无法可靠回测")

    frame = frame.rename(columns={"time": "date"})
    frame = prepare_indicators(frame)
    market_note = "本策略不使用大盘环境"
    if strategy_requires_market_regime(strategy):
        frame = enrich_market_regime(frame)
        market_note = "大盘环境使用沪深300当日及更早数据，未使用未来行情"
    finance_note = "本策略不使用财务指标"
    if strategy_requires_fundamentals(strategy):
        start_year = (
            pd.Timestamp(request.start_date).year
            if request.start_date
            else int(frame["date"].min().year)
        )
        periods = get_financial_history(request.code, start_year=start_year)
        frame = enrich_price_frame(frame, periods)
        finance_note = (
            "财务数据按保守可用日期并入；历史PE/PB由当时股价与当期财务值估算，"
            "不会用当前财务数据回填过去"
        )

    signals = evaluate_strategy(frame, strategy)
    start = pd.Timestamp(request.start_date) if request.start_date else frame["date"].iloc[0]
    end = pd.Timestamp(request.end_date) if request.end_date else frame["date"].iloc[-1]
    active = (frame["date"] >= start) & (frame["date"] <= end)
    if active.sum() < 40:
        raise MarketDataError("所选日期范围少于 40 个交易日，回测结果没有参考价值")

    first_index = int(np.flatnonzero(active.to_numpy())[0])
    last_index = int(np.flatnonzero(active.to_numpy())[-1])
    risk = {**strategy["config"].get("risk", {}), **request.risk_overrides()}
    trades = _simulate_trades(
        frame,
        signals.entry,
        signals.exit,
        signals.entry_score,
        signals.exit_score,
        first_index,
        last_index,
        risk,
    )
    active_frame = frame.loc[first_index:last_index].copy()
    curve = _equity_curve(active_frame, trades)
    metrics = _metrics(active_frame, curve, trades)
    name = request.code
    try:
        quotes, _ = data_source.get_spot_quotes()
        quote = next((item for item in quotes if item["code"] == request.code), None)
        if quote:
            name = quote["name"]
    except MarketDataError:
        pass

    public_trades = [{key: value for key, value in item.items() if not key.startswith("_")} for item in trades]
    markers = [
        marker
        for trade in public_trades
        for marker in [
            {
                "date": trade["entry_date"],
                "type": "buy",
                "price": trade["entry_price"],
                "label": f"买入 · 信号{trade['entry_score']:.0f}分",
                "detail": f"{trade['signal_date']} 出现信号，下一交易日开盘买入",
            },
            {
                "date": trade["exit_date"],
                "type": "sell",
                "price": trade["exit_price"],
                "label": f"卖出 · {trade['exit_reason']}",
                "detail": f"本笔收益 {trade['return_pct']:.2f}%",
            },
        ]
    ]
    return {
        "code": request.code,
        "name": name,
        "strategy_id": strategy["id"],
        "strategy_name": strategy["name"],
        "preset": strategy["name"],
        "start_date": active_frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": active_frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        **metrics,
        "equity_curve": curve,
        "trades": public_trades,
        "markers": markers,
        "risk": risk,
        "meta": {
            **meta,
            "financial_note": finance_note,
            "market_note": market_note,
            "validation_note": "结果为单股历史回放，不等于全市场样本外验证",
        },
    }


def _simulate_trades(
    frame: pd.DataFrame,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    entry_score: pd.Series,
    exit_score: pd.Series,
    first_index: int,
    last_index: int,
    risk: dict[str, Any],
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    next_available = first_index
    commission = float(risk.get("commission_pct", 0.1)) / 100
    stop_loss_pct = float(risk.get("stop_loss_pct", 7))
    take_profit_pct = float(risk.get("take_profit_pct", 15))
    max_days = int(risk.get("max_holding_days", 10))

    for signal_index in np.flatnonzero(entry_signal.to_numpy()):
        if signal_index < next_available or signal_index < first_index:
            continue
        if signal_index + 1 > last_index:
            break
        entry_index = signal_index + 1
        entry_price = float(frame.loc[entry_index, "open"])
        if not math.isfinite(entry_price) or entry_price <= 0:
            continue

        stop_price = entry_price * (1 - stop_loss_pct / 100)
        take_price = entry_price * (1 + take_profit_pct / 100)
        planned_last = min(entry_index + max_days - 1, last_index)
        exit_index = planned_last
        exit_price = float(frame.loc[exit_index, "close"])
        exit_reason = "达到最长持有期"
        exit_signal_score = float(exit_score.iloc[exit_index])

        for index in range(entry_index, planned_last + 1):
            day_low = float(frame.loc[index, "low"])
            day_high = float(frame.loc[index, "high"])
            # 同日同时触发止损和止盈时，采用先止损的保守假设。
            if day_low <= stop_price:
                exit_index = index
                exit_price = stop_price
                exit_reason = "触发止损"
                exit_signal_score = float(exit_score.iloc[index])
                break
            if day_high >= take_price:
                exit_index = index
                exit_price = take_price
                exit_reason = "触发止盈"
                exit_signal_score = float(exit_score.iloc[index])
                break
            if index > entry_index and bool(exit_signal.iloc[index]):
                exit_index = index
                exit_price = float(frame.loc[index, "close"])
                exit_reason = "策略卖出信号"
                exit_signal_score = float(exit_score.iloc[index])
                break

        return_pct = (exit_price / entry_price - 1 - commission * 2) * 100
        trades.append(
            {
                "signal_date": frame.loc[signal_index, "date"].strftime("%Y-%m-%d"),
                "entry_date": frame.loc[entry_index, "date"].strftime("%Y-%m-%d"),
                "exit_date": frame.loc[exit_index, "date"].strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 3),
                "exit_price": round(exit_price, 3),
                "return_pct": round(return_pct, 3),
                "exit_reason": exit_reason,
                "entry_score": round(float(entry_score.iloc[signal_index]), 2),
                "exit_score": round(exit_signal_score, 2),
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
        trade["_exit_index"]: trade["return_pct"] / 100 for trade in trades
    }
    strategy_factor = 1.0
    benchmark_start = float(frame["close"].iloc[0])
    curve: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        if index in exit_returns:
            strategy_factor *= 1 + exit_returns[index]
        curve.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "strategy": round((strategy_factor - 1) * 100, 3),
                "benchmark": round((float(row["close"]) / benchmark_start - 1) * 100, 3),
            }
        )
    return curve


def _metrics(
    frame: pd.DataFrame,
    curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    strategy_value = pd.Series([item["strategy"] / 100 + 1 for item in curve])
    daily_returns = strategy_value.pct_change().fillna(0)
    total_return = (strategy_value.iloc[-1] - 1) * 100
    days = max(1, (frame["date"].iloc[-1] - frame["date"].iloc[0]).days)
    years = days / 365.25
    annual_return = (strategy_value.iloc[-1] ** (1 / years) - 1) * 100
    drawdown = strategy_value / strategy_value.cummax() - 1
    volatility = float(daily_returns.std())
    sharpe = (
        float(daily_returns.mean() / volatility * math.sqrt(252))
        if volatility > 0
        else 0
    )
    wins = sum(trade["return_pct"] > 0 for trade in trades)
    gross_profit = sum(max(0.0, float(trade["return_pct"])) for trade in trades)
    gross_loss = abs(sum(min(0.0, float(trade["return_pct"])) for trade in trades))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    expectancy = (
        sum(float(trade["return_pct"]) for trade in trades) / len(trades)
        if trades
        else 0.0
    )
    return {
        "total_return": round(float(total_return), 3),
        "annual_return": round(float(annual_return), 3),
        "max_drawdown": round(abs(float(drawdown.min())) * 100, 3),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0,
        "trade_count": len(trades),
        "profit_factor": round(profit_factor, 3),
        "expectancy": round(expectancy, 3),
        "benchmark_return": curve[-1]["benchmark"],
    }
