from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import ranking_archive_service as service
from app.database import Base, RankingDiscovery


@pytest.fixture()
def isolated_database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(service, "SessionLocal", session_local)
    return session_local


def archive_payload():
    items = []
    for mode in ("short", "swing"):
        for rank in range(1, 4):
            items.append(
                {
                    "discovery_date": "2026-08-28",
                    "mode": mode,
                    "rank": rank,
                    "code": f"{rank if mode == 'short' else rank + 3:06d}",
                    "name": f"sample-{mode}-{rank}",
                    "industry": None,
                    "discovery_price": 10 + rank,
                    "discovery_score": 70 + rank,
                    "recommendation": "watch",
                    "confidence": 70,
                    "reasons": ["verified"],
                    "risks": [],
                    "quote_time": "2026-08-28 15:00:00",
                    "source": "test",
                }
            )
    return {
        "schema_version": 1,
        "trade_date": "2026-08-28",
        "captured_at": datetime.now().isoformat(),
        "items": items,
    }


def test_archive_import_is_complete_and_idempotent(isolated_database):
    payload = archive_payload()
    assert service.import_ranking_archive(payload) == 6
    assert service.import_ranking_archive(payload) == 0
    with isolated_database() as session:
        rows = list(session.scalars(select(RankingDiscovery)))
    assert len(rows) == 6
    assert {(row.mode, row.rank) for row in rows} == {
        (mode, rank) for mode in ("short", "swing") for rank in range(1, 4)
    }


def test_archive_rejects_incomplete_day(isolated_database):
    payload = archive_payload()
    payload["items"].pop()
    with pytest.raises(ValueError, match="ranks 1-3"):
        service.import_ranking_archive(payload)