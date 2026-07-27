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
