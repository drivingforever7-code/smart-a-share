from __future__ import annotations

import json
import math
import threading
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import akshare as ak
import numpy as np
from sqlalchemy import desc, select

from .database import LimitBreakEvent, LimitBreakModelVersion, SessionLocal


SHANGHAI = ZoneInfo("Asia/Shanghai")
STAGES = ("midday", "afternoon", "close")
FEATURE_NAMES = (
    "early_limit",
    "price_proximity",
    "break_quality",
    "turnover_quality",
    "amplitude_quality",
    "liquidity",
    "cap_quality",
    "prior_heat",
    "market_strength",
    "industry_heat",
)
BASELINE_VERSION = "rule-baseline-v1"
BASELINE_PARAMETERS = {
    "intercept": -2.35,
    "weights": {
        "early_limit": 0.55,
        "price_proximity": 1.55,
        "break_quality": 0.72,
        "turnover_quality": 0.32,
        "amplitude_quality": 0.48,
        "liquidity": 0.18,
        "cap_quality": 0.15,
        "prior_heat": 0.24,
        "market_strength": 0.82,
        "industry_heat": 0.24,
    },
}

_pool_cache_lock = threading.Lock()
_pool_cache: dict[str, Any] = {}


class LimitBreakDataError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(SHANGHAI).replace(tzinfo=None)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _integer(value: Any, default: int = 0) -> int:
    return int(round(_number(value, default)))


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return default if result.lower() == "nan" else result


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def _stage_for_time(moment: datetime) -> str:
    minutes = moment.hour * 60 + moment.minute
    if minutes < 13 * 60 + 30:
        return "midday"
    if minutes < 15 * 60 + 5:
        return "afternoon"
    return "close"


def _time_minutes(raw: Any) -> int:
    digits = "".join(char for char in _text(raw) if char.isdigit()).zfill(6)[-6:]
    try:
        return int(digits[:2]) * 60 + int(digits[2:4])
    except ValueError:
        return 15 * 60


def _display_time(raw: Any) -> str | None:
    digits = "".join(char for char in _text(raw) if char.isdigit()).zfill(6)[-6:]
    if not digits.strip("0"):
        return None
    return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"


def _limit_stats(raw: Any) -> tuple[int, int]:
    parts = _text(raw, "0/0").split("/")
    return (
        _integer(parts[0]) if parts else 0,
        _integer(parts[1]) if len(parts) > 1 else 0,
    )


def _fetch_pools(trade_date: str):
    now = _now()
    cache_key = trade_date
    with _pool_cache_lock:
        cached = _pool_cache.get(cache_key)
        if cached and (now - cached["time"]).total_seconds() < 45:
            return cached["broken"], cached["sealed"]
    try:
        broken = ak.stock_zt_pool_zbgc_em(date=trade_date.replace("-", ""))
        sealed = ak.stock_zt_pool_em(date=trade_date.replace("-", ""))
    except Exception as exc:  # AKShare 上游会抛出多种网络异常
        raise LimitBreakDataError(f"炸板行情暂时不可用：{exc}") from exc
    with _pool_cache_lock:
        _pool_cache[cache_key] = {"time": now, "broken": broken, "sealed": sealed}
    return broken, sealed


def _row_dict(row: Any) -> dict[str, Any]:
    return {str(key): value for key, value in row.to_dict().items()}


def _feature_snapshot(
    item: dict[str, Any],
    *,
    market_seal_rate: float,
    industry_heat_count: int,
) -> dict[str, float]:
    first_minutes = _time_minutes(item.get("首次封板时间"))
    early_limit = _clamp((15 * 60 - first_minutes) / (5.5 * 60))
    price = _number(item.get("最新价"))
    limit_price = _number(item.get("涨停价"), price)
    distance = max((limit_price - price) / limit_price * 100, 0.0) if limit_price else 10.0
    break_count = max(_integer(item.get("炸板次数"), 1), 1)
    turnover = _number(item.get("换手率"))
    amplitude = _number(item.get("振幅"))
    amount = max(_number(item.get("成交额")), 1.0)
    circulating_cap = max(_number(item.get("流通市值")), 1.0)
    _, recent_limit_count = _limit_stats(item.get("涨停统计"))
    return {
        "early_limit": round(early_limit, 6),
        "price_proximity": round(1 - _clamp(distance / 8), 6),
        "break_quality": round(1 - _clamp((break_count - 1) / 5), 6),
        "turnover_quality": round(1 - _clamp(abs(turnover - 10) / 18), 6),
        "amplitude_quality": round(1 - _clamp(amplitude / 24), 6),
        "liquidity": round(_clamp((math.log10(amount) - 7) / 3), 6),
        "cap_quality": round(1 - _clamp(abs(math.log10(circulating_cap) - 9.7) / 2.2), 6),
        "prior_heat": round(_clamp(recent_limit_count / 5), 6),
        "market_strength": round(_clamp(market_seal_rate), 6),
        "industry_heat": round(_clamp(industry_heat_count / 6), 6),
    }


def _active_model(session) -> tuple[str, dict[str, Any]]:
    model = session.scalar(
        select(LimitBreakModelVersion)
        .where(LimitBreakModelVersion.is_active.is_(True))
        .order_by(desc(LimitBreakModelVersion.created_at))
    )
    if model is None:
        return BASELINE_VERSION, BASELINE_PARAMETERS
    return model.version, json.loads(model.parameters_json)


def _probability(features: dict[str, float], parameters: dict[str, Any]) -> float:
    linear = _number(parameters.get("intercept"), -2.35)
    weights = parameters.get("weights") or {}
    linear += sum(_number(weights.get(name)) * features.get(name, 0.0) for name in FEATURE_NAMES)
    linear = min(max(linear, -20), 20)
    return round(100 / (1 + math.exp(-linear)), 1)


def _advice(
    probability: float,
    item: dict[str, Any],
    features: dict[str, float],
) -> dict[str, Any]:
    price = _number(item.get("最新价"))
    limit_price = _number(item.get("涨停价"), price)
    distance = max((limit_price - price) / limit_price * 100, 0.0) if limit_price else 99.0
    break_count = max(_integer(item.get("炸板次数"), 1), 1)
    turnover = _number(item.get("换手率"))
    amplitude = _number(item.get("振幅"))

    positives: list[tuple[float, str]] = [
        (features["price_proximity"], f"距涨停价仅 {distance:.2f}%"),
        (features["early_limit"], f"首次封板时间 {_display_time(item.get('首次封板时间')) or '未知'}"),
        (features["break_quality"], f"当前记录炸板 {break_count} 次"),
        (features["market_strength"], f"当日市场封板率 {features['market_strength'] * 100:.1f}%"),
        (features["industry_heat"], "同行业涨停或炸板活跃"),
    ]
    reasons = [text for _, text in sorted(positives, reverse=True)[:3]]
    risks: list[str] = []
    if distance > 3:
        risks.append(f"距离涨停价仍有 {distance:.2f}%，回封需要更强买盘")
    if break_count >= 4:
        risks.append(f"已炸板 {break_count} 次，抛压反复")
    if turnover > 22:
        risks.append(f"换手率 {turnover:.1f}% 偏高，分歧较大")
    if amplitude > 16:
        risks.append(f"振幅 {amplitude:.1f}% 偏高")
    if not risks:
        risks.append("炸板股波动和成交失败风险显著高于普通股票")

    if (
        probability >= 75
        and distance <= 2.5
        and break_count <= 3
        and turnover <= 25
        and amplitude <= 20
    ):
        recommendation = "建议小仓位试买"
        position_pct = 10
    elif probability >= 65:
        recommendation = "建议观察"
        position_pct = 0
    else:
        recommendation = "建议回避"
        position_pct = 0
    return {
        "recommendation": recommendation,
        "position_pct": position_pct,
        "reasons": reasons,
        "risks": risks[:3],
        "invalidation": "价格继续远离涨停价、炸板次数增加、市场封板率快速下降或数据超过 2 分钟未更新",
    }


def _review(event: LimitBreakEvent, outcome: str) -> dict[str, Any]:
    features = json.loads(event.features_json)
    positive = sorted(
        ((features.get(name, 0.0), name) for name in FEATURE_NAMES),
        reverse=True,
    )
    labels = {
        "early_limit": "首次封板较早",
        "price_proximity": "观测时仍接近涨停价",
        "break_quality": "炸板次数较少",
        "turnover_quality": "换手率处于中性区间",
        "amplitude_quality": "日内振幅相对可控",
        "liquidity": "成交活跃度可用",
        "cap_quality": "流通市值处于模型中性区间",
        "prior_heat": "近期涨停活跃",
        "market_strength": "市场封板情绪较强",
        "industry_heat": "同行业热度较高",
    }
    strongest = [labels[name] for _, name in positive[:3]]
    predicted_reseal = event.predicted_probability >= 50
    actual_reseal = outcome == "resealed"
    if predicted_reseal == actual_reseal:
        summary = (
            "模型判断方向正确：优势因子最终得到回封结果验证。"
            if actual_reseal
            else "模型判断方向正确：弱势特征对应了收盘未回封。"
        )
    else:
        summary = (
            "模型低估了回封：盘中弱势特征随后被新增买盘扭转。"
            if actual_reseal
            else "模型高估了回封：临近涨停等优势未能抵消后续抛压。"
        )
    return {
        "summary": summary,
        "strongest_factors": strongest,
        "prediction_correct": predicted_reseal == actual_reseal,
    }


def _event_values(
    item: dict[str, Any],
    *,
    trade_date: str,
    stage: str,
    market_seal_rate: float,
    industry_heat_count: int,
    model_version: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    price = _number(item.get("最新价"))
    limit_price = _number(item.get("涨停价"), price)
    distance = max((limit_price - price) / limit_price * 100, 0.0) if limit_price else 0.0
    features = _feature_snapshot(
        item,
        market_seal_rate=market_seal_rate,
        industry_heat_count=industry_heat_count,
    )
    probability = _probability(features, parameters)
    advice = _advice(probability, item, features)
    return {
        "trade_date": trade_date,
        "code": _text(item.get("代码")),
        "name": _text(item.get("名称")),
        "industry": _text(item.get("所属行业")) or None,
        "prediction_stage": stage,
        "observed_at": _now(),
        "first_limit_time": _display_time(item.get("首次封板时间")),
        "last_limit_time": _display_time(item.get("最后封板时间")),
        "price": price,
        "limit_price": limit_price,
        "change_pct": _number(item.get("涨跌幅")),
        "distance_to_limit_pct": round(distance, 3),
        "amount": _number(item.get("成交额")),
        "circulating_market_cap": _number(item.get("流通市值")),
        "turnover_rate": _number(item.get("换手率")),
        "amplitude": _number(item.get("振幅")),
        "speed": _number(item.get("涨速")),
        "break_count": _integer(item.get("炸板次数")),
        "limit_statistics": _text(item.get("涨停统计"), "0/0"),
        "streak_count": _integer(item.get("连板数")),
        "market_seal_rate": round(market_seal_rate * 100, 2),
        "industry_heat": industry_heat_count,
        "features_json": json.dumps(features, ensure_ascii=False),
        "predicted_probability": probability,
        "recommendation": advice["recommendation"],
        "position_pct": advice["position_pct"],
        "reasons_json": json.dumps(advice["reasons"], ensure_ascii=False),
        "risks_json": json.dumps(advice["risks"], ensure_ascii=False),
        "invalidation": advice["invalidation"],
        "model_version": model_version,
        "outcome": "pending",
        "eligible_for_evaluation": stage != "close",
        "source": "AKShare/东方财富涨停板行情",
    }


def _evaluation_events(session) -> list[LimitBreakEvent]:
    rows = list(
        session.scalars(
            select(LimitBreakEvent)
            .where(
                LimitBreakEvent.eligible_for_evaluation.is_(True),
                LimitBreakEvent.outcome.in_(("resealed", "failed")),
            )
            .order_by(
                LimitBreakEvent.trade_date,
                LimitBreakEvent.code,
                LimitBreakEvent.observed_at,
            )
        )
    )
    latest: dict[tuple[str, str], LimitBreakEvent] = {}
    for row in rows:
        latest[(row.trade_date, row.code)] = row
    qualified = [
        row for row in latest.values()
        if row.predicted_probability >= 65
        and row.distance_to_limit_pct <= 3.0
        and row.break_count <= 3
        and row.turnover_rate <= 25
        and row.amplitude <= 20
    ]
    selected: list[LimitBreakEvent] = []
    for trade_date in sorted({row.trade_date for row in qualified}):
        day_rows = sorted(
            (row for row in qualified if row.trade_date == trade_date),
            key=lambda row: row.predicted_probability,
            reverse=True,
        )
        selected.extend(day_rows[:10])
    return selected


def _fit_candidate(session, trained_through: str) -> None:
    samples = _evaluation_events(session)
    dates = sorted({row.trade_date for row in samples})
    if len(samples) < 60 or len(dates) < 10:
        return
    version = f"logit-{trained_through.replace('-', '')}-{len(samples)}"
    if session.get(LimitBreakModelVersion, version) is not None:
        return

    split_index = max(1, int(len(dates) * 0.8))
    train_dates = set(dates[:split_index])
    validation_dates = set(dates[split_index:])
    train = [row for row in samples if row.trade_date in train_dates]
    validation = [row for row in samples if row.trade_date in validation_dates]
    if len(validation) < 12:
        return

    x_train = np.array(
        [[json.loads(row.features_json).get(name, 0.0) for name in FEATURE_NAMES] for row in train],
        dtype=float,
    )
    y_train = np.array([1.0 if row.outcome == "resealed" else 0.0 for row in train])
    if len(set(y_train.tolist())) < 2:
        return

    weights = np.array([BASELINE_PARAMETERS["weights"][name] for name in FEATURE_NAMES], dtype=float)
    intercept = float(BASELINE_PARAMETERS["intercept"])
    for _ in range(700):
        logits = np.clip(x_train @ weights + intercept, -20, 20)
        predictions = 1 / (1 + np.exp(-logits))
        error = predictions - y_train
        weights -= 0.08 * ((x_train.T @ error) / len(train) + 0.03 * weights)
        intercept -= 0.08 * float(error.mean())

    candidate_parameters = {
        "intercept": round(intercept, 8),
        "weights": {
            name: round(float(weight), 8)
            for name, weight in zip(FEATURE_NAMES, weights, strict=True)
        },
    }
    _, incumbent_parameters = _active_model(session)
    y_validation = np.array(
        [1.0 if row.outcome == "resealed" else 0.0 for row in validation],
        dtype=float,
    )
    candidate_prob = np.array(
        [
            _probability(json.loads(row.features_json), candidate_parameters) / 100
            for row in validation
        ]
    )
    incumbent_prob = np.array(
        [
            _probability(json.loads(row.features_json), incumbent_parameters) / 100
            for row in validation
        ]
    )
    candidate_brier = float(np.mean((candidate_prob - y_validation) ** 2))
    incumbent_brier = float(np.mean((incumbent_prob - y_validation) ** 2))
    candidate_accuracy = float(np.mean((candidate_prob >= 0.5) == y_validation))
    activate = candidate_brier <= incumbent_brier - 0.01
    if activate:
        for current in session.scalars(
            select(LimitBreakModelVersion).where(LimitBreakModelVersion.is_active.is_(True))
        ):
            current.is_active = False
    session.add(
        LimitBreakModelVersion(
            version=version,
            model_type="logistic_regression",
            parameters_json=json.dumps(candidate_parameters, ensure_ascii=False),
            trained_through=trained_through,
            train_samples=len(train),
            validation_samples=len(validation),
            validation_brier=round(candidate_brier, 6),
            validation_accuracy=round(candidate_accuracy * 100, 2),
            is_active=activate,
            created_at=_now(),
        )
    )


def _prune_redundant_finalized_observations(session, trade_date: str) -> int:
    """Keep one auditable prediction per stock/day after the close review is complete."""
    rows = list(
        session.scalars(
            select(LimitBreakEvent)
            .where(
                LimitBreakEvent.trade_date == trade_date,
                LimitBreakEvent.outcome.in_(("resealed", "failed")),
            )
            .order_by(
                LimitBreakEvent.code,
                desc(LimitBreakEvent.eligible_for_evaluation),
                desc(LimitBreakEvent.observed_at),
            )
        )
    )
    kept_codes: set[str] = set()
    removed = 0
    for row in rows:
        if row.code not in kept_codes:
            kept_codes.add(row.code)
            continue
        session.delete(row)
        removed += 1
    return removed


def capture_limit_breaks(
    stage: Literal["auto", "midday", "afternoon", "close"] = "auto",
    trade_date: str | None = None,
) -> dict[str, Any]:
    moment = _now()
    resolved_stage = _stage_for_time(moment) if stage == "auto" else stage
    resolved_date = trade_date or moment.date().isoformat()
    minutes = moment.hour * 60 + moment.minute
    if stage == "auto" and minutes < 9 * 60 + 25:
        return {
            "trade_date": resolved_date,
            "stage": "pre_market",
            "created": 0,
            "broken_count": 0,
            "resealed_count": 0,
            "market_seal_rate": 0.0,
            "source": "AKShare/东方财富涨停板行情",
            "captured_at": moment.isoformat(),
            "skipped_reason": "集合竞价前不保存盘中预测，避免把上一交易日或未完成数据当作今日样本。",
        }
    broken_df, sealed_df = _fetch_pools(resolved_date)
    broken_rows = [_row_dict(row) for _, row in broken_df.iterrows()]
    sealed_rows = [_row_dict(row) for _, row in sealed_df.iterrows()]
    resealed_rows = [row for row in sealed_rows if _integer(row.get("炸板次数")) > 0]
    candidates = (
        [*broken_rows, *resealed_rows]
        if resolved_stage == "close"
        else broken_rows
    )
    market_seal_rate = len(sealed_rows) / max(len(sealed_rows) + len(broken_rows), 1)
    industry_counts: dict[str, int] = defaultdict(int)
    for row in [*sealed_rows, *broken_rows]:
        industry_counts[_text(row.get("所属行业"), "行业未知")] += 1

    created = 0
    pruned = 0
    with SessionLocal.begin() as session:
        model_version, parameters = _active_model(session)
        ranked_values: list[dict[str, Any]] = []
        if resolved_stage != "close":
            for item in candidates:
                values = _event_values(
                    item,
                    trade_date=resolved_date,
                    stage=resolved_stage,
                    market_seal_rate=market_seal_rate,
                    industry_heat_count=industry_counts[_text(item.get("所属行业"), "行业未知")],
                    model_version=model_version,
                    parameters=parameters,
                )
                if values["predicted_probability"] >= 60:
                    ranked_values.append(values)
            ranked_values.sort(key=lambda row: row["predicted_probability"], reverse=True)
            ranked_values = ranked_values[:10]
        for values in ranked_values:
            code = values["code"]
            if not code:
                continue
            exists = session.scalar(
                select(LimitBreakEvent.id).where(
                    LimitBreakEvent.trade_date == resolved_date,
                    LimitBreakEvent.code == code,
                    LimitBreakEvent.prediction_stage == resolved_stage,
                )
            )
            if exists is not None:
                continue
            session.add(LimitBreakEvent(**values))
            created += 1
        session.flush()

        if resolved_stage == "close":
            resealed_codes = {_text(row.get("代码")) for row in resealed_rows}
            failed_codes = {_text(row.get("代码")) for row in broken_rows}
            events = list(
                session.scalars(
                    select(LimitBreakEvent).where(LimitBreakEvent.trade_date == resolved_date)
                )
            )
            for event in events:
                if event.code in resealed_codes:
                    event.outcome = "resealed"
                elif event.code in failed_codes:
                    event.outcome = "failed"
                else:
                    continue
                event.outcome_at = moment
                event.review_json = json.dumps(_review(event, event.outcome), ensure_ascii=False)
            _fit_candidate(session, resolved_date)
            pruned = _prune_redundant_finalized_observations(session, resolved_date)

    return {
        "trade_date": resolved_date,
        "stage": resolved_stage,
        "created": created,
        "pruned": pruned,
        "broken_count": len(broken_rows),
        "resealed_count": len(resealed_rows),
        "market_seal_rate": round(market_seal_rate * 100, 2),
        "source": "AKShare/东方财富涨停板行情",
        "captured_at": moment.isoformat(),
    }


def _model_stats(session) -> dict[str, Any]:
    events = _evaluation_events(session)
    model_version, _ = _active_model(session)
    if not events:
        return {
            "active_model": model_version,
            "sample_count": 0,
            "trading_days": 0,
            "resealed_count": 0,
            "failed_count": 0,
            "reseal_rate": None,
            "brier_score": None,
            "accuracy": None,
            "calibration": [],
            "upgrade_gate": "至少需要 60 个有效盘中样本、10 个交易日和完整正负样本。",
        }
    outcomes = [1 if row.outcome == "resealed" else 0 for row in events]
    probabilities = [row.predicted_probability / 100 for row in events]
    calibration = []
    for low in (0, 20, 40, 60, 80):
        band = [
            (probability, outcome)
            for probability, outcome in zip(probabilities, outcomes, strict=True)
            if low / 100 <= probability < (low + 20) / 100
            or (low == 80 and probability == 1)
        ]
        if band:
            calibration.append(
                {
                    "range": f"{low}-{low + 20}%",
                    "count": len(band),
                    "average_probability": round(sum(item[0] for item in band) / len(band) * 100, 1),
                    "actual_reseal_rate": round(sum(item[1] for item in band) / len(band) * 100, 1),
                }
            )
    return {
        "active_model": model_version,
        "sample_count": len(events),
        "trading_days": len({row.trade_date for row in events}),
        "resealed_count": sum(outcomes),
        "failed_count": len(events) - sum(outcomes),
        "reseal_rate": round(sum(outcomes) / len(events) * 100, 2),
        "brier_score": round(
            sum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes, strict=True))
            / len(events),
            4,
        ),
        "accuracy": round(
            sum((probability >= 0.5) == bool(outcome) for probability, outcome in zip(probabilities, outcomes, strict=True))
            / len(events)
            * 100,
            2,
        ),
        "calibration": calibration,
        "upgrade_gate": "候选模型仅在时间切分样本外 Brier 分数至少改善 0.01 时自动升级。",
    }


def limit_break_research(days: int = 5, refresh: bool = True) -> dict[str, Any]:
    capture_meta = None
    warning = None
    if refresh:
        try:
            capture_meta = capture_limit_breaks("auto")
        except LimitBreakDataError as exc:
            warning = str(exc)

    with SessionLocal() as session:
        dates = list(
            session.scalars(
                select(LimitBreakEvent.trade_date)
                .distinct()
                .order_by(desc(LimitBreakEvent.trade_date))
                .limit(days)
            )
        )
        display_date = dates[0] if dates else None
        rows = (
            list(
                session.scalars(
                    select(LimitBreakEvent)
                    .where(LimitBreakEvent.trade_date == display_date)
                    .order_by(
                        desc(LimitBreakEvent.trade_date),
                        LimitBreakEvent.code,
                        LimitBreakEvent.observed_at,
                    )
                )
            )
            if dates
            else []
        )
        evaluation_events = _evaluation_events(session)
        stats = _model_stats(session)

    grouped: dict[tuple[str, str], list[LimitBreakEvent]] = defaultdict(list)
    for row in rows:
        grouped[(row.trade_date, row.code)].append(row)

    items = []
    for (trade_date, code), observations in grouped.items():
        latest = observations[-1]
        eligible = [row for row in observations if row.eligible_for_evaluation]
        prediction = eligible[-1] if eligible else latest
        review = json.loads(prediction.review_json) if prediction.review_json else None
        items.append(
            {
                "id": prediction.id,
                "trade_date": trade_date,
                "code": code,
                "name": latest.name,
                "industry": latest.industry,
                "prediction_stage": prediction.prediction_stage,
                "observed_at": prediction.observed_at.isoformat(),
                "first_limit_time": latest.first_limit_time,
                "last_limit_time": latest.last_limit_time,
                "price": latest.price,
                "limit_price": latest.limit_price,
                "change_pct": latest.change_pct,
                "distance_to_limit_pct": latest.distance_to_limit_pct,
                "amount": latest.amount,
                "circulating_market_cap": latest.circulating_market_cap,
                "turnover_rate": latest.turnover_rate,
                "amplitude": latest.amplitude,
                "break_count": latest.break_count,
                "limit_statistics": latest.limit_statistics,
                "streak_count": latest.streak_count,
                "market_seal_rate": latest.market_seal_rate,
                "industry_heat": latest.industry_heat,
                "predicted_probability": prediction.predicted_probability,
                "recommendation": prediction.recommendation,
                "position_pct": prediction.position_pct,
                "reasons": json.loads(prediction.reasons_json),
                "risks": json.loads(prediction.risks_json),
                "invalidation": prediction.invalidation,
                "model_version": prediction.model_version,
                "outcome": latest.outcome,
                "eligible_for_evaluation": prediction.eligible_for_evaluation,
                "review": review,
                "source": latest.source,
                "observation_count": len(observations),
            }
        )

    # 只展示高概率且通过基础风险约束的候选，已回封记录仍按原概率顺序保留
    items = [
        item for item in items
        if item["predicted_probability"] >= 65
        and item["distance_to_limit_pct"] <= 3.0
        and item["break_count"] <= 3
        and item["turnover_rate"] <= 25
        and item["amplitude"] <= 20
    ]
    items.sort(key=lambda item: (item["trade_date"], item["predicted_probability"]), reverse=True)
    limited_items: list[dict[str, Any]] = []
    for trade_date in dates:
        limited_items.extend([item for item in items if item["trade_date"] == trade_date][:10])
    items = limited_items
    rank_by_date: dict[str, int] = defaultdict(int)
    for item in items:
        rank_by_date[item["trade_date"]] += 1
        item["probability_rank"] = rank_by_date[item["trade_date"]]

    daily_reviews = []
    for trade_date in dates:
        day_events = [row for row in evaluation_events if row.trade_date == trade_date]
        day_items = [item for item in items if item["trade_date"] == trade_date]
        finished = day_events or [
            item for item in day_items if item["outcome"] in ("resealed", "failed")
        ]
        daily_reviews.append(
            {
                "trade_date": trade_date,
                "total": len(day_items) if day_items else len(day_events),
                "evaluated": len(day_events),
                "resealed": sum(item.outcome == "resealed" if isinstance(item, LimitBreakEvent) else item["outcome"] == "resealed" for item in finished),
                "failed": sum(item.outcome == "failed" if isinstance(item, LimitBreakEvent) else item["outcome"] == "failed" for item in finished),
                "reseal_rate": (
                    round(sum(item.outcome == "resealed" if isinstance(item, LimitBreakEvent) else item["outcome"] == "resealed" for item in finished) / len(finished) * 100, 2)
                    if finished
                    else None
                ),
            }
        )

    return {
        "days": days,
        "display_date": display_date,
        "available_dates": dates,
        "items": items,
        "daily_reviews": daily_reviews,
        "model_stats": stats,
        "capture": capture_meta,
        "warning": warning,
        "methodology": {
            "prediction_rule": "盘中时间戳特征预测，收盘结果仅用于标签和复盘。",
            "source_url": "https://akshare.akfamily.xyz/data/stock/stock.html",
            "research_url": "https://arxiv.org/abs/1503.03548",
            "risk_note": "炸板股属于高波动事件，回封概率不是收益概率，也不代表能够按显示价格成交。",
        },
    }
