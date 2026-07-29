from __future__ import annotations

from datetime import datetime

from app import limit_break_service as service


def test_pre_market_auto_capture_is_skipped(monkeypatch):
    monkeypatch.setattr(service, "_now", lambda: datetime(2026, 7, 30, 6, 30))
    monkeypatch.setattr(
        service,
        "_fetch_pools",
        lambda _: (_ for _ in ()).throw(AssertionError("盘前不应请求炸板行情")),
    )

    result = service.capture_limit_breaks("auto", "2026-07-30")

    assert result["stage"] == "pre_market"
    assert result["created"] == 0
    assert "盘中预测" in result["skipped_reason"]
