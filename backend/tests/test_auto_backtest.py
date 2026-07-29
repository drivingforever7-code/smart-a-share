from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auto_backtest_service as service
from app.database import Base, RankingDiscovery


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    return session_local


def opportunity(code: str, rank: int, mode: str) -> dict:
    return {
        "code": code,
        "name": f"测试{rank}",
        "industry": "测试行业",
        "price": 10.0 + rank,
        "score": 90.0 - rank,
        "recommendation": "建议买入",
        "confidence": 80.0,
        "reasons": ["趋势成立", f"{mode}信号"],
        "risks": ["波动风险"],
        "meta": {
            "quote_time": "2026-07-29 15:00:00",
            "fetched_at": "2026-07-29T15:01:00",
            "source": "测试源",
            "is_cached": False,
        },
    }


def test_capture_freezes_first_top_three(isolated_database):
    first = [opportunity(f"00000{rank}", rank, "short") for rank in range(1, 4)]
    assert service.capture_mode_snapshot("short", first) is True

    changed = [opportunity(f"60000{rank}", rank, "short") for rank in range(1, 4)]
    assert service.capture_mode_snapshot("short", changed) is False

    with isolated_database() as session:
        rows = list(session.scalars(select(RankingDiscovery).order_by(RankingDiscovery.rank)))
    assert [row.code for row in rows] == ["000001", "000002", "000003"]


def test_auto_backtest_calculates_return_and_summary(isolated_database, monkeypatch):
    def fake_opportunities(mode: str, *, limit: int):
        prefix = "0" if mode == "short" else "6"
        return [opportunity(f"{prefix}0000{rank}", rank, mode) for rank in range(1, 4)]

    quotes = [
        {"code": "000001", "price": 12.1},
        {"code": "000002", "price": 12.0},
        {"code": "000003", "price": 11.7},
        {"code": "600001", "price": 11.55},
        {"code": "600002", "price": 11.4},
        {"code": "600003", "price": 13.65},
    ]
    meta = {
        "quote_time": "2026-07-30 10:00:00",
        "fetched_at": datetime.now().isoformat(),
        "source": "测试源",
        "is_cached": False,
    }
    monkeypatch.setattr(service.market_service, "opportunities", fake_opportunities)
    monkeypatch.setattr(service.data_source, "get_spot_quotes", lambda: (quotes, meta))

    result = service.auto_backtest(5)

    assert len(result["items"]) == 6
    short_first = next(
        item for item in result["items"] if item["mode"] == "short" and item["rank"] == 1
    )
    assert short_first["return_pct"] == 10.0
    assert result["summaries"]["short"]["positive_count"] == 1
    assert result["summaries"]["swing"]["priced_count"] == 3
