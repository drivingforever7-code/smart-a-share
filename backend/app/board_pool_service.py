from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import akshare as ak
from sqlalchemy import desc, select

from .database import BoardPoolEvent, BoardPoolModelVersion, SessionLocal

SHANGHAI = ZoneInfo("Asia/Shanghai")
POOL_TYPES = ("streak", "down_repair")
MIN_PROBABILITY = {"streak": 0.58, "down_repair": 0.64}
BASELINES = {
    "streak": {
        "version": "streak-rule-v1.0",
        "intercept": -2.0,
        "weights": {"height": 0.42, "early": 0.55, "seal": 0.65, "turnover": 0.35,
                    "liquidity": 0.30, "break_quality": 0.45, "industry": 0.28},
    },
    "down_repair": {
        "version": "down-repair-rule-v1.0",
        "intercept": -2.35,
        "weights": {"short_streak": 0.55, "weak_seal": 0.65, "liquidity": 0.35,
                    "turnover": 0.25, "large_cap": 0.30, "market_relief": 0.45},
    },
}


class BoardPoolDataError(RuntimeError):
    pass


def _value(row: dict[str, Any], *names: str, default: Any = 0) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value) not in {"", "nan", "None"}:
            return value
    return default


def _number(row: dict[str, Any], *names: str, default: float = 0.0) -> float:
    try:
        return float(str(_value(row, *names, default=default)).replace("%", ""))
    except (TypeError, ValueError):
        return default


def _code(row: dict[str, Any]) -> str:
    return str(_value(row, "代码", "股票代码", default="")).zfill(6)


def _minutes(raw: Any) -> int:
    digits = "".join(ch for ch in str(raw) if ch.isdigit()).zfill(6)
    try:
        return int(digits[-6:-4]) * 60 + int(digits[-4:-2])
    except ValueError:
        return 15 * 60


def _rows(frame: Any) -> list[dict[str, Any]]:
    return [] if frame is None or getattr(frame, "empty", True) else frame.to_dict("records")


def _fetch(trade_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    compact = trade_date.replace("-", "")
    try:
        up = _rows(ak.stock_zt_pool_em(date=compact))
        down = _rows(ak.stock_zt_pool_dtgc_em(date=compact))
    except Exception as exc:
        raise BoardPoolDataError(f"连板/跌停池数据暂不可用：{exc}") from exc
    return up, down


def _features(pool_type: str, row: dict[str, Any], industry_count: Counter[str], market: dict[str, int]) -> dict[str, float]:
    amount = _number(row, "成交额")
    cap = _number(row, "流通市值")
    turnover = _number(row, "换手率")
    seal = _number(row, "封板资金", "封单资金")
    industry = str(_value(row, "所属行业", "行业", default="未知"))
    if pool_type == "streak":
        height = _number(row, "连板数", "连续涨停天数", default=1)
        breaks = _number(row, "炸板次数", "开板次数")
        return {
            "height": min(height, 6) / 6,
            "early": max(0.0, min(1.0, (14 * 60 + 50 - _minutes(_value(row, "首次封板时间"))) / 330)),
            "seal": min(seal / max(amount, 1), 0.25) / 0.25,
            "turnover": max(0.0, 1 - abs(turnover - 14) / 22),
            "liquidity": min(amount / 1_000_000_000, 1.0),
            "break_quality": max(0.0, 1 - breaks / 4),
            "industry": min(industry_count[industry] / 5, 1.0),
        }
    streak = _number(row, "连续跌停", "连续跌停天数", default=1)
    return {
        "short_streak": max(0.0, 1 - (streak - 1) / 3),
        "weak_seal": max(0.0, 1 - min(seal / max(amount, 1), 0.5) / 0.5),
        "liquidity": min(amount / 800_000_000, 1.0),
        "turnover": max(0.0, 1 - abs(turnover - 10) / 20),
        "large_cap": min(cap / 10_000_000_000, 1.0),
        "market_relief": max(0.0, 1 - market.get("down", 0) / max(market.get("up", 0) + market.get("down", 0), 1)),
    }


def _active_model(session, pool_type: str) -> tuple[str, dict[str, Any]]:
    row = session.scalar(select(BoardPoolModelVersion).where(
        BoardPoolModelVersion.pool_type == pool_type,
        BoardPoolModelVersion.is_active.is_(True),
    ).order_by(desc(BoardPoolModelVersion.created_at)))
    if row:
        return row.version, json.loads(row.parameters_json)
    baseline = BASELINES[pool_type]
    return baseline["version"], baseline


def _probability(features: dict[str, float], parameters: dict[str, Any]) -> float:
    z = float(parameters.get("intercept", 0))
    for key, weight in parameters.get("weights", {}).items():
        z += float(weight) * features.get(key, 0.0)
    return round(1 / (1 + math.exp(-max(-20, min(20, z)))), 4)


def _finalize_previous(session, trade_date: str, current_up: set[str], current_down: set[str]) -> int:
    pending = list(session.scalars(select(BoardPoolEvent).where(
        BoardPoolEvent.trade_date < trade_date,
        BoardPoolEvent.outcome == "pending",
    )))
    changed = 0
    for event in pending:
        success = event.code in current_up if event.pool_type == "streak" else event.code not in current_down
        event.outcome = "success" if success else "failed"
        event.outcome_date = trade_date
        event.review_json = json.dumps({
            "prediction_correct": success == (event.predicted_probability >= 0.5),
            "summary": "达到预测目标" if success else "未达到预测目标",
            "main_factors": sorted(json.loads(event.features_json).items(), key=lambda item: item[1], reverse=True)[:3],
        }, ensure_ascii=False)
        changed += 1
    return changed


def _maybe_upgrade(session, pool_type: str, trade_date: str) -> None:
    rows = list(session.scalars(select(BoardPoolEvent).where(
        BoardPoolEvent.pool_type == pool_type,
        BoardPoolEvent.outcome.in_(["success", "failed"]),
    ).order_by(BoardPoolEvent.trade_date, BoardPoolEvent.rank)))
    days = sorted({row.trade_date for row in rows})
    if len(rows) < 60 or len(days) < 10:
        return
    if session.scalar(select(BoardPoolModelVersion.version).where(BoardPoolModelVersion.trained_through == trade_date, BoardPoolModelVersion.pool_type == pool_type)):
        return
    split = max(1, int(len(days) * 0.7))
    train_days, validation_days = set(days[:split]), set(days[split:])
    train = [row for row in rows if row.trade_date in train_days]
    validation = [row for row in rows if row.trade_date in validation_days]
    if len(validation) < 20:
        return
    actual_rate = sum(row.outcome == "success" for row in train) / len(train)
    predicted_rate = sum(row.predicted_probability for row in train) / len(train)
    baseline = dict(BASELINES[pool_type])
    baseline["weights"] = dict(baseline["weights"])
    baseline["intercept"] += max(-0.45, min(0.45, (actual_rate - predicted_rate) * 2))
    old_brier = sum((row.predicted_probability - (row.outcome == "success")) ** 2 for row in validation) / len(validation)
    candidate_probs = [_probability(json.loads(row.features_json), baseline) for row in validation]
    new_brier = sum((prob - (row.outcome == "success")) ** 2 for prob, row in zip(candidate_probs, validation)) / len(validation)
    accepted = new_brier <= old_brier - 0.01
    version = f"{pool_type}-v1.{len(list(session.scalars(select(BoardPoolModelVersion).where(BoardPoolModelVersion.pool_type == pool_type)))) + 1}"
    if accepted:
        for current in session.scalars(select(BoardPoolModelVersion).where(BoardPoolModelVersion.pool_type == pool_type, BoardPoolModelVersion.is_active.is_(True))):
            current.is_active = False
    session.add(BoardPoolModelVersion(
        version=version, pool_type=pool_type, parameters_json=json.dumps(baseline),
        trained_through=trade_date, train_samples=len(train), validation_samples=len(validation),
        validation_brier=round(new_brier, 4),
        validation_accuracy=round(sum((p >= 0.5) == (r.outcome == "success") for p, r in zip(candidate_probs, validation)) / len(validation), 4),
        is_active=accepted,
    ))


def capture_board_pools(trade_date: str | None = None) -> dict[str, Any]:
    trade_date = trade_date or datetime.now(SHANGHAI).date().isoformat()
    up_rows, down_rows = _fetch(trade_date)
    current_up, current_down = {_code(row) for row in up_rows}, {_code(row) for row in down_rows}
    industry_count = Counter(str(_value(row, "所属行业", "行业", default="未知")) for row in up_rows)
    market = {"up": len(up_rows), "down": len(down_rows)}
    created = 0
    with SessionLocal.begin() as session:
        finalized = _finalize_previous(session, trade_date, current_up, current_down)
        pools = {
            "streak": [row for row in up_rows if _number(row, "连板数", "连续涨停天数", default=1) >= 2],
            "down_repair": down_rows,
        }
        for pool_type, rows in pools.items():
            version, parameters = _active_model(session, pool_type)
            candidates = []
            for row in rows:
                features = _features(pool_type, row, industry_count, market)
                probability = _probability(features, parameters)
                if probability >= MIN_PROBABILITY[pool_type]:
                    candidates.append((probability, row, features))
            candidates.sort(key=lambda item: item[0], reverse=True)
            for rank, (probability, row, features) in enumerate(candidates[:10], 1):
                code = _code(row)
                exists = session.scalar(select(BoardPoolEvent.id).where(
                    BoardPoolEvent.trade_date == trade_date,
                    BoardPoolEvent.pool_type == pool_type,
                    BoardPoolEvent.code == code,
                ))
                if exists:
                    continue
                reasons = [f"模型概率 {probability * 100:.1f}%", "仅使用预测时已可用的涨跌停池字段"]
                risks = ["极端情绪票波动大，概率不代表可成交或保证收益"]
                session.add(BoardPoolEvent(
                    trade_date=trade_date, pool_type=pool_type, code=code,
                    name=str(_value(row, "名称", default=code)),
                    industry=str(_value(row, "所属行业", "行业", default="未知")),
                    rank=rank, predicted_at=datetime.now(SHANGHAI).replace(tzinfo=None),
                    predicted_probability=probability,
                    recommendation="小仓位观察" if probability >= 0.72 else "仅观察",
                    reasons_json=json.dumps(reasons, ensure_ascii=False),
                    risks_json=json.dumps(risks, ensure_ascii=False),
                    features_json=json.dumps(features, ensure_ascii=False),
                    model_version=version, source="AKShare 东方财富涨跌停池",
                ))
                created += 1
        for pool_type in POOL_TYPES:
            _maybe_upgrade(session, pool_type, trade_date)
    return {"trade_date": trade_date, "created": created, "finalized": finalized, "up_count": len(up_rows), "down_count": len(down_rows)}


def _stats(rows: list[BoardPoolEvent], pool_type: str) -> dict[str, Any]:
    evaluated = [row for row in rows if row.outcome in {"success", "failed"}]
    success = sum(row.outcome == "success" for row in evaluated)
    return {
        "pool_type": pool_type,
        "sample_count": len(evaluated),
        "trading_days": len({row.trade_date for row in evaluated}),
        "success_rate": round(success / len(evaluated), 4) if evaluated else None,
        "accuracy": round(sum((row.predicted_probability >= 0.5) == (row.outcome == "success") for row in evaluated) / len(evaluated), 4) if evaluated else None,
        "brier_score": round(sum((row.predicted_probability - (row.outcome == "success")) ** 2 for row in evaluated) / len(evaluated), 4) if evaluated else None,
        "method": "按每个交易日前 10 个且通过概率门槛的预测统计",
    }


def board_pool_research(days: int = 5, refresh: bool = True) -> dict[str, Any]:
    warning = None
    capture = None
    if refresh:
        try:
            capture = capture_board_pools()
        except BoardPoolDataError as exc:
            warning = str(exc)
    with SessionLocal() as session:
        dates = list(session.scalars(select(BoardPoolEvent.trade_date).distinct().order_by(desc(BoardPoolEvent.trade_date)).limit(days)))
        rows = list(session.scalars(select(BoardPoolEvent).where(BoardPoolEvent.trade_date.in_(dates)).order_by(desc(BoardPoolEvent.trade_date), BoardPoolEvent.pool_type, BoardPoolEvent.rank))) if dates else []
        models = list(session.scalars(select(BoardPoolModelVersion).order_by(desc(BoardPoolModelVersion.created_at))))
    items = [{
        "id": row.id, "trade_date": row.trade_date, "pool_type": row.pool_type,
        "code": row.code, "name": row.name, "industry": row.industry, "rank": row.rank,
        "predicted_at": row.predicted_at.isoformat(), "predicted_probability": row.predicted_probability,
        "recommendation": row.recommendation, "reasons": json.loads(row.reasons_json),
        "risks": json.loads(row.risks_json), "features": json.loads(row.features_json),
        "model_version": row.model_version, "outcome": row.outcome,
        "outcome_date": row.outcome_date, "review": json.loads(row.review_json) if row.review_json else None,
        "source": row.source,
    } for row in rows]
    return {
        "days": days, "available_dates": dates, "items": items,
        "stats": {pool_type: _stats([row for row in rows if row.pool_type == pool_type], pool_type) for pool_type in POOL_TYPES},
        "versions": [{"version": row.version, "pool_type": row.pool_type, "trained_through": row.trained_through,
                      "train_samples": row.train_samples, "validation_samples": row.validation_samples,
                      "validation_brier": row.validation_brier, "validation_accuracy": row.validation_accuracy,
                      "is_active": row.is_active} for row in models],
        "capture": capture, "warning": warning,
        "methodology": {
            "streak": "预测下一交易日继续涨停并晋级连板；连板高度、封板质量、换手、流动性、行业热度联合评分",
            "down_repair": "预测下一交易日打开跌停并修复；对连续跌停和强封单从严过滤",
            "validation": "按日期顺序切分，至少 60 个完成样本、10 个交易日且验证 Brier 改善 0.01 才升级",
        },
    }
