from __future__ import annotations

from typing import Any

from .ai_analysis_service import AiServiceError, _chat_json
from .ai_schemas import TradeReviewRequest
from .market_service import market_service
from .reliable_data_source import data_source


def review_trade(payload: TradeReviewRequest) -> dict[str, Any]:
    """仅在用户主动请求时，根据可核对行情对一笔交易进行复盘。"""
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
            if payload.trade_date:
                bars = [row for row in bars if str(row.get("time", ""))[:10] <= payload.trade_date]
            snapshot["historical_bars"] = bars[-40:]
            snapshot["bar_meta"] = meta
        except Exception as exc:
            snapshot["bar_error"] = str(exc)[:180]

    system = (
        "你是严格、直接但不羞辱用户的 A 股交易复盘教练。只能使用输入快照中在交易时已可用的数据，"
        "不得用未来行情替当时决策找理由。输出 JSON，字段必须包括 verdict、score(0-100)、"
        "entry_review、exit_review、position_review、discipline_review、mistakes、good_decisions、"
        "better_plan、missed_alternatives、improvement_actions、risks、data_limits。"
        "必须明确指出买卖点、仓位、止损和机会成本问题；没有足够数据时直说。"
    )
    try:
        result = _chat_json(system, str(snapshot))
    except AiServiceError:
        raise
    return {"request": payload.model_dump(), "snapshot": snapshot, "review": result}
