from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import ranking_optimizer_service as service
from app.database import Base, RankingStrategyVersion, RankingTrainingSample


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    service.invalidate_version_cache()
    return session_local


def opportunity(code: str, score: float = 80) -> dict:
    return {
        "code": code,
        "name": f"测试{code}",
        "price": 10,
        "score": score,
        "short_score": score,
        "swing_score": score - 5,
        "confidence": 80,
        "change_pct": 2,
        "turnover_rate": 8,
        "volume_ratio": 1.5,
        "amount": 500_000_000,
        "pe": 20,
        "pb": 2,
        "risks": [],
        "recommendation": "建议买入",
        "meta": {
            "quote_time": "2026-07-30 15:00:00",
            "source": "测试源",
        },
    }


def test_baseline_version_keeps_original_score(isolated_database):
    service.ensure_baseline_versions()
    result = service.apply_active_version("short", [opportunity("000001", 82)])

    assert result[0]["score"] == 82
    assert result[0]["strategy_version"] == "short-v1.0"
    assert result[0]["strategy_adjustment"] == 0


def test_training_cycle_matures_after_target_observation(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setitem(service.MODE_RULES["short"], "horizon", 1)
    monkeypatch.setitem(service.MODE_RULES["swing"], "horizon", 1)
    opportunities = {
        "short": [opportunity(f"0000{i:02d}") for i in range(1, 4)],
        "swing": [opportunity(f"6000{i:02d}") for i in range(1, 4)],
    }
    first_meta = {
        "quote_time": "2026-07-29 15:00:00",
        "fetched_at": "2026-07-29T15:01:00",
        "source": "测试源",
    }
    second_meta = {
        **first_meta,
        "quote_time": "2026-07-30 15:00:00",
        "fetched_at": "2026-07-30T15:01:00",
    }
    service.process_training_cycle(opportunities, [], first_meta)
    quotes = [
        {"code": item["code"], "price": 11}
        for items in opportunities.values()
        for item in items
    ]
    service.process_training_cycle(opportunities, quotes, second_meta)

    with isolated_database() as session:
        samples = list(session.scalars(select(RankingTrainingSample)))
    previous = [sample for sample in samples if sample.sample_date == "2026-07-29"]
    assert len(previous) == 6
    assert all(sample.matured for sample in previous)
    assert all(sample.label_return_pct == 10 for sample in previous)


def test_candidate_activates_only_after_out_of_time_improvement(isolated_database):
    service.ensure_baseline_versions()
    start = datetime(2026, 1, 1)
    with isolated_database.begin() as session:
        for day in range(20):
            sample_date = (start + timedelta(days=day)).date().isoformat()
            for rank in range(1, 21):
                positive = rank > 3
                features = {name: 0.5 for name in service.FEATURE_NAMES}
                features["price_change"] = 1.0 if positive else -1.0
                session.add(
                    RankingTrainingSample(
                        sample_date=sample_date,
                        mode="short",
                        code=f"{day:02d}{rank:04d}",
                        name="训练样本",
                        candidate_rank=rank,
                        discovery_price=10,
                        base_score=100 - rank,
                        strategy_score=100 - rank,
                        strategy_version="short-v1.0",
                        features_json=json.dumps(features),
                        target_observations=5,
                        matured=True,
                        label_return_pct=5 if positive else -5,
                        label_max_drawdown_pct=-1 if positive else -5,
                        label_positive=positive,
                        matured_at=datetime.now(),
                        quote_time=f"{sample_date} 15:00:00",
                        source="测试源",
                        created_at=datetime.now(),
                    )
                )

    with isolated_database.begin() as session:
        result = service._optimize_mode(session, "short", "2026-07-30")

    assert result["status"] == "activated"
    with isolated_database() as session:
        active = session.scalar(
            select(RankingStrategyVersion).where(
                RankingStrategyVersion.mode == "short",
                RankingStrategyVersion.is_active.is_(True),
            )
        )
    assert active is not None
    assert active.version == "short-v1.1"

def test_training_skips_fetch_time_without_real_quote_time(isolated_database):
    opportunities = {
        "short": [opportunity("000001")],
        "swing": [opportunity("600001")],
    }
    meta = {
        "quote_time": None,
        "fetched_at": "2026-07-30T15:01:00",
        "source": "缓存；后台刷新中",
    }

    result = service.process_training_cycle(opportunities, [], meta)

    assert result["skipped"] is True
    assert result["trade_date"] is None
    with isolated_database() as session:
        assert list(session.scalars(select(RankingTrainingSample))) == []


def test_training_deduplicates_candidates_and_keeps_order(isolated_database):
    repeated = opportunity("000001", 90)
    opportunities = {
        "short": [repeated, repeated, opportunity("000002", 80)],
        "swing": [opportunity("600001", 85)],
    }
    meta = {
        "quote_time": "2026-07-30 15:00:00",
        "fetched_at": "2026-07-30T15:01:00",
        "source": "测试源",
    }

    result = service.process_training_cycle(opportunities, [], meta)

    assert result["skipped"] is False
    with isolated_database() as session:
        rows = list(
            session.scalars(
                select(RankingTrainingSample)
                .where(RankingTrainingSample.mode == "short")
                .order_by(RankingTrainingSample.candidate_rank)
            )
        )
    assert [(row.candidate_rank, row.code) for row in rows] == [
        (1, "000001"),
        (2, "000002"),
    ]

def test_verified_trade_date_samples_survive_cleanup(isolated_database):
    items = [opportunity("000001")]
    items[0]["meta"]["quote_time"] = None
    items[0]["meta"]["trade_date"] = "2026-07-30"
    opportunities = {"short": items, "swing": []}
    meta = {
        "quote_time": None,
        "trade_date": "2026-07-30",
        "fetched_at": "2026-07-30T15:01:00",
        "source": "测试源",
    }

    result = service.process_training_cycle(opportunities, [], meta)

    assert result["skipped"] is False
    assert service.repair_unverified_training_samples() == 0
    with isolated_database() as session:
        samples = list(session.scalars(select(RankingTrainingSample)))
    assert len(samples) == 1
    assert "交易日历确认" in samples[0].source
