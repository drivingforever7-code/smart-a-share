from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import board_pool_service as service
from app.database import Base, BoardPoolEvent


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    monkeypatch.setattr(service, "MIN_PROBABILITY", {"streak": 0.0, "down_repair": 0.0})
    return session_local


def _up_rows(count: int = 12):
    return [{
        "代码": f"{index:06d}", "名称": f"连板{index}", "所属行业": "测试行业",
        "连板数": 2 + index % 3, "首次封板时间": "093000", "炸板次数": index % 2,
        "封板资金": 80_000_000, "成交额": 600_000_000,
        "换手率": 12, "流通市值": 8_000_000_000,
    } for index in range(1, count + 1)]


def _down_rows(count: int = 12):
    return [{
        "代码": f"{index + 100:06d}", "名称": f"跌停{index}", "所属行业": "测试行业",
        "连续跌停": 1, "封单资金": 20_000_000, "成交额": 500_000_000,
        "换手率": 8, "流通市值": 12_000_000_000,
    } for index in range(1, count + 1)]


def test_each_pool_saves_at_most_top_ten(isolated_database, monkeypatch):
    monkeypatch.setattr(service, "_fetch", lambda _: (_up_rows(), _down_rows()))
    result = service.capture_board_pools("2026-08-04")
    assert result["created"] == 20
    with isolated_database() as session:
        streak = list(session.scalars(select(BoardPoolEvent).where(BoardPoolEvent.pool_type == "streak")))
        down = list(session.scalars(select(BoardPoolEvent).where(BoardPoolEvent.pool_type == "down_repair")))
    assert len(streak) == 10
    assert len(down) == 10
    assert [row.rank for row in streak] == list(range(1, 11))


def test_next_day_finalizes_previous_predictions(isolated_database, monkeypatch):
    monkeypatch.setattr(service, "_fetch", lambda _: (_up_rows(1), _down_rows(1)))
    service.capture_board_pools("2026-08-04")
    monkeypatch.setattr(service, "_fetch", lambda _: (_up_rows(1), []))
    result = service.capture_board_pools("2026-08-05")
    assert result["finalized"] == 2
    with isolated_database() as session:
        previous = list(session.scalars(select(BoardPoolEvent).where(BoardPoolEvent.trade_date == "2026-08-04")))
    assert {row.outcome for row in previous} == {"success"}
