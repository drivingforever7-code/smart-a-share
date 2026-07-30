from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auto_backtest_service as service
from app.database import Base, RankingAdviceSnapshot, RankingDiscovery


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    monkeypatch.setattr(
        service,
        "process_training_cycle",
        lambda *_: {"trade_date": "2026-07-30", "optimization": {}},
    )
    monkeypatch.setattr(
        service,
        "ranking_strategy_status",
        lambda: {
            "short": {"active_version": "short-v1.0"},
            "swing": {"active_version": "swing-v1.0"},
        },
    )
    monkeypatch.setattr(
        service,
        "discovery_version_map",
        lambda rows: {row.id: f"{row.mode}-v1.0" for row in rows},
    )
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
    assert short_first["action_advice"] in {"加仓", "继续持有", "减仓", "清仓", "观望"}
    assert short_first["action_date"] == "2026-07-30"
    assert result["summaries"]["short"]["positive_count"] == 1
    assert result["summaries"]["swing"]["priced_count"] == 3
    with isolated_database() as session:
        advice_count = len(list(session.scalars(select(RankingAdviceSnapshot))))
    assert advice_count == 6

def test_snapshot_rejects_missing_quote_time(isolated_database):
    items = [opportunity(f"00000{rank}", rank, "short") for rank in range(1, 4)]
    for item in items:
        item["meta"]["quote_time"] = None
        item["meta"]["fetched_at"] = "2026-07-30T15:01:00"

    assert service.capture_mode_snapshot("short", items) is False
    with isolated_database() as session:
        assert list(session.scalars(select(RankingDiscovery))) == []


def test_snapshot_deduplicates_codes_before_ranking(isolated_database):
    first = opportunity("000001", 1, "short")
    duplicate = {**first, "name": "重复股票"}
    items = [
        first,
        duplicate,
        opportunity("000002", 2, "short"),
        opportunity("000003", 3, "short"),
    ]

    assert service.capture_mode_snapshot("short", items) is True
    with isolated_database() as session:
        rows = list(session.scalars(select(RankingDiscovery).order_by(RankingDiscovery.rank)))
    assert [(row.rank, row.code) for row in rows] == [
        (1, "000001"),
        (2, "000002"),
        (3, "000003"),
    ]


def test_repair_removes_later_unverified_duplicate_day(isolated_database):
    with isolated_database.begin() as session:
        for day in ("2026-07-29", "2026-07-30"):
            for rank in range(1, 4):
                item = opportunity(f"00000{rank}", rank, "short")
                session.add(
                    RankingDiscovery(
                        discovery_date=day,
                        mode="short",
                        rank=rank,
                        code=item["code"],
                        name=item["name"],
                        industry=item["industry"],
                        discovery_price=item["price"],
                        discovery_score=item["score"],
                        recommendation=item["recommendation"],
                        confidence=item["confidence"],
                        reasons_json="[]",
                        risks_json="[]",
                        quote_time=None,
                        source="缓存；后台刷新中",
                    )
                )

    assert service.repair_repeated_cached_discoveries() == 3
    with isolated_database() as session:
        rows = list(session.scalars(select(RankingDiscovery)))
    assert {row.discovery_date for row in rows} == {"2026-07-29"}

def test_snapshot_accepts_independently_verified_trade_date(isolated_database):
    items = [opportunity(f"00000{rank}", rank, "short") for rank in range(1, 4)]
    for item in items:
        item["meta"]["quote_time"] = None
        item["meta"]["trade_date"] = "2026-07-30"

    assert service.capture_mode_snapshot("short", items) is True
    with isolated_database() as session:
        rows = list(session.scalars(select(RankingDiscovery)))
    assert len(rows) == 3
    assert all("交易日历确认" in row.source for row in rows)
