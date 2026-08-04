from __future__ import annotations

import json
import math
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import delete, desc, or_, select

from .database import (
    RankingOptimizationAudit,
    RankingOptimizationRun,
    RankingStrategyVersion,
    RankingTrainingObservation,
    RankingTrainingSample,
    SessionLocal,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
MODES = ("short", "swing")
FEATURE_NAMES = (
    "base_score",
    "confidence",
    "short_score",
    "swing_score",
    "price_change",
    "turnover_quality",
    "volume_ratio_quality",
    "liquidity",
    "valuation_quality",
    "risk_quality",
)
MODE_RULES = {
    "short": {
        "horizon": 5,
        "required_samples": 200,
        "required_days": 20,
    },
    "swing": {
        "horizon": 15,
        "required_samples": 300,
        "required_days": 30,
    },
}
BASELINE_PARAMETERS = {
    "intercept": 0.0,
    "weights": {name: 0.0 for name in FEATURE_NAMES},
    "adjustment_scale": 1.5,
    "max_adjustment": 8.0,
}

_version_cache_lock = threading.Lock()
_version_cache: dict[str, tuple[float, str, dict[str, Any]]] = {}


def _now() -> datetime:
    return datetime.now(SHANGHAI).replace(tzinfo=None)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def _trade_date(meta: dict[str, Any]) -> date:
    value = str(meta.get("trade_date") or meta.get("quote_time") or "").strip()
    if len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    raise ValueError("行情缺少真实行情时间，不能留存训练样本")


def repair_unverified_training_samples() -> int:
    """移除旧逻辑用抓取时间生成、但没有真实行情时间的未成熟样本。"""
    removed = 0
    with SessionLocal.begin() as session:
        invalid = list(
            session.scalars(
                select(RankingTrainingSample).where(
                    RankingTrainingSample.matured.is_(False),
                    or_(
                        RankingTrainingSample.quote_time.is_(None),
                        RankingTrainingSample.quote_time == "",
                    ),
                    RankingTrainingSample.source.not_like("%交易日历确认%"),
                )
            )
        )
        if not invalid:
            return 0
        ids = [item.id for item in invalid]
        affected = {(item.mode, item.sample_date) for item in invalid}
        session.execute(
            delete(RankingTrainingObservation).where(
                RankingTrainingObservation.sample_id.in_(ids)
            )
        )
        session.execute(
            delete(RankingTrainingSample).where(RankingTrainingSample.id.in_(ids))
        )
        for mode, sample_date in affected:
            session.execute(
                delete(RankingOptimizationRun).where(
                    RankingOptimizationRun.mode == mode,
                    RankingOptimizationRun.run_date == sample_date,
                    RankingOptimizationRun.status == "waiting",
                )
            )
        removed = len(ids)
    return removed


def _baseline_version(mode: str) -> str:
    return f"{mode}-v1.0"


def ensure_baseline_versions() -> None:
    with SessionLocal.begin() as session:
        for mode in MODES:
            exists = session.scalar(
                select(RankingStrategyVersion.version).where(
                    RankingStrategyVersion.mode == mode,
                    RankingStrategyVersion.is_active.is_(True),
                )
            )
            if exists is None:
                session.add(
                    RankingStrategyVersion(
                        version=_baseline_version(mode),
                        mode=mode,
                        parameters_json=json.dumps(BASELINE_PARAMETERS, ensure_ascii=False),
                        trained_through=None,
                        train_samples=0,
                        validation_samples=0,
                        validation_mean_return=None,
                        validation_mean_drawdown=None,
                        validation_positive_rate=None,
                        status="active",
                        is_active=True,
                        activated_at=_now(),
                        notes="初始确定性评分版本，不包含自动学习修正。",
                        created_at=_now(),
                    )
                )
    invalidate_version_cache()


def invalidate_version_cache() -> None:
    with _version_cache_lock:
        _version_cache.clear()


def _active_version(mode: str) -> tuple[str, dict[str, Any]]:
    now_monotonic = time.monotonic()
    with _version_cache_lock:
        cached = _version_cache.get(mode)
        if cached and now_monotonic - cached[0] < 30:
            return cached[1], cached[2]
    with SessionLocal() as session:
        row = session.scalar(
            select(RankingStrategyVersion)
            .where(
                RankingStrategyVersion.mode == mode,
                RankingStrategyVersion.is_active.is_(True),
            )
            .order_by(desc(RankingStrategyVersion.created_at))
        )
    if row is None:
        ensure_baseline_versions()
        return _active_version(mode)
    parameters = json.loads(row.parameters_json)
    with _version_cache_lock:
        _version_cache[mode] = (now_monotonic, row.version, parameters)
    return row.version, parameters


def feature_snapshot(item: dict[str, Any]) -> dict[str, float]:
    turnover = _number(item.get("turnover_rate"))
    volume_ratio = _number(item.get("volume_ratio"))
    amount = max(_number(item.get("amount")), 1.0)
    pe = _number(item.get("pe"))
    pb = _number(item.get("pb"))
    valuation_parts = []
    if pe > 0:
        valuation_parts.append(1 - _clamp(abs(pe - 22) / 55))
    if pb > 0:
        valuation_parts.append(1 - _clamp(abs(pb - 2.5) / 7))
    valuation = sum(valuation_parts) / len(valuation_parts) if valuation_parts else 0.5
    return {
        "base_score": round(_clamp(_number(item.get("base_score", item.get("score"))) / 100), 6),
        "confidence": round(_clamp(_number(item.get("confidence")) / 100), 6),
        "short_score": round(_clamp(_number(item.get("short_score")) / 100), 6),
        "swing_score": round(_clamp(_number(item.get("swing_score")) / 100), 6),
        "price_change": round(_clamp(_number(item.get("change_pct")) / 20, -1, 1), 6),
        "turnover_quality": round(1 - _clamp(abs(turnover - 8) / 22), 6),
        "volume_ratio_quality": round(1 - _clamp(abs(volume_ratio - 1.5) / 2.5), 6),
        "liquidity": round(_clamp((math.log10(amount) - 7) / 3), 6),
        "valuation_quality": round(valuation, 6),
        "risk_quality": round(1 - _clamp(len(item.get("risks") or []) / 4), 6),
    }


def _expected_return(features: dict[str, float], parameters: dict[str, Any]) -> float:
    value = _number(parameters.get("intercept"))
    weights = parameters.get("weights") or {}
    value += sum(
        _number(weights.get(name)) * features.get(name, 0.0)
        for name in FEATURE_NAMES
    )
    return value


def _score_with_parameters(
    item: dict[str, Any],
    parameters: dict[str, Any],
) -> tuple[float, float]:
    base_score = _number(item.get("base_score", item.get("score")))
    expected = _expected_return(feature_snapshot(item), parameters)
    adjustment = _clamp(
        expected * _number(parameters.get("adjustment_scale"), 1.5),
        -_number(parameters.get("max_adjustment"), 8.0),
        _number(parameters.get("max_adjustment"), 8.0),
    )
    return round(_clamp(base_score + adjustment, 0, 100), 1), round(adjustment, 2)


def _recommendation(score: float, original: str) -> str:
    if original == "建议回避":
        return original
    if score >= 80:
        return "建议买入"
    if score >= 70:
        return "建议小仓位试买"
    if score >= 60:
        return "建议观察"
    return "暂不建议"


def apply_active_version(mode: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    version, parameters = _active_version(mode)
    result = []
    for source in items:
        item = dict(source)
        item["base_score"] = _number(source.get("base_score", source.get("score")))
        score, adjustment = _score_with_parameters(item, parameters)
        item["score"] = score
        item["recommendation"] = _recommendation(
            score, str(source.get("recommendation") or "建议观察")
        )
        item["strategy_version"] = version
        item["strategy_adjustment"] = adjustment
        result.append(item)
    return result


def _sample_item(sample: RankingTrainingSample) -> dict[str, Any]:
    features = json.loads(sample.features_json)
    return {
        "score": sample.base_score,
        "base_score": sample.base_score,
        "confidence": features.get("confidence", 0) * 100,
        "short_score": features.get("short_score", 0) * 100,
        "swing_score": features.get("swing_score", 0) * 100,
        "change_pct": features.get("price_change", 0) * 20,
        "turnover_rate": 8,
        "volume_ratio": 1.5,
        "amount": 1e9,
        "pe": 22,
        "pb": 2.5,
        "risks": [],
        "_stored_features": features,
    }


def _candidate_score(sample: RankingTrainingSample, parameters: dict[str, Any]) -> float:
    features = json.loads(sample.features_json)
    expected = _number(parameters.get("intercept")) + sum(
        _number((parameters.get("weights") or {}).get(name)) * features.get(name, 0.0)
        for name in FEATURE_NAMES
    )
    adjustment = _clamp(
        expected * _number(parameters.get("adjustment_scale"), 1.5),
        -_number(parameters.get("max_adjustment"), 8.0),
        _number(parameters.get("max_adjustment"), 8.0),
    )
    return sample.base_score + adjustment


def _next_version(session, mode: str) -> str:
    highest_major = 1
    highest_minor = 0
    versions = list(
        session.scalars(
            select(RankingStrategyVersion.version).where(
                RankingStrategyVersion.mode == mode
            )
        )
    )
    for version in versions:
        try:
            major_minor = version.split("-v", 1)[1]
            major, minor = (int(part) for part in major_minor.split(".", 1))
        except (IndexError, ValueError):
            continue
        if (major, minor) > (highest_major, highest_minor):
            highest_major, highest_minor = major, minor
    return f"{mode}-v{highest_major}.{highest_minor + 1}"


def _metrics(groups: dict[str, list[RankingTrainingSample]], selector) -> dict[str, float]:
    selected: list[RankingTrainingSample] = []
    daily_returns: list[float] = []
    for samples in groups.values():
        chosen = selector(samples)[:3]
        selected.extend(chosen)
        if chosen:
            daily_returns.append(
                sum(_number(item.label_return_pct) for item in chosen) / len(chosen)
            )
    if not selected:
        return {"mean_return": 0.0, "mean_drawdown": 0.0, "positive_rate": 0.0, "positive_days": 0.0}
    return {
        "mean_return": round(
            sum(_number(item.label_return_pct) for item in selected) / len(selected), 4
        ),
        "mean_drawdown": round(
            sum(_number(item.label_max_drawdown_pct) for item in selected) / len(selected), 4
        ),
        "positive_rate": round(
            sum(_number(item.label_return_pct) > 0 for item in selected) / len(selected) * 100,
            4,
        ),
        "positive_days": round(
            sum(value > 0 for value in daily_returns) / len(daily_returns) * 100,
            4,
        ) if daily_returns else 0.0,
    }


def _fit_parameters(samples: list[RankingTrainingSample]) -> dict[str, Any]:
    x = np.array(
        [
            [1.0, *[json.loads(sample.features_json).get(name, 0.0) for name in FEATURE_NAMES]]
            for sample in samples
        ],
        dtype=float,
    )
    y = np.clip(
        np.array([_number(sample.label_return_pct) for sample in samples], dtype=float),
        -20,
        20,
    )
    regularizer = np.eye(x.shape[1]) * 0.35
    regularizer[0, 0] = 0.05
    coefficients = np.linalg.pinv(x.T @ x + regularizer) @ x.T @ y
    coefficients = np.clip(coefficients, -15, 15)
    return {
        "intercept": round(float(coefficients[0]), 8),
        "weights": {
            name: round(float(value), 8)
            for name, value in zip(FEATURE_NAMES, coefficients[1:], strict=True)
        },
        "adjustment_scale": 1.5,
        "max_adjustment": 8.0,
    }


def _optimize_mode(session, mode: str, run_date: str) -> dict[str, Any]:
    existing = session.scalar(
        select(RankingOptimizationRun).where(
            RankingOptimizationRun.mode == mode,
            RankingOptimizationRun.run_date == run_date,
        )
    )
    if existing is not None:
        return {"mode": mode, "status": existing.status}

    rules = MODE_RULES[mode]
    matured = list(
        session.scalars(
            select(RankingTrainingSample)
            .where(
                RankingTrainingSample.mode == mode,
                RankingTrainingSample.matured.is_(True),
            )
            .order_by(RankingTrainingSample.sample_date, RankingTrainingSample.candidate_rank)
        )
    )
    dates = sorted({item.sample_date for item in matured})
    active = session.scalar(
        select(RankingStrategyVersion)
        .where(
            RankingStrategyVersion.mode == mode,
            RankingStrategyVersion.is_active.is_(True),
        )
        .order_by(desc(RankingStrategyVersion.created_at))
    )
    active_version = active.version if active else _baseline_version(mode)

    if len(matured) < rules["required_samples"] or len(dates) < rules["required_days"]:
        reason = (
            f"成熟样本 {len(matured)}/{rules['required_samples']}，"
            f"交易日 {len(dates)}/{rules['required_days']}，继续积累。"
        )
        session.add(
            RankingOptimizationRun(
                mode=mode,
                run_date=run_date,
                incumbent_version=active_version,
                candidate_version=None,
                sample_count=len(matured),
                trading_days=len(dates),
                metrics_json=json.dumps({}, ensure_ascii=False),
                status="waiting",
                accepted=False,
                reason=reason,
                completed_at=_now(),
            )
        )
        return {"mode": mode, "status": "waiting", "reason": reason}

    split_index = max(1, int(len(dates) * 0.75))
    train_dates = set(dates[:split_index])
    validation_dates = set(dates[split_index:])
    train = [item for item in matured if item.sample_date in train_dates]
    validation = [item for item in matured if item.sample_date in validation_dates]
    if len(validation_dates) < 5 or len(validation) < 60:
        reason = f"时间后段验证集只有 {len(validation_dates)} 日、{len(validation)} 个样本，尚不足 5 日和 60 样本。"
        session.add(
            RankingOptimizationRun(
                mode=mode,
                run_date=run_date,
                incumbent_version=active_version,
                candidate_version=None,
                sample_count=len(matured),
                trading_days=len(dates),
                metrics_json=json.dumps({}, ensure_ascii=False),
                status="waiting",
                accepted=False,
                reason=reason,
                completed_at=_now(),
            )
        )
        return {"mode": mode, "status": "waiting", "reason": reason}

    parameters = _fit_parameters(train)
    groups: dict[str, list[RankingTrainingSample]] = defaultdict(list)
    for item in validation:
        groups[item.sample_date].append(item)
    incumbent_metrics = _metrics(
        groups,
        lambda samples: sorted(samples, key=lambda item: item.candidate_rank),
    )
    candidate_metrics = _metrics(
        groups,
        lambda samples: sorted(
            samples,
            key=lambda item: _candidate_score(item, parameters),
            reverse=True,
        ),
    )
    return_improvement = (
        candidate_metrics["mean_return"] - incumbent_metrics["mean_return"]
    )
    drawdown_change = (
        candidate_metrics["mean_drawdown"] - incumbent_metrics["mean_drawdown"]
    )
    positive_rate_change = (
        candidate_metrics["positive_rate"] - incumbent_metrics["positive_rate"]
    )
    accepted = (
        return_improvement >= 0.5
        and drawdown_change >= -1.0
        and positive_rate_change >= -3.0
    )
    candidate_version = _next_version(session, mode)
    reason = (
        f"验证前三平均收益变化 {return_improvement:+.2f}pct，"
        f"平均最大回撤变化 {drawdown_change:+.2f}pct，"
        f"上涨比例变化 {positive_rate_change:+.2f}pct。"
    )
    if accepted:
        for version in session.scalars(
            select(RankingStrategyVersion).where(
                RankingStrategyVersion.mode == mode,
                RankingStrategyVersion.is_active.is_(True),
            )
        ):
            version.is_active = False
            version.status = "superseded"
    session.add(
        RankingStrategyVersion(
            version=candidate_version,
            mode=mode,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            trained_through=max(train_dates),
            train_samples=len(train),
            validation_samples=len(validation),
            validation_mean_return=candidate_metrics["mean_return"],
            validation_mean_drawdown=candidate_metrics["mean_drawdown"],
            validation_positive_rate=candidate_metrics["positive_rate"],
            status="active" if accepted else "rejected",
            is_active=accepted,
            activated_at=_now() if accepted else None,
            notes=reason,
            created_at=_now(),
        )
    )
    optimization_run = RankingOptimizationRun(
            mode=mode,
            run_date=run_date,
            incumbent_version=active_version,
            candidate_version=candidate_version,
            sample_count=len(matured),
            trading_days=len(dates),
            metrics_json=json.dumps(
                {
                    "incumbent": incumbent_metrics,
                    "candidate": candidate_metrics,
                    "return_improvement": round(return_improvement, 4),
                    "drawdown_change": round(drawdown_change, 4),
                    "positive_rate_change": round(positive_rate_change, 4),
                },
                ensure_ascii=False,
            ),
            status="activated" if accepted else "rejected",
            accepted=accepted,
            reason=reason,
            completed_at=_now(),
        )
    session.add(optimization_run)
    session.flush()
    for sample in matured:
        observations = list(session.scalars(
            select(RankingTrainingObservation)
            .where(RankingTrainingObservation.sample_id == sample.id)
            .order_by(RankingTrainingObservation.observation_date)
        ))
        session.add(RankingOptimizationAudit(
            run_id=optimization_run.id,
            mode=mode,
            sample_date=sample.sample_date,
            split="train" if sample in train else "validation",
            code=sample.code,
            name=sample.name,
            features_json=sample.features_json,
            observations_json=json.dumps([
                {"date": row.observation_date, "price": row.price, "return_pct": row.return_pct}
                for row in observations
            ], ensure_ascii=False),
            labels_json=json.dumps({
                "return_pct": sample.label_return_pct,
                "max_drawdown_pct": sample.label_max_drawdown_pct,
                "positive": sample.label_positive,
            }, ensure_ascii=False),
            candidate_score=_candidate_score(sample, parameters),
        ))
    if accepted:
        invalidate_version_cache()
    return {
        "mode": mode,
        "status": "activated" if accepted else "rejected",
        "candidate_version": candidate_version,
        "reason": reason,
    }


def process_training_cycle(
    opportunities: dict[str, list[dict[str, Any]]],
    quotes: list[dict[str, Any]],
    meta: dict[str, Any],
) -> dict[str, Any]:
    ensure_baseline_versions()
    repaired_samples = repair_unverified_training_samples()
    try:
        current_date = _trade_date(meta)
    except ValueError as exc:
        return {
            "trade_date": None,
            "created_samples": 0,
            "created_observations": 0,
            "repaired_samples": repaired_samples,
            "skipped": True,
            "reason": str(exc),
            "optimization": {},
        }
    current_date_text = current_date.isoformat()
    quote_map = {str(item.get("code")): item for item in quotes}
    created_samples = 0
    created_observations = 0

    with SessionLocal.begin() as session:
        for mode in MODES:
            already_saved = session.scalar(
                select(RankingTrainingSample.id).where(
                    RankingTrainingSample.sample_date == current_date_text,
                    RankingTrainingSample.mode == mode,
                )
            )
            if already_saved is None:
                unique_items: list[dict[str, Any]] = []
                seen_codes: set[str] = set()
                for item in opportunities.get(mode, []):
                    code = str(item.get("code") or "")
                    if not code or code in seen_codes:
                        continue
                    seen_codes.add(code)
                    unique_items.append(item)
                    if len(unique_items) >= 20:
                        break
                for rank, item in enumerate(unique_items, start=1):
                    price = _number(item.get("price"))
                    if price <= 0:
                        continue
                    features = feature_snapshot(item)
                    session.add(
                        RankingTrainingSample(
                            sample_date=current_date_text,
                            mode=mode,
                            code=str(item["code"]),
                            name=str(item["name"]),
                            candidate_rank=rank,
                            discovery_price=price,
                            base_score=_number(item.get("base_score", item.get("score"))),
                            strategy_score=_number(item.get("score")),
                            strategy_version=str(
                                item.get("strategy_version") or _baseline_version(mode)
                            ),
                            features_json=json.dumps(features, ensure_ascii=False),
                            target_observations=MODE_RULES[mode]["horizon"],
                            matured=False,
                            quote_time=(item.get("meta") or {}).get("quote_time"),
                            source=(
                                f"{str((item.get('meta') or {}).get('source') or '未知')}；交易日历确认"
                                if (item.get("meta") or {}).get("trade_date")
                                and not (item.get("meta") or {}).get("quote_time")
                                else str((item.get("meta") or {}).get("source") or "未知")
                            ),
                            created_at=_now(),
                        )
                    )
                    created_samples += 1
        session.flush()

        pending = list(
            session.scalars(
                select(RankingTrainingSample).where(
                    RankingTrainingSample.matured.is_(False),
                    RankingTrainingSample.sample_date < current_date_text,
                )
            )
        )
        for sample in pending:
            quote = quote_map.get(sample.code)
            price = _number(quote.get("price")) if quote else 0
            if price <= 0:
                continue
            exists = session.scalar(
                select(RankingTrainingObservation.id).where(
                    RankingTrainingObservation.sample_id == sample.id,
                    RankingTrainingObservation.observation_date == current_date_text,
                )
            )
            if exists is None:
                session.add(
                    RankingTrainingObservation(
                        sample_id=sample.id,
                        observation_date=current_date_text,
                        price=price,
                        return_pct=round((price / sample.discovery_price - 1) * 100, 4),
                        quote_time=str(meta.get("quote_time") or ""),
                        created_at=_now(),
                    )
                )
                created_observations += 1
        session.flush()

        for sample in pending:
            observations = list(
                session.scalars(
                    select(RankingTrainingObservation)
                    .where(RankingTrainingObservation.sample_id == sample.id)
                    .order_by(RankingTrainingObservation.observation_date)
                )
            )
            if len(observations) >= sample.target_observations:
                horizon = observations[: sample.target_observations]
                final = horizon[-1]
                sample.matured = True
                sample.label_return_pct = final.return_pct
                sample.label_max_drawdown_pct = min(
                    [0.0, *[item.return_pct for item in horizon]]
                )
                sample.label_positive = final.return_pct > 0
                sample.matured_at = _now()

        results = {
            mode: _optimize_mode(session, mode, current_date_text)
            for mode in MODES
        }

    return {
        "trade_date": current_date_text,
        "created_samples": created_samples,
        "created_observations": created_observations,
        "repaired_samples": repaired_samples,
        "skipped": False,
        "optimization": results,
    }


def ranking_strategy_status() -> dict[str, Any]:
    ensure_baseline_versions()
    result: dict[str, Any] = {}
    with SessionLocal() as session:
        for mode in MODES:
            active = session.scalar(
                select(RankingStrategyVersion)
                .where(
                    RankingStrategyVersion.mode == mode,
                    RankingStrategyVersion.is_active.is_(True),
                )
                .order_by(desc(RankingStrategyVersion.created_at))
            )
            matured = list(
                session.scalars(
                    select(RankingTrainingSample).where(
                        RankingTrainingSample.mode == mode,
                        RankingTrainingSample.matured.is_(True),
                    )
                )
            )
            pending_count = len(
                list(
                    session.scalars(
                        select(RankingTrainingSample.id).where(
                            RankingTrainingSample.mode == mode,
                            RankingTrainingSample.matured.is_(False),
                        )
                    )
                )
            )
            recent_runs = list(
                session.scalars(
                    select(RankingOptimizationRun)
                    .where(RankingOptimizationRun.mode == mode)
                    .order_by(desc(RankingOptimizationRun.run_date))
                    .limit(5)
                )
            )
            audit_rows = list(session.scalars(
                select(RankingOptimizationAudit)
                .where(RankingOptimizationAudit.mode == mode)
                .order_by(desc(RankingOptimizationAudit.id))
                .limit(300)
            ))
            audits_by_run: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for audit in audit_rows:
                audits_by_run[audit.run_id].append({
                    "sample_date": audit.sample_date,
                    "split": audit.split,
                    "code": audit.code,
                    "name": audit.name,
                    "features": json.loads(audit.features_json),
                    "observations": json.loads(audit.observations_json),
                    "labels": json.loads(audit.labels_json),
                    "candidate_score": audit.candidate_score,
                })
            versions = list(
                session.scalars(
                    select(RankingStrategyVersion)
                    .where(RankingStrategyVersion.mode == mode)
                    .order_by(desc(RankingStrategyVersion.created_at))
                    .limit(10)
                )
            )
            rules = MODE_RULES[mode]
            trading_days = len({item.sample_date for item in matured})
            result[mode] = {
                "active_version": active.version if active else _baseline_version(mode),
                "horizon_observations": rules["horizon"],
                "matured_samples": len(matured),
                "pending_samples": pending_count,
                "trading_days": trading_days,
                "required_samples": rules["required_samples"],
                "required_days": rules["required_days"],
                "sample_progress_pct": round(
                    min(len(matured) / rules["required_samples"], 1) * 100, 1
                ),
                "day_progress_pct": round(
                    min(trading_days / rules["required_days"], 1) * 100, 1
                ),
                "ready_for_optimization": (
                    len(matured) >= rules["required_samples"]
                    and trading_days >= rules["required_days"]
                ),
                "recent_runs": [
                    {
                        "run_date": run.run_date,
                        "status": run.status,
                        "candidate_version": run.candidate_version,
                        "sample_count": run.sample_count,
                        "trading_days": run.trading_days,
                        "metrics": json.loads(run.metrics_json),
                        "reason": run.reason,
                        "audit_samples": audits_by_run.get(run.id, []),
                    }
                    for run in recent_runs
                ],
                "versions": [
                    {
                        "version": version.version,
                        "status": version.status,
                        "is_active": version.is_active,
                        "trained_through": version.trained_through,
                        "train_samples": version.train_samples,
                        "validation_samples": version.validation_samples,
                        "validation_mean_return": version.validation_mean_return,
                        "validation_mean_drawdown": version.validation_mean_drawdown,
                        "validation_positive_rate": version.validation_positive_rate,
                        "activated_at": (
                            version.activated_at.isoformat()
                            if version.activated_at
                            else None
                        ),
                        "notes": version.notes,
                    }
                    for version in versions
                ],
            }
    return result


def discovery_version_map(discovery_rows: list[Any]) -> dict[int, str]:
    if not discovery_rows:
        return {}
    result: dict[int, str] = {}
    with SessionLocal() as session:
        for row in discovery_rows:
            sample = session.scalar(
                select(RankingTrainingSample).where(
                    RankingTrainingSample.sample_date == row.discovery_date,
                    RankingTrainingSample.mode == row.mode,
                    RankingTrainingSample.code == row.code,
                )
            )
            result[row.id] = (
                sample.strategy_version if sample else _baseline_version(row.mode)
            )
    return result
