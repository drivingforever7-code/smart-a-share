from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from .database import SessionLocal
from .strategy_catalog_v2 import (
    BUILTIN_STRATEGIES,
    INDICATORS,
    LEGACY_BUILTIN_IDS,
    LEGACY_REPLACEMENTS,
    OPERATORS,
)
from .strategy_models import StrategyDefinition
from .strategy_schemas import CompositeConfig, RuleConfig, StrategyPayload


FUNDAMENTAL_INDICATORS = {"pe", "pb", "roe", "revenue_growth", "profit_growth"}


class StrategyNotFoundError(ValueError):
    pass


def initialize_strategy_catalog() -> None:
    """播种新版策略，并把自定义组合中的旧策略引用迁移到替代策略。"""
    with SessionLocal.begin() as session:
        existing = set(session.scalars(select(StrategyDefinition.id)).all())
        for item in BUILTIN_STRATEGIES:
            if item["id"] in existing:
                continue
            session.add(
                StrategyDefinition(
                    id=item["id"],
                    name=item["name"],
                    category=item["category"],
                    mode=item["mode"],
                    description=item["description"],
                    icon=item["icon"],
                    config_json=json.dumps(item["config"], ensure_ascii=False),
                    is_builtin=True,
                )
            )

        custom_composites = session.scalars(
            select(StrategyDefinition).where(
                StrategyDefinition.category == "composite",
                StrategyDefinition.is_builtin.is_(False),
            )
        ).all()
        for composite in custom_composites:
            config = json.loads(composite.config_json)
            changed = False
            for component in config.get("components", []):
                old_id = component.get("strategy_id")
                if old_id in LEGACY_REPLACEMENTS:
                    component["strategy_id"] = LEGACY_REPLACEMENTS[old_id]
                    changed = True
            if changed:
                # 多个旧策略可能映射到同一新版策略，合并其权重。
                merged: dict[str, float] = {}
                for component in config.get("components", []):
                    child_id = component["strategy_id"]
                    merged[child_id] = merged.get(child_id, 0) + float(component["weight"])
                config["components"] = [
                    {"strategy_id": child_id, "weight": weight}
                    for child_id, weight in merged.items()
                ]
                composite.config_json = json.dumps(config, ensure_ascii=False)
                composite.updated_at = datetime.now()

        legacy_rows = session.scalars(
            select(StrategyDefinition).where(
                StrategyDefinition.id.in_(LEGACY_BUILTIN_IDS),
                StrategyDefinition.is_builtin.is_(True),
            )
        ).all()
        for row in legacy_rows:
            session.delete(row)


def strategy_catalog_metadata() -> dict[str, Any]:
    return {"indicators": INDICATORS, "operators": OPERATORS}


def list_strategies() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(StrategyDefinition).order_by(
                StrategyDefinition.is_builtin.desc(),
                StrategyDefinition.created_at.asc(),
            )
        ).all()
        return [_serialize(row) for row in rows]


def get_strategy(strategy_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(StrategyDefinition, strategy_id)
        if row is None:
            raise StrategyNotFoundError(f"没有找到策略 {strategy_id}")
        return _serialize(row)


def create_strategy(payload: StrategyPayload) -> dict[str, Any]:
    strategy_id = f"custom_{uuid.uuid4().hex[:12]}"
    validated_config = _validated_config(payload)
    with SessionLocal.begin() as session:
        row = StrategyDefinition(
            id=strategy_id,
            name=payload.name,
            category=payload.category,
            mode=payload.mode,
            description=payload.description,
            icon=payload.icon,
            config_json=json.dumps(validated_config, ensure_ascii=False),
            is_builtin=False,
        )
        session.add(row)
    return get_strategy(strategy_id)


def update_strategy(strategy_id: str, payload: StrategyPayload) -> dict[str, Any]:
    validated_config = _validated_config(payload)
    if payload.category == "composite":
        _validate_component_references(strategy_id, validated_config)
    with SessionLocal.begin() as session:
        row = session.get(StrategyDefinition, strategy_id)
        if row is None:
            raise StrategyNotFoundError(f"没有找到策略 {strategy_id}")
        row.name = payload.name
        row.category = payload.category
        row.mode = payload.mode
        row.description = payload.description
        row.icon = payload.icon
        row.config_json = json.dumps(validated_config, ensure_ascii=False)
        row.updated_at = datetime.now()
    return get_strategy(strategy_id)


def copy_strategy(strategy_id: str) -> dict[str, Any]:
    original = get_strategy(strategy_id)
    payload = StrategyPayload(
        name=f"{original['name']} 副本",
        category=original["category"],
        mode=original["mode"],
        description=original["description"],
        icon=original["icon"],
        config=original["config"],
    )
    return create_strategy(payload)


def reset_builtin_strategy(strategy_id: str) -> dict[str, Any]:
    default = next(
        (item for item in BUILTIN_STRATEGIES if item["id"] == strategy_id),
        None,
    )
    if default is None:
        raise StrategyNotFoundError("只有内置策略可以恢复默认")
    payload = StrategyPayload(
        name=default["name"],
        category=default["category"],
        mode=default["mode"],
        description=default["description"],
        icon=default["icon"],
        config=default["config"],
    )
    return update_strategy(strategy_id, payload)


def delete_strategy(strategy_id: str) -> None:
    with SessionLocal.begin() as session:
        row = session.get(StrategyDefinition, strategy_id)
        if row is None:
            raise StrategyNotFoundError(f"没有找到策略 {strategy_id}")
        if row.is_builtin:
            raise ValueError("内置策略不能删除，可以恢复默认参数")
        all_rows = session.scalars(
            select(StrategyDefinition).where(StrategyDefinition.category == "composite")
        ).all()
        for composite in all_rows:
            config = json.loads(composite.config_json)
            if any(
                item.get("strategy_id") == strategy_id
                for item in config.get("components", [])
            ):
                raise ValueError(f"策略正在被组合“{composite.name}”使用，不能删除")
        session.delete(row)


def strategy_requires_fundamentals(
    strategy: dict[str, Any],
    *,
    visited: set[str] | None = None,
) -> bool:
    visited = visited or set()
    if strategy["id"] in visited:
        return False
    visited.add(strategy["id"])
    if strategy["category"] == "rule":
        conditions = [
            *strategy["config"].get("entry_conditions", []),
            *strategy["config"].get("exit_conditions", []),
        ]
        return any(condition.get("left") in FUNDAMENTAL_INDICATORS for condition in conditions)
    for component in strategy["config"].get("components", []):
        child = get_strategy(component["strategy_id"])
        if strategy_requires_fundamentals(child, visited=visited):
            return True
    return False


def _validated_config(payload: StrategyPayload) -> dict[str, Any]:
    if payload.category == "rule":
        return RuleConfig.model_validate(payload.config).model_dump()
    config = CompositeConfig.model_validate(payload.config).model_dump()
    _validate_component_references(None, config)
    return config


def _validate_component_references(
    strategy_id: str | None,
    config: dict[str, Any],
) -> None:
    ids = [item["strategy_id"] for item in config.get("components", [])]
    if strategy_id and strategy_id in ids:
        raise ValueError("组合策略不能包含自己")
    with SessionLocal() as session:
        existing = set(
            session.scalars(
                select(StrategyDefinition.id).where(StrategyDefinition.id.in_(ids))
            ).all()
        )
    missing = [item for item in ids if item not in existing]
    if missing:
        raise ValueError(f"组合中存在未找到的策略：{', '.join(missing)}")


def _serialize(row: StrategyDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "category": row.category,
        "mode": row.mode,
        "description": row.description,
        "icon": row.icon,
        "config": json.loads(row.config_json),
        "is_builtin": row.is_builtin,
        "created_at": row.created_at.isoformat(timespec="seconds"),
        "updated_at": row.updated_at.isoformat(timespec="seconds"),
    }


MARKET_INDICATORS = {"market_regime_up", "market_momentum20"}


def strategy_requires_market_regime(
    strategy: dict[str, Any],
    *,
    visited: set[str] | None = None,
) -> bool:
    visited = set(visited or set())
    if strategy["id"] in visited:
        return False
    visited.add(strategy["id"])
    if strategy["category"] == "rule":
        conditions = [
            *strategy["config"].get("entry_conditions", []),
            *strategy["config"].get("exit_conditions", []),
        ]
        return any(condition.get("left") in MARKET_INDICATORS for condition in conditions)
    return any(
        strategy_requires_market_regime(
            get_strategy(component["strategy_id"]),
            visited=visited,
        )
        for component in strategy["config"].get("components", [])
    )
