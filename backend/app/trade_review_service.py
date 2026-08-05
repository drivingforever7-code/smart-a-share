from __future__ import annotations

import re
from datetime import date
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


def _conversation_text(payload: TradeReviewRequest) -> str:
    return "\n".join([*(item.content for item in payload.history[-8:]), payload.description])


def _resolve_stock(payload: TradeReviewRequest) -> dict[str, str] | None:
    text = _conversation_text(payload)
    explicit_code = payload.code or next(iter(re.findall(r"(?<!\d)\d{6}(?!\d)", text)), None)
    if explicit_code:
        return {"code": explicit_code, "name": ""}
    try:
        quotes, _ = data_source.get_spot_quotes()
    except Exception:
        quotes = []

    generic_aliases = {"科技", "股份", "集团", "银行", "证券", "能源", "发展", "控股", "中国"}
    matches: list[tuple[int, dict[str, Any]]] = []
    for quote in quotes:
        name = str(quote.get("name", "")).strip()
        if not name:
            continue
        aliases = {name}
        cleaned = re.sub(r"^(ST|\*ST|N)", "", name, flags=re.IGNORECASE)
        aliases.add(cleaned)
        if len(cleaned) >= 4:
            aliases.update({cleaned[-3:], cleaned[-2:]})
        matched = [alias for alias in aliases if len(alias) >= 2 and alias not in generic_aliases and alias in text]
        if matched:
            matches.append((max(map(len, matched)), quote))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return None
    quote = matches[0][1]
    return {"code": str(quote.get("code", "")), "name": str(quote.get("name", ""))}


def _extract_trade_date(payload: TradeReviewRequest) -> str | None:
    if payload.trade_date:
        return payload.trade_date
    text = _conversation_text(payload)
    match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    if "今天" in payload.description or "今日" in payload.description:
        return date.today().isoformat()
    return None


def review_trade(payload: TradeReviewRequest) -> dict[str, Any]:
    """从自然语言对话识别股票，并生成当前行动方案。"""
    resolved_stock = _resolve_stock(payload)
    trade_date = _extract_trade_date(payload)
    snapshot: dict[str, Any] = {
        "latest_user_message": payload.description,
        "conversation_history": [item.model_dump() for item in payload.history[-8:]],
        "resolved_stock": resolved_stock,
        "trade_date": trade_date,
        "legacy_structured_input": {"action": payload.action, "price": payload.price, "position_pct": payload.position_pct},
    }
    if resolved_stock:
        code = resolved_stock["code"]
        try:
            snapshot["analysis_now"] = market_service.stock_analysis(code, "short")
        except Exception as exc:
            snapshot["analysis_error"] = str(exc)[:180]
        try:
            bars, meta = data_source.get_bars(code, "day", 180)
            trade_bars = bars if not trade_date else [row for row in bars if str(row.get("time", ""))[:10] <= trade_date]
            snapshot["bars_available_at_trade"] = trade_bars[-40:]
            snapshot["recent_bars_for_current_plan"] = bars[-60:]
            snapshot["reference_levels"] = _reference_levels(bars)
            snapshot["bar_meta"] = meta
        except Exception as exc:
            snapshot["bar_error"] = str(exc)[:180]

    system = (
        "你是 A 股交易行动顾问，正在与用户连续对话。先回答用户这轮问题，再给现在该怎么做；不要训话和空泛评价。"
        "若 resolved_stock 为空，必须先请用户说明股票代码或完整名称，所有价格填 null，不得猜股票。"
        "复盘历史买卖点只能使用 bars_available_at_trade；当前措施可使用 analysis_now、recent_bars_for_current_plan 和 reference_levels。"
        "输出严格 JSON。必须含 reply（自然、简洁、可以直接显示的对话回答）和 action_plan。action_plan 字段为 recommended_action"
        "（只能是加仓、继续持有、减仓、清仓、等待、分批买入之一）、action_summary、current_reference_price、target_price、"
        "second_target_price、stop_loss_price、add_or_rebuy_range（两个数字或 null）、suggested_position_pct、holding_period、"
        "price_basis、trigger_plan（数组）、action_rationale（数组）。所有价格必须是数字或 null，不能承诺收益。"
        "同时输出 verdict、score、entry_review、exit_review、mistakes、risks、data_limits；这些复盘字段保持简短。"
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
    if not resolved_stock:
        result["reply"] = result.get("reply") or "请告诉我股票的 6 位代码或完整名称，以及你做了什么，我才能读取真实行情给你目标价和止损价。"
        plan.update({"recommended_action": "等待", "action_summary": "尚未识别到具体股票，请先补充股票代码或名称。", "current_reference_price": None, "target_price": None, "second_target_price": None, "stop_loss_price": None, "add_or_rebuy_range": None})
    else:
        plan.setdefault("recommended_action", "等待")
        plan.setdefault("action_summary", "先按触发条件观察，不立即追加风险。")
        for result_key, level_key in (("current_reference_price", "current_reference_price"), ("target_price", "baseline_target_price"), ("second_target_price", "baseline_second_target_price"), ("stop_loss_price", "baseline_stop_loss_price")):
            plan[result_key] = _number(plan.get(result_key)) or levels.get(level_key)
        raw_range = plan.get("add_or_rebuy_range")
        normalized = [_number(item) for item in raw_range] if isinstance(raw_range, (list, tuple)) and len(raw_range) == 2 else []
        plan["add_or_rebuy_range"] = normalized if len(normalized) == 2 and all(normalized) else levels.get("baseline_add_range")
    plan.setdefault("price_basis", levels.get("basis", "数据不足，暂无可靠价格依据。"))
    plan.setdefault("trigger_plan", [])
    plan.setdefault("action_rationale", [])
    result.setdefault("reply", plan.get("action_summary", "请继续告诉我你的交易情况。"))
    return {"request": payload.model_dump(), "snapshot": snapshot, "review": result}