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

    frame = frame.reset_index(drop=True)
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
        request.code,
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
            "execution_note": "日线信号次日执行；计入双边佣金、买卖滑点和卖出印花税；跳空按开盘价，一字板按不可成交处理。",
            "validation_note": "结果为单股历史回放，不等于全市场样本外验证",
        },
    }


def _price_limit_rate(code: str) -> float:
    """按证券代码估算普通交易日涨跌幅限制，ST 等特殊状态由后续数据层补充。"""
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    if code.startswith(("4", "8")):
        return 0.30
    return 0.10


def _valid_bar(frame: pd.DataFrame, index: int) -> bool:
    values = [frame.loc[index, key] for key in ("open", "high", "low", "close")]
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in values):
        return False
    if "volume" in frame.columns:
        volume = frame.loc[index, "volume"]
        if not math.isfinite(float(volume)) or float(volume) <= 0:
            return False
    return True


def _is_locked_limit(
    frame: pd.DataFrame,
    index: int,
    code: str,
    side: str,
) -> bool:
    """只拦截接近一字板的确定性不可成交场景，避免把普通触板误判为锁死。"""
    if index <= 0 or not _valid_bar(frame, index):
        return True
    previous_close = float(frame.loc[index - 1, "close"])
    if not math.isfinite(previous_close) or previous_close <= 0:
        return False
    day_high = float(frame.loc[index, "high"])
    day_low = float(frame.loc[index, "low"])
    one_price = abs(day_high - day_low) <= max(0.01, previous_close * 0.001)
    rate = _price_limit_rate(code)
    if side == "buy":
        upper = previous_close * (1 + rate)
        return one_price and day_low >= upper * 0.997
    lower = previous_close * (1 - rate)
    return one_price and day_high <= lower * 1.003


def _simulate_trades(
    frame: pd.DataFrame,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    entry_score: pd.Series,
    exit_score: pd.Series,
    first_index: int,
    last_index: int,
    risk: dict[str, Any],
    code: str = "000001",
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    next_available = first_index
    commission = float(risk.get("commission_pct", 0.1)) / 100
    slippage = float(risk.get("slippage_pct", 0.05)) / 100
    stamp_duty = float(risk.get("stamp_duty_pct", 0.05)) / 100
    stop_loss_pct = float(risk.get("stop_loss_pct", 7))
    take_profit_pct = float(risk.get("take_profit_pct", 15))
    max_days = int(risk.get("max_holding_days", 10))

    for signal_index in np.flatnonzero(entry_signal.to_numpy()):
        if signal_index < next_available or signal_index < first_index:
            continue
        entry_index = signal_index + 1
        if entry_index > last_index:
            break
        if not _valid_bar(frame, entry_index):
            continue
        if _is_locked_limit(frame, entry_index, code, "buy"):
            continue

        raw_entry_price = float(frame.loc[entry_index, "open"])
        entry_price = raw_entry_price * (1 + slippage)
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        take_price = entry_price * (1 + take_profit_pct / 100)
        planned_last = min(entry_index + max_days - 1, last_index)
        exit_index: int | None = None
        raw_exit_price: float | None = None
        exit_reason = ""
        exit_signal_score = 0.0
        pending_signal_index: int | None = None
        estimated_exit = False

        for index in range(entry_index, last_index + 1):
            if not _valid_bar(frame, index):
                continue

            locked_sell = _is_locked_limit(frame, index, code, "sell")
            day_open = float(frame.loc[index, "open"])
            day_low = float(frame.loc[index, "low"])
            day_high = float(frame.loc[index, "high"])

            # 收盘后产生的卖出信号，只允许从下一交易日开盘起执行。
            if pending_signal_index is not None and index > pending_signal_index:
                if locked_sell:
                    continue
                exit_index = index
                raw_exit_price = day_open
                exit_reason = "策略卖出信号·次日开盘"
                exit_signal_score = float(exit_score.iloc[pending_signal_index])
                break

            if not locked_sell:
                # 跳空穿越止损/止盈时使用实际开盘价，不能虚构触发价成交。
                if day_open <= stop_price:
                    exit_index = index
                    raw_exit_price = day_open
                    exit_reason = "跳空触发止损"
                    exit_signal_score = float(exit_score.iloc[index])
                    break
                if day_open >= take_price:
                    exit_index = index
                    raw_exit_price = day_open
                    exit_reason = "跳空触发止盈"
                    exit_signal_score = float(exit_score.iloc[index])
                    break
                # 同日同时触发时先按止损处理，采用保守假设。
                if day_low <= stop_price:
                    exit_index = index
                    raw_exit_price = stop_price
                    exit_reason = "触发止损"
                    exit_signal_score = float(exit_score.iloc[index])
                    break
                if day_high >= take_price:
                    exit_index = index
                    raw_exit_price = take_price
                    exit_reason = "触发止盈"
                    exit_signal_score = float(exit_score.iloc[index])
                    break

            # 最长持有期是进场前已冻结的规则，可按当日收盘执行。
            if index >= planned_last:
                if locked_sell:
                    continue
                exit_index = index
                raw_exit_price = float(frame.loc[index, "close"])
                exit_reason = "达到最长持有期"
                exit_signal_score = float(exit_score.iloc[index])
                break

            if bool(exit_signal.iloc[index]):
                pending_signal_index = index

        if exit_index is None or raw_exit_price is None:
            valid_indices = [
                index
                for index in range(entry_index, last_index + 1)
                if _valid_bar(frame, index)
            ]
            if not valid_indices:
                continue
            exit_index = valid_indices[-1]
            raw_exit_price = float(frame.loc[exit_index, "close"])
            exit_reason = "回测区间末尾估值"
            exit_signal_score = float(exit_score.iloc[exit_index])
            estimated_exit = True

        exit_price = raw_exit_price * (1 - slippage)
        buy_cost_rate = commission
        sell_cost_rate = commission + stamp_duty
        gross_return_pct = (raw_exit_price / raw_entry_price - 1) * 100
        net_factor = (exit_price / entry_price) * (1 - sell_cost_rate) / (1 + buy_cost_rate)
        return_pct = (net_factor - 1) * 100
        trades.append(
            {
                "signal_date": frame.loc[signal_index, "date"].strftime("%Y-%m-%d"),
                "entry_date": frame.loc[entry_index, "date"].strftime("%Y-%m-%d"),
                "exit_date": frame.loc[exit_index, "date"].strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 3),
                "exit_price": round(exit_price, 3),
                "gross_return_pct": round(gross_return_pct, 3),
                "return_pct": round(return_pct, 3),
                "cost_pct": round(gross_return_pct - return_pct, 3),
                "exit_reason": exit_reason,
                "estimated_exit": estimated_exit,
                "entry_score": round(float(entry_score.iloc[signal_index]), 2),
                "exit_score": round(exit_signal_score, 2),
                "_entry_index": int(entry_index),
                "_exit_index": int(exit_index),
                "_buy_cost_rate": buy_cost_rate,
            }
        )
        # 若在开盘退出，当日收盘信号仍可用于下一交易日重新进入。
        next_available = exit_index
    return trades


def _equity_curve(
    frame: pd.DataFrame,
    trades: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按每日收盘价盯市，平仓日使用实际净成交结果。"""
    ordered_trades = sorted(trades, key=lambda item: item["_entry_index"])
    strategy_factor = 1.0
    trade_cursor = 0
    benchmark_start = float(frame["close"].iloc[0])
    curve: list[dict[str, Any]] = []

    for index, row in frame.iterrows():
        current_value = strategy_factor
        if trade_cursor < len(ordered_trades):
            trade = ordered_trades[trade_cursor]
            entry_index = int(trade["_entry_index"])
            exit_index = int(trade["_exit_index"])
            if entry_index <= index < exit_index:
                current_value = (
                    strategy_factor
                    * (float(row["close"]) / float(trade["entry_price"]))
                    / (1 + float(trade["_buy_cost_rate"]))
                )
            elif index == exit_index:
                strategy_factor *= 1 + float(trade["return_pct"]) / 100
                current_value = strategy_factor
                trade_cursor += 1

        curve.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "strategy": round((current_value - 1) * 100, 3),
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
