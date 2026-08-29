from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from sqlalchemy import select

from .database import RankingDiscovery, SessionLocal

ARCHIVE_SCHEMA_VERSION = 1
ARCHIVE_DIR = Path(__file__).resolve().parents[1] / "ranking_archives"
DEFAULT_REMOTE_INDEX_URL = (
    "https://raw.githubusercontent.com/drivingforever7-code/"
    "smart-a-share/main/backend/ranking_archives/index.json"
)
_ARCHIVE_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
_SYNC_LOCK = threading.Lock()
_REMOTE_SYNC_COOLDOWN_SECONDS = 300
_next_remote_sync_at = 0.0
_packaged_loaded = False


def _iso_date(value: Any) -> str:
    result = str(value or "").strip()[:10]
    date.fromisoformat(result)
    return result


def _normalise_archive(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if int(payload.get("schema_version") or 0) != ARCHIVE_SCHEMA_VERSION:
        raise ValueError("unsupported ranking archive schema")
    trade_date = _iso_date(payload.get("trade_date"))
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("ranking archive items must be a list")

    items: list[dict[str, Any]] = []
    groups: dict[str, list[int]] = {"short": [], "swing": []}
    codes_by_mode: dict[str, set[str]] = {"short": set(), "swing": set()}
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("invalid ranking archive item")
        if _iso_date(raw.get("discovery_date")) != trade_date:
            raise ValueError("archive item date does not match trade date")
        mode = str(raw.get("mode") or "")
        if mode not in groups:
            raise ValueError("invalid ranking archive mode")
        rank = int(raw.get("rank") or 0)
        code = str(raw.get("code") or "").strip()
        if rank not in {1, 2, 3} or len(code) != 6 or not code.isdigit():
            raise ValueError("invalid ranking archive rank or code")
        if code in codes_by_mode[mode]:
            raise ValueError("duplicate code in ranking archive mode")
        discovery_price = float(raw.get("discovery_price") or 0)
        if discovery_price <= 0:
            raise ValueError("invalid ranking archive discovery price")
        groups[mode].append(rank)
        codes_by_mode[mode].add(code)
        items.append(
            {
                "discovery_date": trade_date,
                "mode": mode,
                "rank": rank,
                "code": code,
                "name": str(raw.get("name") or code)[:40],
                "industry": (str(raw["industry"])[:60] if raw.get("industry") else None),
                "discovery_price": discovery_price,
                "discovery_score": float(raw.get("discovery_score") or 0),
                "recommendation": str(raw.get("recommendation") or "建议观察")[:30],
                "confidence": float(raw.get("confidence") or 0),
                "reasons": [str(value) for value in (raw.get("reasons") or [])],
                "risks": [str(value) for value in (raw.get("risks") or [])],
                "quote_time": (str(raw["quote_time"])[:32] if raw.get("quote_time") else None),
                "source": str(raw.get("source") or "GitHub ranking archive")[:30],
            }
        )
    if any(sorted(ranks) != [1, 2, 3] for ranks in groups.values()):
        raise ValueError("archive must contain short and swing ranks 1-3")
    return trade_date, sorted(items, key=lambda item: (item["mode"], item["rank"]))


def import_ranking_archive(payload: dict[str, Any]) -> int:
    trade_date, items = _normalise_archive(payload)
    captured_at_text = str(payload.get("captured_at") or "")
    try:
        captured_at = datetime.fromisoformat(captured_at_text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        captured_at = datetime.now()

    imported = 0
    with SessionLocal.begin() as session:
        existing = set(
            session.execute(
                select(RankingDiscovery.mode, RankingDiscovery.rank).where(
                    RankingDiscovery.discovery_date == trade_date
                )
            ).all()
        )
        for item in items:
            key = (item["mode"], item["rank"])
            if key in existing:
                continue
            session.add(
                RankingDiscovery(
                    discovery_date=item["discovery_date"],
                    mode=item["mode"],
                    rank=item["rank"],
                    code=item["code"],
                    name=item["name"],
                    industry=item["industry"],
                    discovery_price=item["discovery_price"],
                    discovery_score=item["discovery_score"],
                    recommendation=item["recommendation"],
                    confidence=item["confidence"],
                    reasons_json=json.dumps(item["reasons"], ensure_ascii=False),
                    risks_json=json.dumps(item["risks"], ensure_ascii=False),
                    quote_time=item["quote_time"],
                    source=item["source"],
                    discovered_at=captured_at,
                )
            )
            imported += 1
    return imported


def import_packaged_ranking_archives() -> dict[str, Any]:
    imported = 0
    errors: list[str] = []
    if not ARCHIVE_DIR.exists():
        return {"imported": 0, "errors": []}
    for path in sorted(ARCHIVE_DIR.glob("*.json")):
        if not _ARCHIVE_FILE_RE.fullmatch(path.name):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            imported += import_ranking_archive(payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    return {"imported": imported, "errors": errors}


def _read_remote_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "smart-a-share-ranking-archive/1"})
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("remote archive payload must be an object")
    return payload


def _existing_dates() -> set[str]:
    with SessionLocal() as session:
        return set(session.scalars(select(RankingDiscovery.discovery_date).distinct()))


def sync_ranking_archives(force: bool = False) -> dict[str, Any]:
    global _next_remote_sync_at, _packaged_loaded
    with _SYNC_LOCK:
        packaged = {"imported": 0, "errors": []}
        if not _packaged_loaded:
            packaged = import_packaged_ranking_archives()
            _packaged_loaded = True

        now = time.monotonic()
        if not force and now < _next_remote_sync_at:
            return {"status": "cooldown", "imported": packaged["imported"], "errors": packaged["errors"]}
        _next_remote_sync_at = now + _REMOTE_SYNC_COOLDOWN_SECONDS

        index_url = os.getenv("RANKING_ARCHIVE_INDEX_URL", DEFAULT_REMOTE_INDEX_URL).strip()
        if not index_url:
            return {"status": "disabled", "imported": packaged["imported"], "errors": packaged["errors"]}

        imported = int(packaged["imported"])
        errors = list(packaged["errors"])
        try:
            index = _read_remote_json(index_url)
            entries = index.get("archives") or []
            if not isinstance(entries, list):
                raise ValueError("remote archive index is invalid")
            existing_dates = _existing_dates()
            for entry in entries:
                if isinstance(entry, str):
                    filename = entry
                    archive_date = entry.removesuffix(".json")
                elif isinstance(entry, dict):
                    filename = str(entry.get("file") or "")
                    archive_date = str(entry.get("date") or "")
                else:
                    continue
                if not _ARCHIVE_FILE_RE.fullmatch(filename):
                    errors.append(f"unsafe archive filename: {filename}")
                    continue
                if archive_date in existing_dates:
                    continue
                payload = _read_remote_json(urljoin(index_url, filename))
                imported += import_ranking_archive(payload)
                existing_dates.add(archive_date)
        except Exception as exc:
            errors.append(str(exc))
            return {"status": "remote_unavailable", "imported": imported, "errors": errors}
        return {"status": "synced", "imported": imported, "errors": errors}