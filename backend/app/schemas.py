from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ScoreMode = Literal["short", "swing"]


class ScreenerRequest(BaseModel):
    mode: ScoreMode = "short"
    preset: str | None = None
    boards: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    min_score: float | None = 0
    min_change_pct: float | None = None
    max_change_pct: float | None = None
    min_turnover_rate: float | None = None
    min_volume_ratio: float | None = None
    min_pe: float | None = None
    max_pe: float | None = None
    min_pb: float | None = None
    max_pb: float | None = None
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    include_st: bool = False
    include_new: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=200)
    sort_by: str = "score"
    sort_order: Literal["asc", "desc"] = "desc"


class BacktestRequest(BaseModel):
    code: str
    preset: str
    start_date: str | None = None
    end_date: str | None = None
    holding_days: int = Field(default=10, ge=1, le=120)
    stop_loss_pct: float = Field(default=7, gt=0, le=50)
    take_profit_pct: float = Field(default=15, gt=0, le=200)
    commission_pct: float = Field(default=0.1, ge=0, le=2)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip()
        if len(value) != 6 or not value.isdigit():
            raise ValueError("股票代码必须是 6 位数字")
        return value
