from app.ai_schemas import TradeReviewRequest
from app import trade_review_service as service


def test_reference_levels_produce_auditable_prices():
    bars = [
        {"time": f"2026-07-{day:02d}", "open": 9.8 + day * 0.05, "high": 10.2 + day * 0.05, "low": 9.6 + day * 0.05, "close": 10 + day * 0.05}
        for day in range(1, 21)
    ]
    levels = service._reference_levels(bars)
    assert levels["available"] is True
    assert levels["baseline_stop_loss_price"] < levels["current_reference_price"]
    assert levels["baseline_target_price"] > levels["current_reference_price"]
    assert len(levels["baseline_add_range"]) == 2


def test_review_trade_keeps_trade_time_and_current_data_separate(monkeypatch):
    bars = [
        {"time": f"2026-07-{day:02d}", "open": 10 + day * 0.1, "high": 10.4 + day * 0.1, "low": 9.8 + day * 0.1, "close": 10.2 + day * 0.1}
        for day in range(1, 21)
    ]
    monkeypatch.setattr(service.data_source, "get_bars", lambda *_: (bars, {"quote_time": "2026-07-20"}))
    monkeypatch.setattr(service.market_service, "stock_analysis", lambda *_: {"latest_price": 12.2, "score": 76})
    monkeypatch.setattr(service, "_chat_json", lambda *_: {"verdict": "测试"})
    result = service.review_trade(TradeReviewRequest(description="十元买入后询问操作", code="000001", trade_date="2026-07-10", action="买入", price=10))
    snapshot = result["snapshot"]
    assert len(snapshot["bars_available_at_trade"]) == 10
    assert len(snapshot["recent_bars_for_current_plan"]) == 20
    assert result["review"]["action_plan"]["target_price"] is not None
    assert result["review"]["action_plan"]["stop_loss_price"] is not None

def test_resolve_stock_from_chinese_name_in_conversation(monkeypatch):
    monkeypatch.setattr(
        service.data_source,
        "get_spot_quotes",
        lambda: ([{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}], {}),
    )
    payload = TradeReviewRequest(description="我今天买了茅台半仓，现在怎么办")
    assert service._resolve_stock(payload) == {"code": "600519", "name": "贵州茅台"}


def test_missing_stock_forces_clarification_and_no_prices(monkeypatch):
    monkeypatch.setattr(service.data_source, "get_spot_quotes", lambda: ([], {}))
    monkeypatch.setattr(
        service,
        "_chat_json",
        lambda *_: {"reply": "猜测回答", "action_plan": {"target_price": 99, "stop_loss_price": 88}},
    )
    result = service.review_trade(TradeReviewRequest(description="我今天买了一只票，怎么办"))
    plan = result["review"]["action_plan"]
    assert plan["recommended_action"] == "等待"
    assert plan["target_price"] is None
    assert plan["stop_loss_price"] is None
    assert "股票" in plan["action_summary"]