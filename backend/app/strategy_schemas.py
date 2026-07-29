from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class StrategyCondition(BaseModel):
    left: str
    operator: Literal[
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "cross_above",
        "cross_below",
        "is_true",
    ]
    right_type: Literal["value", "indicator"] = "value"
    right: float | str | list[float] | None = None

    @model_validator(mode="after")
    def validate_right(self):
        if self.operator == "between":
            if not isinstance(self.right, list) or len(self.right) != 2:
                raise ValueError("区间条件必须填写两个数值")
        elif self.operator != "is_true" and self.right is None:
            raise ValueError("这个条件需要比较值")
        return self


class RiskConfig(BaseModel):
    stop_loss_pct: float = Field(default=7, gt=0, le=50)
    take_profit_pct: float = Field(default=15, gt=0, le=200)
    max_holding_days: int = Field(default=10, ge=1, le=250)
    commission_pct: float = Field(default=0.1, ge=0, le=2)
    slippage_pct: float = Field(default=0.05, ge=0, le=2)
    stamp_duty_pct: float = Field(default=0.05, ge=0, le=2)


class StrategyComponent(BaseModel):
    strategy_id: str
    weight: float = Field(gt=0, le=100)


class RuleConfig(BaseModel):
    entry_logic: Literal["all", "any"] = "all"
    entry_conditions: list[StrategyCondition] = Field(min_length=1)
    exit_logic: Literal["all", "any"] = "any"
    exit_conditions: list[StrategyCondition] = Field(default_factory=list)
    risk: RiskConfig = Field(default_factory=RiskConfig)


class CompositeConfig(BaseModel):
    components: list[StrategyComponent] = Field(min_length=2)
    trigger_score: float = Field(default=50, ge=1, le=100)
    exit_score: float = Field(default=50, ge=1, le=100)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @model_validator(mode="after")
    def validate_weights(self):
        total = sum(component.weight for component in self.components)
        if abs(total - 100) > 0.01:
            raise ValueError(f"组合策略权重合计必须为 100%，当前为 {total:.2f}%")
        ids = [component.strategy_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("组合策略不能重复选择同一个子策略")
        return self


class StrategyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    category: Literal["rule", "composite"]
    mode: Literal["short", "swing"]
    description: str = Field(default="", max_length=240)
    icon: str = Field(default="📐", max_length=12)
    config: dict[str, Any]

    @model_validator(mode="after")
    def validate_config(self):
        if self.category == "rule":
            RuleConfig.model_validate(self.config)
        else:
            CompositeConfig.model_validate(self.config)
        return self


class StrategyBacktestRequest(BaseModel):
    code: str
    strategy_id: str | None = None
    preset: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    max_holding_days: int | None = Field(default=None, ge=1, le=250)
    holding_days: int | None = Field(default=None, ge=1, le=250)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=50)
    take_profit_pct: float | None = Field(default=None, gt=0, le=200)
    commission_pct: float | None = Field(default=None, ge=0, le=2)
    slippage_pct: float | None = Field(default=None, ge=0, le=2)
    stamp_duty_pct: float | None = Field(default=None, ge=0, le=2)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip()
        if len(value) != 6 or not value.isdigit():
            raise ValueError("股票代码必须是 6 位数字")
        return value

    @model_validator(mode="after")
    def validate_strategy(self):
        if not self.strategy_id and not self.preset:
            raise ValueError("请选择一个策略")
        return self

    @property
    def resolved_strategy_id(self) -> str:
        return self.strategy_id or self.preset or ""

    def risk_overrides(self) -> dict[str, float | int]:
        result: dict[str, float | int] = {}
        holding = self.max_holding_days or self.holding_days
        if holding is not None:
            result["max_holding_days"] = holding
        for key in [
            "stop_loss_pct",
            "take_profit_pct",
            "commission_pct",
            "slippage_pct",
            "stamp_duty_pct",
        ]:
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result
