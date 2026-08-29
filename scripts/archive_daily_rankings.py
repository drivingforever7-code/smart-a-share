from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MODES = ("short", "swing")
FIELDS = (
    "discovery_date",
    "mode",
    "rank",
    "code",
    "name",
    "industry",
    "discovery_price",
    "discovery_score",
    "recommendation",
    "confidence",
    "reasons",
    "risks",
    "quote_time",
    "source",
)


def build_archive(response: dict[str, Any]) -> dict[str, Any]:
    trade_date = str((response.get("meta") or {}).get("trade_date") or "")[:10]
    date.fromisoformat(trade_date)
    items = [
        item
        for item in (response.get("items") or [])
        if item.get("discovery_date") == trade_date and item.get("mode") in MODES
    ]
    archived: list[dict[str, Any]] = []
    for mode in MODES:
        group = sorted(
            (item for item in items if item.get("mode") == mode),
            key=lambda item: int(item.get("rank") or 0),
        )
        if [int(item.get("rank") or 0) for item in group] != [1, 2, 3]:
            raise ValueError(f"{trade_date} {mode} does not contain ranks 1-3")
        if len({str(item.get("code")) for item in group}) != 3:
            raise ValueError(f"{trade_date} {mode} contains duplicate codes")
        archived.extend({field: item.get(field) for field in FIELDS} for item in group)
    return {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "items": archived,
    }


def write_archive(payload: dict[str, Any], output_dir: Path) -> tuple[Path, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trade_date = str(payload["trade_date"])
    archive_path = output_dir / f"{trade_date}.json"
    created = not archive_path.exists()
    if archive_path.exists():
        existing = json.loads(archive_path.read_text(encoding="utf-8"))
        if existing.get("trade_date") != trade_date or existing.get("items") != payload.get("items"):
            raise ValueError(f"{trade_date} archive conflicts with the frozen snapshot")
    else:
        archive_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    index_path = output_dir / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"schema_version": SCHEMA_VERSION, "archives": []}
    entries = {
        str(entry.get("date")): entry
        for entry in (index.get("archives") or [])
        if isinstance(entry, dict) and entry.get("date")
    }
    index_changed = trade_date not in entries
    entries[trade_date] = {"date": trade_date, "file": archive_path.name}
    if index_changed or not index_path.exists():
        index = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "archives": [entries[key] for key in sorted(entries)],
        }
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return archive_path, created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("response_json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    response = json.loads(args.response_json.read_text(encoding="utf-8"))
    path, created = write_archive(build_archive(response), args.output_dir)
    print(f"archive={path.name} status={'created' if created else 'verified'}")


if __name__ == "__main__":
    main()