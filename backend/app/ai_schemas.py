from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AiAnalysisRequest(BaseModel):
    code: str
    depth: Literal["quick", "standard", "deep"] = "standard"

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip()
        if len(value) != 6 or not value.isdigit():
            raise ValueError("股票代码必须是 6 位数字")
        return value


class AiHistoryQuery(BaseModel):
    code: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class TradeReviewRequest(BaseModel):
    description: str = Field(min_length=5, max_length=4000)
    code: str | None = None
    trade_date: str | None = None
    action: Literal["买入", "卖出", "加仓", "清仓", "其他"] = "其他"
    price: float | None = Field(default=None, gt=0)
    position_pct: float | None = Field(default=None, ge=0, le=100)

    @field_validator("code")
    @classmethod
    def validate_optional_code(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if len(value) != 6 or not value.isdigit():
            raise ValueError("股票代码必须是 6 位数字")
        return value
