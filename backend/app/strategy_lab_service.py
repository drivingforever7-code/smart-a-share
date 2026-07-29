from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .database import SessionLocal
from .research_models import StrategyEvaluation
from .strategy_backtest_service import run_strategy_backtest
from .strategy_schemas import StrategyBacktestRequest
from .strategy_service import get_strategy, list_strategies


class StrategyLabRequest(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=12)
    strategy_ids: list[str] = Field(min_length=1, max_length=12)
    start_date: str = "2018-01-01"
    split_date: str = "2023-01-01"
    end_date: str = Field(default_factory=lambda: date.today().isoformat())

    @field_validator("codes")
    @classmethod
    def validate_codes(cls, values: list[str]) -> list[str]:
        normalized = []
        for raw in values:
            value = raw.strip()
            if len(value) != 6 or not value.isdigit():
                raise ValueError(f"股票代码必须是6位数字：{raw}")
            if value not in normalized:
                normalized.append(value)
        return normalized

    @model_validator(mode="after")
    def validate_dates(self):
        start = date.fromisoformat(self.start_date)
        split = date.fromisoformat(self.split_date)
        end = date.fromisoformat(self.end_date)
        if not start < split < end:
            raise ValueError("必须满足：开始日期 < 样本分界日 < 结束日期")
        return self


def evaluate_strategy_basket(request: StrategyLabRequest) -> dict[str, Any]:
    strategies = {item["id"]: item for item in list_strategies()}
    missing = [item for item in request.strategy_ids if item not in strategies]
    if missing:
        raise ValueError(f"没有找到策略：{', '.join(missing)}")

    split = date.fromisoformat(request.split_date)
    in_end = (split - timedelta(days=1)).isoformat()
    periods = {
        "in_sample": (request.start_date, in_end),
        "out_of_sample": (request.split_date, request.end_date),
    }
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []

    for strategy_id in request.strategy_ids:
        for sample_type, (start_date, end_date) in periods.items():
            for code in request.codes:
                try:
                    result = run_strategy_backtest(
                        StrategyBacktestRequest(
                            code=code,
                            strategy_id=strategy_id,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    )
                    buckets.setdefault((strategy_id, sample_type), []).append(result)
                except Exception as exc:
                    errors.append(
                        {
                            "strategy_id": strategy_id,
                            "sample_type": sample_type,
                            "code": code,
                            "error": str(exc)[:240],
                        }
                    )

    rows = []
    for strategy_id in request.strategy_ids:
        row = {
            "strategy_id": strategy_id,
            "strategy_name": strategies[strategy_id]["name"],
            "mode": strategies[strategy_id]["mode"],
        }
        for sample_type in periods:
            summary = _aggregate(buckets.get((strategy_id, sample_type), []))
            row[sample_type] = summary
            _persist_evaluation(
                strategy_id,
                sample_type,
                periods[sample_type],
                summary,
            )
        out_sample = row["out_of_sample"]
        row["assessment"] = _assessment(out_sample)
        rows.append(row)

    rows.sort(
        key=lambda item: (
            item["out_of_sample"]["profit_factor"],
            item["out_of_sample"]["expectancy"],
        ),
        reverse=True,
    )
    return {
        "codes": request.codes,
        "start_date": request.start_date,
        "split_date": request.split_date,
        "end_date": request.end_date,
        "rows": rows,
        "errors": errors,
        "method": {
            "in_sample": f"{request.start_date} 至 {in_end}",
            "out_of_sample": f"{request.split_date} 至 {request.end_date}",
            "ranking": "优先比较样本外盈亏比和单笔期望，不按胜率单独排名",
            "limitations": [
                "这是用户所选股票篮子的历史验证，不代表全A股表现",
                "不同股票上市时间和数据完整度不同，失败项会单独列出",
                "已计入基础涨跌停不可成交、可配置滑点、佣金和卖出印花税",
                "尚未覆盖 ST 特殊涨跌幅、最低五元佣金、盘口冲击和资金容量",
                "样本外结果若反复用于选择策略，会产生污染；最终结论需另留盲测集或滚动验证",
            ],
        },
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [trade for result in results for trade in result.get("trades", [])]
    returns = [float(trade["return_pct"]) for trade in trades]
    gross_profit = sum(max(0.0, value) for value in returns)
    gross_loss = abs(sum(min(0.0, value) for value in returns))
    wins = sum(value > 0 for value in returns)
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else (999.0 if gross_profit > 0 else 0.0)
    )
    return {
        "stock_count": len(results),
        "trade_count": len(trades),
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0,
        "profit_factor": round(profit_factor, 3),
        "expectancy": round(sum(returns) / len(returns), 3) if returns else 0,
        "median_total_return": round(
            median(float(item["total_return"]) for item in results), 3
        )
        if results
        else 0,
        "median_max_drawdown": round(
            median(float(item["max_drawdown"]) for item in results), 3
        )
        if results
        else 0,
        "median_sharpe": round(
            median(float(item["sharpe_ratio"]) for item in results), 3
        )
        if results
        else 0,
    }


def _assessment(summary: dict[str, Any]) -> str:
    trades = summary["trade_count"]
    profit_factor = summary["profit_factor"]
    expectancy = summary["expectancy"]
    drawdown = summary["median_max_drawdown"]
    if trades < 20:
        return "样本不足"
    if profit_factor >= 1.35 and expectancy > 0 and drawdown <= 25:
        return "样本外较稳健"
    if profit_factor >= 1.1 and expectancy > 0:
        return "样本外有正期望"
    if profit_factor < 1 or expectancy <= 0:
        return "样本外未通过"
    return "需要继续观察"


def _persist_evaluation(
    strategy_id: str,
    sample_type: str,
    period: tuple[str, str],
    summary: dict[str, Any],
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            StrategyEvaluation(
                strategy_id=strategy_id,
                code="BASKET",
                sample_type=sample_type,
                market_regime="all",
                start_date=period[0],
                end_date=period[1],
                trade_count=summary["trade_count"],
                win_rate=summary["win_rate"],
                profit_factor=summary["profit_factor"],
                expectancy=summary["expectancy"],
                total_return=summary["median_total_return"],
                max_drawdown=summary["median_max_drawdown"],
                sharpe_ratio=summary["median_sharpe"],
            )
        )
