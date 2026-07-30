from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError

from .database import RankingAdviceSnapshot, RankingDiscovery, SessionLocal
from .market_service import market_service
from .reliable_data_source import data_source
from .ranking_optimizer_service import (
    discovery_version_map,
    process_training_cycle,
    ranking_strategy_status,
)


MODES = ("short", "swing")
SHANGHAI = ZoneInfo("Asia/Shanghai")
ADVICE_MODEL_VERSION = "daily-position-v1"


def _snapshot_date(items: list[dict[str, Any]]) -> date:
    """只接受明确行情时间，禁止把抓取时间或服务器时间冒充交易日期。"""
    if not items:
        raise ValueError("没有可用于留存的榜单数据")
    dates: set[date] = set()
    for item in items:
        meta = item.get("meta") or {}
        value = str(meta.get("trade_date") or meta.get("quote_time") or "").strip()
        if len(value) < 10:
            raise ValueError("榜单缺少经校验的交易日期，本次不生成发现快照")
        try:
            dates.add(date.fromisoformat(value[:10]))
        except ValueError as exc:
            raise ValueError("榜单行情时间格式无效，本次不生成发现快照") from exc
    if len(dates) != 1:
        raise ValueError("榜单股票行情日期不一致，本次不生成发现快照")
    result = dates.pop()
    now = datetime.now(SHANGHAI)
    if result == now.date() and now.time() < time(15, 5):
        raise ValueError("当日 15:05 前不冻结收盘机会榜")
    return result


def _unique_ranked(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """保持原排名顺序按股票代码去重，避免同一股票占据两个名次。"""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        code = str(item.get("code") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def repair_repeated_cached_discoveries() -> int:
    """清理缺少行情时间且照搬上一发现日的缓存重复榜单。"""
    removed = 0
    with SessionLocal.begin() as session:
        rows = list(
            session.scalars(
                select(RankingDiscovery).order_by(
                    RankingDiscovery.mode,
                    RankingDiscovery.discovery_date,
                    RankingDiscovery.rank,
                )
            )
        )
        groups: dict[tuple[str, str], list[RankingDiscovery]] = {}
        for row in rows:
            groups.setdefault((row.mode, row.discovery_date), []).append(row)
        previous_codes: dict[str, tuple[str, ...]] = {}
        for (mode, _), group in groups.items():
            codes = tuple(row.code for row in sorted(group, key=lambda item: item.rank))
            unverified = all(
                not str(row.quote_time or "").strip()
                and "交易日历确认" not in str(row.source or "")
                for row in group
            )
            if unverified and previous_codes.get(mode) == codes:
                ids = [row.id for row in group]
                session.execute(
                    delete(RankingAdviceSnapshot).where(
                        RankingAdviceSnapshot.discovery_id.in_(ids)
                    )
                )
                session.execute(
                    delete(RankingDiscovery).where(RankingDiscovery.id.in_(ids))
                )
                removed += len(ids)
                continue
            previous_codes[mode] = codes
    return removed


def _meta_date(meta: dict[str, Any]) -> date:
    for key in ("quote_time", "fetched_at"):
        value = str(meta.get(key) or "").strip()
        if len(value) >= 10:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return datetime.now(SHANGHAI).date()


def capture_mode_snapshot(mode: str, items: list[dict[str, Any]]) -> bool:
    """北京时间 15:05 后冻结当日收盘前三，之后不回写历史排名。"""
    if mode not in MODES:
        return False
    top_three = _unique_ranked(items, 3)
    if len(top_three) < 3:
        return False
    if any(not item.get("price") or float(item["price"]) <= 0 for item in top_three):
        return False

    try:
        discovery_date = _snapshot_date(top_three)
    except ValueError:
        return False
    with SessionLocal() as session:
        exists = session.scalar(
            select(RankingDiscovery.id).where(
                RankingDiscovery.discovery_date == discovery_date.isoformat(),
                RankingDiscovery.mode == mode,
            )
        )
        if exists is not None:
            return False

    try:
        with SessionLocal.begin() as session:
            for rank, item in enumerate(top_three, start=1):
                meta = item.get("meta") or {}
                session.add(
                    RankingDiscovery(
                        discovery_date=discovery_date.isoformat(),
                        mode=mode,
                        rank=rank,
                        code=str(item["code"]),
                        name=str(item["name"]),
                        industry=item.get("industry"),
                        discovery_price=float(item["price"]),
                        discovery_score=float(item["score"]),
                        recommendation=str(item["recommendation"]),
                        confidence=float(item["confidence"]),
                        reasons_json=json.dumps(item.get("reasons") or [], ensure_ascii=False),
                        risks_json=json.dumps(item.get("risks") or [], ensure_ascii=False),
                        quote_time=meta.get("quote_time"),
                        source=(
                            f"交易日历确认；{str(meta.get('source') or '未知')}"[:30]
                            if meta.get("trade_date") and not meta.get("quote_time")
                            else str(meta.get("source") or "未知")[:30]
                        ),
                        discovered_at=datetime.now(SHANGHAI).replace(tzinfo=None),
                    )
                )
    except IntegrityError:
        return False
    return True


def _daily_action(
    row: RankingDiscovery,
    current: dict[str, Any] | None,
    current_price: float | None,
    return_pct: float | None,
    tracking_days: int,
) -> dict[str, Any]:
    if current_price is None or current is None:
        return {
            "action": "观望",
            "position_pct": 0,
            "confidence": 30.0,
            "current_score": None,
            "current_recommendation": None,
            "reasons": ["当前行情或评分不完整，不能生成高置信度操作"],
            "risks": ["数据不足时不应继续加仓或假设可以卖出"],
            "invalidation": "待最新行情和评分恢复后重新评估",
        }

    score = float(current.get("score") or 0)
    confidence = float(current.get("confidence") or 0)
    recommendation = str(current.get("recommendation") or "建议观察")
    risks = list(current.get("risks") or [])
    mode_name = "短线" if row.mode == "short" else "波段"
    stop_line = -5.0 if row.mode == "short" else -8.0
    max_days = 8 if row.mode == "short" else 30
    profit_lock = 10.0 if row.mode == "short" else 18.0
    return_value = return_pct or 0.0

    if recommendation == "建议回避" or score < 55 or return_value <= stop_line:
        action, position = "清仓", 0
        reasons = [
            f"当前{mode_name}评分 {score:.1f}，已低于继续持有门槛",
            f"发现后涨跌 {return_value:+.2f}%，止损参考 {stop_line:.1f}%",
        ]
    elif tracking_days >= max_days and score < 72:
        action, position = "清仓", 0
        reasons = [
            f"已跟踪 {tracking_days} 天，超过{mode_name}默认观察周期",
            f"当前评分 {score:.1f} 未能维持强势",
        ]
    elif return_value >= profit_lock and score < 76:
        action, position = "减仓", 25
        reasons = [
            f"发现后已有 {return_value:+.2f}% 浮盈，进入保护利润区",
            f"当前评分 {score:.1f}，动能不足以支持满仓继续持有",
        ]
    elif score >= 82 and confidence >= 72 and -2 <= return_value <= 8:
        action, position = "加仓", 60
        reasons = [
            f"当前{mode_name}评分 {score:.1f} 且置信度 {confidence:.1f}%",
            f"发现后涨跌 {return_value:+.2f}%，尚未明显偏离关注区",
        ]
    elif score >= 70:
        action, position = "继续持有", 50
        reasons = [
            f"当前{mode_name}评分 {score:.1f}，核心信号仍成立",
            f"发现后涨跌 {return_value:+.2f}%，暂未触发退出条件",
        ]
    else:
        action, position = "减仓", 25
        reasons = [
            f"当前{mode_name}评分降至 {score:.1f}，信号完整度下降",
            "保留少量观察仓，等待趋势重新确认",
        ]

    return {
        "action": action,
        "position_pct": position,
        "confidence": min(confidence, 90.0),
        "current_score": score,
        "current_recommendation": recommendation,
        "reasons": reasons,
        "risks": risks[:3] or ["市场环境与个股信号可能在下一交易日发生变化"],
        "invalidation": (
            f"跌破发现价止损线 {stop_line:.1f}%、当前评分低于 55，"
            "或出现停牌、涨跌停无法成交及重大数据异常"
        ),
    }


def _save_advice(
    session,
    row: RankingDiscovery,
    advice_date: date,
    current_price: float | None,
    return_pct: float | None,
    action: dict[str, Any],
    meta: dict[str, Any],
) -> None:
    if advice_date <= date.fromisoformat(row.discovery_date):
        return
    snapshot = session.scalar(
        select(RankingAdviceSnapshot).where(
            RankingAdviceSnapshot.discovery_id == row.id,
            RankingAdviceSnapshot.advice_date == advice_date.isoformat(),
        )
    )
    values = {
        "current_price": current_price,
        "return_pct": return_pct,
        "current_score": action["current_score"],
        "current_recommendation": action["current_recommendation"],
        "action": action["action"],
        "position_pct": action["position_pct"],
        "confidence": action["confidence"],
        "reasons_json": json.dumps(action["reasons"], ensure_ascii=False),
        "risks_json": json.dumps(action["risks"], ensure_ascii=False),
        "invalidation": action["invalidation"],
        "quote_time": meta.get("quote_time"),
        "source": str(meta.get("source") or "未知"),
        "model_version": ADVICE_MODEL_VERSION,
        "updated_at": datetime.now(SHANGHAI).replace(tzinfo=None),
    }
    if snapshot is None:
        session.add(
            RankingAdviceSnapshot(
                discovery_id=row.id,
                advice_date=advice_date.isoformat(),
                created_at=datetime.now(SHANGHAI).replace(tzinfo=None),
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(snapshot, key, value)


def _mode_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in items if item["return_pct"] is not None]
    if not valid:
        return {
            "count": len(items),
            "priced_count": 0,
            "average_return_pct": None,
            "positive_count": 0,
            "best": None,
            "worst": None,
        }
    best = max(valid, key=lambda item: item["return_pct"])
    worst = min(valid, key=lambda item: item["return_pct"])
    return {
        "count": len(items),
        "priced_count": len(valid),
        "average_return_pct": round(
            sum(item["return_pct"] for item in valid) / len(valid), 2
        ),
        "positive_count": sum(item["return_pct"] > 0 for item in valid),
        "best": {"code": best["code"], "name": best["name"], "return_pct": best["return_pct"]},
        "worst": {"code": worst["code"], "name": worst["name"], "return_pct": worst["return_pct"]},
    }


def auto_backtest(days: int = 5) -> dict[str, Any]:
    """留存今日榜单，并给历史发现标的生成当日操作建议。"""
    repaired_discoveries = repair_repeated_cached_discoveries()
    opportunity_lists = {
        mode: market_service.opportunities(mode, limit=500) for mode in MODES
    }
    for mode, opportunities in opportunity_lists.items():
        capture_mode_snapshot(mode, opportunities[:3])
    opportunity_maps = {
        mode: {str(item["code"]): item for item in items}
        for mode, items in opportunity_lists.items()
    }

    quotes, current_meta = data_source.get_spot_quotes()
    quote_map = {str(item["code"]): item for item in quotes}
    advice_date = _meta_date(current_meta)
    training_cycle = process_training_cycle(opportunity_lists, quotes, current_meta)

    with SessionLocal.begin() as session:
        discovery_dates = list(
            session.scalars(
                select(RankingDiscovery.discovery_date)
                .distinct()
                .order_by(desc(RankingDiscovery.discovery_date))
                .limit(days)
            )
        )
        rows = (
            list(
                session.scalars(
                    select(RankingDiscovery)
                    .where(RankingDiscovery.discovery_date.in_(discovery_dates))
                    .order_by(
                        desc(RankingDiscovery.discovery_date),
                        RankingDiscovery.mode,
                        RankingDiscovery.rank,
                    )
                )
            )
            if discovery_dates
            else []
        )
        version_map = discovery_version_map(rows)
        items: list[dict[str, Any]] = []
        for row in rows:
            quote = quote_map.get(row.code)
            current_price = float(quote["price"]) if quote and quote.get("price") else None
            return_pct = (
                round((current_price / row.discovery_price - 1) * 100, 2)
                if current_price is not None and row.discovery_price > 0
                else None
            )
            discovered = date.fromisoformat(row.discovery_date)
            tracking_days = max((advice_date - discovered).days, 0) + 1
            current = opportunity_maps[row.mode].get(row.code)
            action = _daily_action(row, current, current_price, return_pct, tracking_days)
            if advice_date <= discovered:
                action = {
                    **action,
                    "action": "等待次日评估",
                    "position_pct": 0,
                    "reasons": ["发现当日只记录榜单快照，下一交易日起生成持仓建议"],
                }
            _save_advice(
                session, row, advice_date, current_price, return_pct, action, current_meta
            )
            items.append(
                {
                    "id": row.id,
                    "discovery_date": row.discovery_date,
                    "mode": row.mode,
                    "rank": row.rank,
                    "code": row.code,
                    "name": row.name,
                    "industry": row.industry,
                    "discovery_price": row.discovery_price,
                    "current_price": current_price,
                    "return_pct": return_pct,
                    "tracking_days": tracking_days,
                    "discovery_score": row.discovery_score,
                    "strategy_version": version_map.get(row.id, f"{row.mode}-v1.0"),
                    "recommendation": row.recommendation,
                    "confidence": row.confidence,
                    "reasons": json.loads(row.reasons_json),
                    "risks": json.loads(row.risks_json),
                    "quote_time": row.quote_time,
                    "source": row.source,
                    "current_quote_time": current_meta.get("quote_time"),
                    "current_source": current_meta.get("source"),
                    "is_cached": bool(current_meta.get("is_cached")),
                    "action_date": advice_date.isoformat(),
                    "action_advice": action["action"],
                    "action_position_pct": action["position_pct"],
                    "current_score": action["current_score"],
                    "current_recommendation": action["current_recommendation"],
                    "action_confidence": action["confidence"],
                    "action_reasons": action["reasons"],
                    "action_risks": action["risks"],
                    "action_invalidation": action["invalidation"],
                    "advice_history": [],
                }
            )
        session.flush()
        histories = list(
            session.scalars(
                select(RankingAdviceSnapshot)
                .where(RankingAdviceSnapshot.discovery_id.in_([row.id for row in rows]))
                .order_by(
                    RankingAdviceSnapshot.discovery_id,
                    desc(RankingAdviceSnapshot.advice_date),
                )
            )
        ) if rows else []
        history_map: dict[int, list[dict[str, Any]]] = {}
        for snapshot in histories:
            history_map.setdefault(snapshot.discovery_id, []).append(
                {
                    "advice_date": snapshot.advice_date,
                    "current_price": snapshot.current_price,
                    "return_pct": snapshot.return_pct,
                    "current_score": snapshot.current_score,
                    "action": snapshot.action,
                    "position_pct": snapshot.position_pct,
                    "confidence": snapshot.confidence,
                    "reasons": json.loads(snapshot.reasons_json),
                    "risks": json.loads(snapshot.risks_json),
                    "invalidation": snapshot.invalidation,
                    "quote_time": snapshot.quote_time,
                    "source": snapshot.source,
                }
            )
        for item in items:
            item["advice_history"] = history_map.get(item["id"], [])

    return {
        "days": days,
        "available_dates": discovery_dates,
        "items": items,
        "summaries": {
            mode: _mode_summary([item for item in items if item["mode"] == mode])
            for mode in MODES
        },
        "meta": current_meta,
        "training_cycle": {
            **training_cycle,
            "repaired_discoveries": repaired_discoveries,
        },
        "strategy_optimization": ranking_strategy_status(),
        "history_note": (
            "自动回测只展示功能启用后真实保存的发现快照，不会伪造启用前历史；"
            "从下一交易日起保存每日操作建议。"
        ),
    }
