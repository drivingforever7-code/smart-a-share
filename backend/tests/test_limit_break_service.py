from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import limit_break_service as service
from app.database import Base, LimitBreakEvent


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    monkeypatch.setattr(
        service,
        "_now",
        lambda: datetime(2026, 7, 30, 11, 35, 0),
    )
    return session_local


def broken_pool() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "测试炸板",
                "涨跌幅": 8.5,
                "最新价": 10.85,
                "涨停价": 11.0,
                "成交额": 500_000_000,
                "流通市值": 8_000_000_000,
                "总市值": 9_000_000_000,
                "换手率": 9.5,
                "涨速": 1.2,
                "首次封板时间": "094500",
                "炸板次数": 2,
                "涨停统计": "3/2",
                "振幅": 11.2,
                "所属行业": "测试行业",
            }
        ]
    )


def sealed_pool(resealed: bool = False) -> pd.DataFrame:
    rows = [
        {
            "代码": "600001",
            "名称": "普通涨停",
            "涨跌幅": 10.0,
            "最新价": 12.0,
            "成交额": 300_000_000,
            "流通市值": 7_000_000_000,
            "总市值": 8_000_000_000,
            "换手率": 8.0,
            "封板资金": 50_000_000,
            "首次封板时间": "100000",
            "最后封板时间": "100000",
            "炸板次数": 0,
            "涨停统计": "1/1",
            "连板数": 1,
            "所属行业": "测试行业",
        }
    ]
    if resealed:
        rows.append(
            {
                "代码": "000001",
                "名称": "测试炸板",
                "涨跌幅": 10.0,
                "最新价": 11.0,
                "成交额": 650_000_000,
                "流通市值": 8_000_000_000,
                "总市值": 9_000_000_000,
                "换手率": 12.0,
                "封板资金": 40_000_000,
                "首次封板时间": "094500",
                "最后封板时间": "143000",
                "炸板次数": 2,
                "涨停统计": "3/2",
                "连板数": 2,
                "所属行业": "测试行业",
            }
        )
    return pd.DataFrame(rows)


def test_intraday_prediction_is_frozen_and_ranked(isolated_database, monkeypatch):
    monkeypatch.setattr(
        service,
        "_fetch_pools",
        lambda _: (broken_pool(), sealed_pool()),
    )
    first = service.capture_limit_breaks("midday", "2026-07-30")
    second = service.capture_limit_breaks("midday", "2026-07-30")

    assert first["created"] == 1
    assert second["created"] == 0
    with isolated_database() as session:
        row = session.scalar(select(LimitBreakEvent))
        assert row is not None
        assert row.eligible_for_evaluation is True
        assert 0 <= row.predicted_probability <= 100
        assert row.outcome == "pending"


def test_close_finalizes_reseal_without_rewriting_prediction(
    isolated_database,
    monkeypatch,
):
    pools = {"value": (broken_pool(), sealed_pool())}
    monkeypatch.setattr(service, "_fetch_pools", lambda _: pools["value"])
    service.capture_limit_breaks("midday", "2026-07-30")

    pools["value"] = (pd.DataFrame(columns=broken_pool().columns), sealed_pool(True))
    service.capture_limit_breaks("close", "2026-07-30")

    result = service.limit_break_research(days=5, refresh=False)
    item = next(row for row in result["items"] if row["code"] == "000001")
    assert item["outcome"] == "resealed"
    assert item["prediction_stage"] == "midday"
    assert item["eligible_for_evaluation"] is True
    assert item["review"]["prediction_correct"] in (True, False)
    assert result["model_stats"]["sample_count"] == 1


def test_research_groups_recent_days_and_keeps_history_in_metrics(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setattr(service, "_fetch_pools", lambda _: (broken_pool(), sealed_pool()))
    for trade_date in ("2026-07-30", "2026-07-31"):
        service.capture_limit_breaks("midday", trade_date)
        service.capture_limit_breaks("close", trade_date)

    result = service.limit_break_research(days=10, refresh=False)

    assert result["display_date"] == "2026-07-31"
    assert {item["trade_date"] for item in result["items"]} == {
        "2026-07-30",
        "2026-07-31",
    }
    assert result["model_stats"]["sample_count"] == 2
    assert {review["trade_date"] for review in result["daily_reviews"]} == {
        "2026-07-30",
        "2026-07-31",
    }


def test_close_only_capture_creates_display_records_without_evaluation(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setattr(service, "_fetch_pools", lambda _: (broken_pool(), sealed_pool(True)))

    capture = service.capture_limit_breaks("close", "2026-08-06")
    result = service.limit_break_research(days=5, refresh=False)

    assert capture["created"] > 0
    assert result["display_date"] == "2026-08-06"
    assert result["items"]
    assert all(item["prediction_stage"] == "close" for item in result["items"])
    assert all(item["eligible_for_evaluation"] is False for item in result["items"])
    assert result["model_stats"]["sample_count"] == 0