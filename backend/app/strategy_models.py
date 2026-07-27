from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class StrategyDefinition(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    category: Mapped[str] = mapped_column(String(20), default="rule")
    mode: Mapped[str] = mapped_column(String(10), default="short")
    description: Mapped[str] = mapped_column(String(240), default="")
    icon: Mapped[str] = mapped_column(String(12), default="📐")
    config_json: Mapped[str] = mapped_column(Text)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint("code", "report_date", name="uq_financial_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    report_date: Mapped[str] = mapped_column(String(10), index=True)
    available_date: Mapped[str] = mapped_column(String(10), index=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_annualized: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_value_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="AKShare / 新浪财经")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
