from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import ranking_optimizer_service as service
from app.database import (
    Base,
    RankingOptimizationRun,
    RankingStrategyVersion,
    RankingTrainingSample,
)


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

def test_sample_threshold_retries_waiting_run_without_day_gate(isolated_database):
    service.ensure_baseline_versions()
    run_date = "2026-08-24"
    with isolated_database.begin() as session:
        waiting = service._optimize_mode(session, "short", run_date)
    assert waiting["status"] == "waiting"

    start = datetime(2026, 8, 1)
    with isolated_database.begin() as session:
        for day in range(11):
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
                        name="样本门槛测试",
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
        result = service._optimize_mode(session, "short", run_date)

    assert result["status"] in {"activated", "rejected"}
    assert result["candidate_version"] == "short-v1.1"


def test_fit_parameters_records_multi_outcome_objective():
    samples = []
    for index, positive in enumerate((False, True, False, True), start=1):
        features = {name: index / 4 for name in service.FEATURE_NAMES}
        samples.append(
            RankingTrainingSample(
                features_json=json.dumps(features),
                label_return_pct=4 if positive else -3,
                label_max_drawdown_pct=-1 if positive else -6,
                label_positive=positive,
            )
        )

    parameters = service._fit_parameters(samples)

    assert parameters["model"] == "multi_factor_contextual_return_success_ridge_v4"
    assert parameters["objective"] == {
        "future_return_weight": 1.0,
        "max_drawdown_weight": 0.10,
        "direction_weight": 1.50,
        "recency_weighted": True,
    }
    assert parameters["feature_names"] == list(service.FEATURE_NAMES)

def test_new_threshold_policy_accepts_return_and_success_improvement():
    assert service._passes_validation_thresholds(0.5, -10.0, 0.0)
    assert not service._passes_validation_thresholds(0.49, -1.0, 5.0)
    assert not service._passes_validation_thresholds(1.0, -10.01, 5.0)
    assert not service._passes_validation_thresholds(1.0, -1.0, -0.01)


def test_rejected_candidate_is_rechecked_under_new_policy(isolated_database):
    service.ensure_baseline_versions()
    with isolated_database.begin() as session:
        session.add(
            RankingStrategyVersion(
                version="short-v1.1",
                mode="short",
                parameters_json=json.dumps(service.BASELINE_PARAMETERS),
                trained_through="2026-08-11",
                train_samples=180,
                validation_samples=60,
                validation_mean_return=1.0,
                validation_mean_drawdown=-5.0,
                validation_positive_rate=60.0,
                status="rejected",
                is_active=False,
                notes="旧门槛未通过",
                created_at=datetime.now(),
            )
        )
        session.add(
            RankingOptimizationRun(
                mode="short",
                run_date="2026-08-25",
                incumbent_version="short-v1.0",
                candidate_version="short-v1.1",
                sample_count=240,
                trading_days=12,
                metrics_json=json.dumps({
                    "return_improvement": 0.55,
                    "drawdown_change": -1.68,
                    "positive_rate_change": 11.11,
                }),
                status="rejected",
                accepted=False,
                reason="旧门槛未通过",
                completed_at=datetime.now(),
            )
        )

    with isolated_database.begin() as session:
        result = service._optimize_mode(session, "short", "2026-08-25")

    assert result["status"] == "activated"
    with isolated_database() as session:
        candidate = session.get(RankingStrategyVersion, "short-v1.1")
    assert candidate is not None
    assert candidate.is_active is True


def test_version_detail_returns_actual_selected_results(isolated_database, monkeypatch):
    monkeypatch.setitem(service.MODE_RULES["short"], "required_samples", 8)
    service.ensure_baseline_versions()
    start = datetime(2026, 8, 1)
    with isolated_database.begin() as session:
        for day in range(4):
            sample_date = (start + timedelta(days=day)).date().isoformat()
            for rank in range(1, 3):
                positive = rank == 2
                features = {name: rank / 2 for name in service.FEATURE_NAMES}
                session.add(
                    RankingTrainingSample(
                        sample_date=sample_date,
                        mode="short",
                        code=f"{day:02d}{rank:04d}",
                        name="版本详情样本",
                        candidate_rank=rank,
                        discovery_price=10,
                        base_score=90 - rank,
                        strategy_score=90 - rank,
                        strategy_version="short-v1.0",
                        features_json=json.dumps(features),
                        target_observations=5,
                        matured=True,
                        label_return_pct=4 if positive else -3,
                        label_max_drawdown_pct=-1 if positive else -5,
                        label_positive=positive,
                        matured_at=datetime.now(),
                        quote_time=f"{sample_date} 15:00:00",
                        source="测试源",
                        created_at=datetime.now(),
                    )
                )
    with isolated_database.begin() as session:
        result = service._optimize_mode(session, "short", "2026-08-25")

    detail = service.ranking_strategy_version_detail("short", result["candidate_version"])

    assert detail["version"] == result["candidate_version"]
    assert len(detail["actual_results"]) == 8
    assert {item["split"] for item in detail["actual_results"]} == {"train", "validation"}
    assert all("labels" in item for item in detail["actual_results"])

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


def test_status_exposes_pending_observation_progress(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setitem(service.MODE_RULES["short"], "horizon", 2)
    monkeypatch.setitem(service.MODE_RULES["swing"], "horizon", 2)
    opportunities = {
        "short": [opportunity("000001")],
        "swing": [opportunity("600001")],
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
    service.process_training_cycle(
        opportunities,
        [{"code": "000001", "price": 11}, {"code": "600001", "price": 11}],
        second_meta,
    )

    status = service.ranking_strategy_status()
    assert status["short"]["matured_samples"] == 0
    assert status["swing"]["matured_samples"] == 0
    assert status["swing"]["pending_samples"] == 2
    assert status["swing"]["observed_pending_samples"] == 1
    assert status["swing"]["max_observations"] == 1
    assert status["swing"]["observation_progress_pct"] == 50.0


def test_contextual_features_include_news_sector_and_peer_strength():
    items = [
        {
            **opportunity("000001", 90),
            "industry": "软件",
            "change_pct": 6,
            "news_sentiment_score": 80,
            "news_sample_count": 3,
        },
        {
            **opportunity("000002", 70),
            "industry": "软件",
            "change_pct": -2,
        },
    ]

    service._enrich_contextual_features(items)
    strong = service.feature_snapshot(items[0])
    weak = service.feature_snapshot(items[1])

    assert strong["news_sentiment"] == 0.8
    assert strong["news_coverage"] == 1.0
    assert weak["news_sentiment"] == 0.5
    assert strong["industry_strength"] == weak["industry_strength"]
    assert strong["peer_relative_strength"] > weak["peer_relative_strength"]


def test_baseline_version_detail_summarizes_real_swing_tracking_samples(
    isolated_database,
):
    service.ensure_baseline_versions()
    with isolated_database.begin() as session:
        mature = RankingTrainingSample(
            sample_date="2026-08-01",
            mode="swing",
            code="600001",
            name="成熟样本",
            candidate_rank=1,
            discovery_price=10,
            base_score=82,
            strategy_score=83,
            strategy_version="swing-v1.0",
            features_json=json.dumps({name: 0.5 for name in service.FEATURE_NAMES}),
            target_observations=15,
            matured=True,
            label_return_pct=8,
            label_max_drawdown_pct=-3,
            label_positive=True,
            matured_at=datetime.now(),
            quote_time="2026-08-01 15:00:00",
            source="测试源",
            created_at=datetime.now(),
        )
        tracking = RankingTrainingSample(
            sample_date="2026-08-20",
            mode="swing",
            code="600002",
            name="跟踪样本",
            candidate_rank=2,
            discovery_price=10,
            base_score=78,
            strategy_score=79,
            strategy_version="swing-v1.0",
            features_json=json.dumps({name: 0.5 for name in service.FEATURE_NAMES}),
            target_observations=15,
            matured=False,
            quote_time="2026-08-20 15:00:00",
            source="测试源",
            created_at=datetime.now(),
        )
        session.add_all([mature, tracking])
        session.flush()
        session.add_all(
            [
                service.RankingTrainingObservation(
                    sample_id=mature.id,
                    observation_date="2026-08-22",
                    price=10.8,
                    return_pct=8,
                    quote_time="2026-08-22 15:00:00",
                    created_at=datetime.now(),
                ),
                service.RankingTrainingObservation(
                    sample_id=tracking.id,
                    observation_date="2026-08-22",
                    price=10.4,
                    return_pct=4,
                    quote_time="2026-08-22 15:00:00",
                    created_at=datetime.now(),
                ),
            ]
        )

    detail = service.ranking_strategy_version_detail("swing", "swing-v1.0")

    assert detail["run"] is None
    assert detail["sample_summary"]["data_status"] == "provisional"
    assert detail["sample_summary"]["available_samples"] == 2
    assert detail["sample_summary"]["matured_samples"] == 1
    assert detail["sample_summary"]["pending_samples"] == 1
    assert detail["sample_summary"]["mean_return"] == 8
    assert detail["sample_summary"]["tracking_mean_return"] == 6
    assert len(detail["actual_results"]) == 2
    assert {row["split"] for row in detail["actual_results"]} == {"matured", "tracking"}
    assert next(row for row in detail["actual_results"] if row["code"] == "600002")[
        "current_return_pct"
    ] == 4
