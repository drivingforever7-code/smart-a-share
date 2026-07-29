from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from .database import RankingDiscovery, SessionLocal
from .market_service import market_service
from .reliable_data_source import data_source


MODES = ("short", "swing")


def _snapshot_date(items: list[dict[str, Any]]) -> date:
    """优先使用行情日期，禁止把服务器时间冒充交易日期。"""
    if not items:
        raise ValueError("没有可用于留存的榜单数据")
    meta = items[0].get("meta") or {}
    for key in ("quote_time", "fetched_at"):
        value = str(meta.get(key) or "").strip()
        if len(value) >= 10:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    raise ValueError("榜单缺少有效行情日期，无法生成发现快照")


def capture_mode_snapshot(mode: str, items: list[dict[str, Any]]) -> bool:
    """首次看到某交易日榜单时冻结前三，之后不回写历史排名。"""
    if mode not in MODES or len(items) < 3:
        return False
    top_three = items[:3]
    if any(not item.get("price") or float(item["price"]) <= 0 for item in top_three):
        return False

    discovery_date = _snapshot_date(top_three)
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
                        source=str(meta.get("source") or "未知"),
                        discovered_at=datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None),
                    )
                )
    except IntegrityError:
        # 并发请求可能同时尝试写入，唯一约束保证只保留第一份真实快照。
        return False
    return True


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
            sum(item["return_pct"] for item in valid) / len(valid),
            2,
        ),
        "positive_count": sum(item["return_pct"] > 0 for item in valid),
        "best": {
            "code": best["code"],
            "name": best["name"],
            "return_pct": best["return_pct"],
        },
        "worst": {
            "code": worst["code"],
            "name": worst["name"],
            "return_pct": worst["return_pct"],
        },
    }


def auto_backtest(days: int = 5) -> dict[str, Any]:
    """留存今日榜单并返回最近若干真实发现日截至当前的表现。"""
    for mode in MODES:
        opportunities = market_service.opportunities(mode, limit=3)
        capture_mode_snapshot(mode, opportunities)

    quotes, current_meta = data_source.get_spot_quotes()
    quote_map = {str(item["code"]): item for item in quotes}

    with SessionLocal() as session:
        discovery_dates = list(
            session.scalars(
                select(RankingDiscovery.discovery_date)
                .distinct()
                .order_by(desc(RankingDiscovery.discovery_date))
                .limit(days)
            )
        )
        if discovery_dates:
            rows = list(
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
        else:
            rows = []

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
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
                "tracking_days": max((today - discovered).days, 0) + 1,
                "discovery_score": row.discovery_score,
                "recommendation": row.recommendation,
                "confidence": row.confidence,
                "reasons": json.loads(row.reasons_json),
                "risks": json.loads(row.risks_json),
                "quote_time": row.quote_time,
                "source": row.source,
                "current_quote_time": current_meta.get("quote_time"),
                "current_source": current_meta.get("source"),
                "is_cached": bool(current_meta.get("is_cached")),
            }
        )

    return {
        "days": days,
        "available_dates": discovery_dates,
        "items": items,
        "summaries": {
            mode: _mode_summary([item for item in items if item["mode"] == mode])
            for mode in MODES
        },
        "meta": current_meta,
        "history_note": (
            "自动回测只展示功能启用后真实保存的发现快照，不会伪造启用前的历史排名。"
        ),
    }
