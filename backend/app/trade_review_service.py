from __future__ import annotations

from typing import Any

from .ai_analysis_service import AiServiceError, _chat_json
from .ai_schemas import TradeReviewRequest
from .market_service import market_service
from .reliable_data_source import data_source


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _reference_levels(bars: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in bars if _number(row.get("close"))]
    if len(valid) < 5:
        return {"available": False, "reason": "有效日线不足，不能给出可靠目标价和止损价。"}
    current = float(valid[-1]["close"])
    ranges: list[float] = []
    previous_close = current
    for row in valid[-15:]:
        high = _number(row.get("high")) or current
        low = _number(row.get("low")) or current
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = float(row["close"])
    atr = sum(ranges) / len(ranges)
    recent = valid[-20:]
    support = min((_number(row.get("low")) or current) for row in recent[-10:])
    resistance = max((_number(row.get("high")) or current) for row in recent)
    stop = min(current * 0.98, max(support, current - 1.5 * atr))
    target = max(resistance, current + 2 * atr)
    second_target = max(target + atr, current + 3 * atr)
    return {
        "available": True,
        "data_date": str(valid[-1].get("time", ""))[:10],
        "current_reference_price": round(current, 2),
        "atr_14": round(atr, 3),
        "recent_support": round(support, 2),
        "recent_resistance": round(resistance, 2),
        "baseline_target_price": round(target, 2),
        "baseline_second_target_price": round(second_target, 2),
        "baseline_stop_loss_price": round(stop, 2),
        "baseline_add_range": [round(max(support, current - atr), 2), round(max(support, current - 0.35 * atr), 2)],
        "basis": "最近日线支撑/压力与 ATR 波动区间，仅作风控参考。",
    }


def review_trade(payload: TradeReviewRequest) -> dict[str, Any]:
    """仅在用户主动请求时，根据可核对行情生成复盘和当前行动方案。"""
    snapshot: dict[str, Any] = {
        "description": payload.description,
        "trade_date": payload.trade_date,
        "action": payload.action,
        "price": payload.price,
        "position_pct": payload.position_pct,
    }
    if payload.code:
        try:
            snapshot["analysis_now"] = market_service.stock_analysis(payload.code, "short")
        except Exception as exc:
            snapshot["analysis_error"] = str(exc)[:180]
        try:
            bars, meta = data_source.get_bars(payload.code, "day", 180)
            trade_bars = bars
            if payload.trade_date:
                trade_bars = [row for row in bars if str(row.get("time", ""))[:10] <= payload.trade_date]
            snapshot["bars_available_at_trade"] = trade_bars[-40:]
            snapshot["recent_bars_for_current_plan"] = bars[-60:]
            snapshot["reference_levels"] = _reference_levels(bars)
            snapshot["bar_meta"] = meta
        except Exception as exc:
            snapshot["bar_error"] = str(exc)[:180]

    system = (
        "你是 A 股交易行动顾问。先给用户现在该怎么做，再简短复盘，不要训话、不要空泛评价。"
        "复盘历史买卖点时只能使用 bars_available_at_trade；当前措施可使用 analysis_now、recent_bars_for_current_plan 和 reference_levels。"
        "输出严格 JSON。必须含 action_plan 对象，其字段为 recommended_action（只能是加仓、继续持有、减仓、清仓、等待、分批买入之一）、"
        "action_summary、current_reference_price、target_price、second_target_price、stop_loss_price、add_or_rebuy_range（两个数字或 null）、"
        "suggested_position_pct、holding_period、price_basis、trigger_plan（数组）、action_rationale（数组）。"
        "所有价格字段必须是数字或 null；优先参考输入的支撑、压力和 ATR，说明触发条件，不能承诺收益。"
        "若行情过期、代码缺失或数据不足，价格填 null，并在 action_summary 与 data_limits 说明需要补什么数据，禁止臆造。"
        "同时输出 verdict、score(0-100)、entry_review、exit_review、position_review、discipline_review、mistakes、good_decisions、"
        "better_plan、missed_alternatives、improvement_actions、risks、data_limits。批评部分应短于行动方案。"
    )
    try:
        result = _chat_json(system, str(snapshot))
    except AiServiceError:
        raise
    plan = result.get("action_plan")
    if not isinstance(plan, dict):
        plan = {}
        result["action_plan"] = plan
    levels = snapshot.get("reference_levels", {})
    plan.setdefault("recommended_action", "等待")
    plan.setdefault("action_summary", "先等待可核对行情与完整交易信息，再决定操作。")
    for result_key, level_key in (
        ("current_reference_price", "current_reference_price"),
        ("target_price", "baseline_target_price"),
        ("second_target_price", "baseline_second_target_price"),
        ("stop_loss_price", "baseline_stop_loss_price"),
    ):
        plan[result_key] = _number(plan.get(result_key)) or levels.get(level_key)
    raw_range = plan.get("add_or_rebuy_range")
    if isinstance(raw_range, (list, tuple)) and len(raw_range) == 2:
        normalized_range = [_number(raw_range[0]), _number(raw_range[1])]
        plan["add_or_rebuy_range"] = normalized_range if all(normalized_range) else levels.get("baseline_add_range")
    else:
        plan["add_or_rebuy_range"] = levels.get("baseline_add_range")
    plan.setdefault("price_basis", levels.get("basis", "数据不足，暂无可靠价格依据。"))
    plan.setdefault("trigger_plan", [])
    plan.setdefault("action_rationale", [])
    return {"request": payload.model_dump(), "snapshot": snapshot, "review": result}