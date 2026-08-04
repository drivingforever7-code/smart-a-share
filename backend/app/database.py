from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), index=True)
    market: Mapped[str] = mapped_column(String(8), default="")
    board: Mapped[str] = mapped_column(String(16), default="")
    industry: Mapped[str | None] = mapped_column(String(60), nullable=True)
    list_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_st: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="正常")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Quote(Base):
    __tablename__ = "quotes"

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), default="")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    amplitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_ytd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    quote_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(30), default="AKShare")


class Bar(Base):
    __tablename__ = "bars"
    __table_args__ = (UniqueConstraint("code", "timeframe", "time", name="uq_bar"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    timeframe: Mapped[str] = mapped_column(String(10), index=True)
    time: Mapped[str] = mapped_column(String(24), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[str] = mapped_column(String(30), default="AKShare")


class ScoreSnapshot(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)
    score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(30))
    dimensions_json: Mapped[str] = mapped_column(Text)
    reasons_json: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    version: Mapped[str] = mapped_column(String(20), default="v1")


class RankingDiscovery(Base):
    __tablename__ = "ranking_discoveries"
    __table_args__ = (
        UniqueConstraint(
            "discovery_date",
            "mode",
            "rank",
            name="uq_ranking_discovery",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discovery_date: Mapped[str] = mapped_column(String(10), index=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(40))
    industry: Mapped[str | None] = mapped_column(String(60), nullable=True)
    discovery_price: Mapped[float] = mapped_column(Float)
    discovery_score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    quote_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingAdviceSnapshot(Base):
    __tablename__ = "ranking_advice_snapshots"
    __table_args__ = (
        UniqueConstraint("discovery_id", "advice_date", name="uq_ranking_daily_advice"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discovery_id: Mapped[int] = mapped_column(
        ForeignKey("ranking_discoveries.id"), index=True
    )
    advice_date: Mapped[str] = mapped_column(String(10), index=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_recommendation: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    position_pct: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    reasons_json: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    invalidation: Mapped[str] = mapped_column(Text)
    quote_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(30), default="daily-position-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LimitBreakEvent(Base):
    __tablename__ = "limit_break_events"
    __table_args__ = (
        UniqueConstraint(
            "trade_date", "code", "prediction_stage", name="uq_limit_break_observation"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(40))
    industry: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prediction_stage: Mapped[str] = mapped_column(String(20), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    first_limit_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    last_limit_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    price: Mapped[float] = mapped_column(Float)
    limit_price: Mapped[float] = mapped_column(Float)
    change_pct: Mapped[float] = mapped_column(Float)
    distance_to_limit_pct: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)
    circulating_market_cap: Mapped[float] = mapped_column(Float)
    turnover_rate: Mapped[float] = mapped_column(Float)
    amplitude: Mapped[float] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    break_count: Mapped[int] = mapped_column(Integer)
    limit_statistics: Mapped[str] = mapped_column(String(20))
    streak_count: Mapped[int] = mapped_column(Integer, default=0)
    market_seal_rate: Mapped[float] = mapped_column(Float)
    industry_heat: Mapped[int] = mapped_column(Integer)
    features_json: Mapped[str] = mapped_column(Text)
    predicted_probability: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(30))
    position_pct: Mapped[int] = mapped_column(Integer, default=0)
    reasons_json: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    invalidation: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(50), index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligible_for_evaluation: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(60))


class LimitBreakModelVersion(Base):
    __tablename__ = "limit_break_model_versions"

    version: Mapped[str] = mapped_column(String(50), primary_key=True)
    model_type: Mapped[str] = mapped_column(String(30))
    parameters_json: Mapped[str] = mapped_column(Text)
    trained_through: Mapped[str] = mapped_column(String(10), index=True)
    train_samples: Mapped[int] = mapped_column(Integer)
    validation_samples: Mapped[int] = mapped_column(Integer)
    validation_brier: Mapped[float] = mapped_column(Float)
    validation_accuracy: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingStrategyVersion(Base):
    __tablename__ = "ranking_strategy_versions"

    version: Mapped[str] = mapped_column(String(30), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)
    parameters_json: Mapped[str] = mapped_column(Text)
    trained_through: Mapped[str | None] = mapped_column(String(10), nullable=True)
    train_samples: Mapped[int] = mapped_column(Integer, default=0)
    validation_samples: Mapped[int] = mapped_column(Integer, default=0)
    validation_mean_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_mean_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingTrainingSample(Base):
    __tablename__ = "ranking_training_samples"
    __table_args__ = (
        UniqueConstraint("sample_date", "mode", "code", name="uq_ranking_training_sample"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_date: Mapped[str] = mapped_column(String(10), index=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(40))
    candidate_rank: Mapped[int] = mapped_column(Integer)
    discovery_price: Mapped[float] = mapped_column(Float)
    base_score: Mapped[float] = mapped_column(Float)
    strategy_score: Mapped[float] = mapped_column(Float)
    strategy_version: Mapped[str] = mapped_column(String(30), index=True)
    features_json: Mapped[str] = mapped_column(Text)
    target_observations: Mapped[int] = mapped_column(Integer)
    matured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    label_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    label_max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    label_positive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    matured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quote_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingTrainingObservation(Base):
    __tablename__ = "ranking_training_observations"
    __table_args__ = (
        UniqueConstraint("sample_id", "observation_date", name="uq_ranking_training_observation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[int] = mapped_column(
        ForeignKey("ranking_training_samples.id"), index=True
    )
    observation_date: Mapped[str] = mapped_column(String(10), index=True)
    price: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    quote_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingOptimizationRun(Base):
    __tablename__ = "ranking_optimization_runs"
    __table_args__ = (
        UniqueConstraint("mode", "run_date", name="uq_ranking_optimization_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)
    run_date: Mapped[str] = mapped_column(String(10), index=True)
    incumbent_version: Mapped[str] = mapped_column(String(30))
    candidate_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer)
    trading_days: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RankingOptimizationAudit(Base):
    __tablename__ = "ranking_optimization_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ranking_optimization_runs.id"), index=True
    )
    mode: Mapped[str] = mapped_column(String(10), index=True)
    sample_date: Mapped[str] = mapped_column(String(10), index=True)
    split: Mapped[str] = mapped_column(String(12), index=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(40))
    features_json: Mapped[str] = mapped_column(Text)
    observations_json: Mapped[str] = mapped_column(Text)
    labels_json: Mapped[str] = mapped_column(Text)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BoardPoolEvent(Base):
    __tablename__ = "board_pool_events"
    __table_args__ = (
        UniqueConstraint("trade_date", "pool_type", "code", name="uq_board_pool_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    pool_type: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(40))
    industry: Mapped[str | None] = mapped_column(String(60), nullable=True)
    rank: Mapped[int] = mapped_column(Integer)
    predicted_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    predicted_probability: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(30))
    reasons_json: Mapped[str] = mapped_column(Text)
    risks_json: Mapped[str] = mapped_column(Text)
    features_json: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(40), index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    outcome_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(60), default="AKShare")


class BoardPoolModelVersion(Base):
    __tablename__ = "board_pool_model_versions"

    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    pool_type: Mapped[str] = mapped_column(String(16), index=True)
    parameters_json: Mapped[str] = mapped_column(Text)
    trained_through: Mapped[str] = mapped_column(String(10), index=True)
    train_samples: Mapped[int] = mapped_column(Integer, default=0)
    validation_samples: Mapped[int] = mapped_column(Integer, default=0)
    validation_brier: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DataUpdateJob(Base):
    __tablename__ = "data_update_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
