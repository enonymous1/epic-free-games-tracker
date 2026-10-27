"""CSV history store with de-duplication.

Rewrites the whole file on each save, like the original tracker and
extended scripts, but the comparison is tolerant of older files: rows
missing a compared column are treated as different, never as a
``KeyError``. A row is new when no existing row shares its id, or when
a shared-id row differs in title, price, status, or promotion dates.
That preserves the originals' "keep history, don't duplicate a run"
behaviour while fixing the crash on a mismatched older CSV.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .catalog import CSV_FIELDS, OfferRecord

_COMPARE_FIELDS = ("title", "original_price", "status", "start_date", "end_date")


def _load_existing(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _is_new(record: dict[str, object], existing: list[dict[str, str]]) -> bool:
    for row in existing:
        if row.get("id") == record["id"]:
            return any(
                str(row.get(field, "")) != str(record[field])
                for field in _COMPARE_FIELDS
            )
    return True


def save_records(records: list[OfferRecord], csv_path: Path) -> tuple[Path, int]:
    """Append only new/changed records; returns (path, rows added)."""
    if not records:
        return csv_path, 0
    existing = _load_existing(csv_path)
    new_rows = [
        record.to_dict() for record in records if _is_new(record.to_dict(), existing)
    ]
    if not new_rows:
        return csv_path, 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = existing + [
        {field: str(row.get(field, "")) for field in CSV_FIELDS} for row in new_rows
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    return csv_path, len(new_rows)
