"""CSV history store with de-duplication.

A row is new when no existing row shares its id, or when a
shared-id row differs in title, price, status, or promotion dates.
That preserves the originals' "keep history, don't duplicate a run"
behaviour while fixing the crash on a mismatched older CSV: rows
missing a compared column are treated as different, never as a
``KeyError``.

Why the comparison is against the *latest* row per id, not the
first: a history file holds several rows per id over time. Comparing
against the first row would drop a state that returns to a
previously seen value (e.g. a price that goes $24.99 -> $19.99 ->
$24.99), even though it differs from the current state.

Why the write is atomic: the file is rewritten in full on every
save, so writing directly to it risks a crash or disk-full event
destroying the whole history. Writing to a temp file in the same
directory and ``os.replace``-ing it over the target leaves the
old file intact on failure.
"""

from __future__ import annotations

import contextlib
import csv
import os
import tempfile
from pathlib import Path

from .catalog import CSV_FIELDS, OfferRecord

_COMPARE_FIELDS = ("title", "original_price", "status", "start_date", "end_date")


def _load_existing(csv_path: Path) -> list[dict[str, str]]:
    """Existing history rows, or ``[]`` when the file does not exist."""
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _latest_by_id(existing: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Last row per id, in file order. Later rows overwrite earlier ones."""
    latest: dict[str, dict[str, str]] = {}
    for row in existing:
        row_id = row.get("id")
        if row_id is not None:
            latest[row_id] = row
    return latest


def _is_new(record: dict[str, object], latest: dict[str, dict[str, str]]) -> bool:
    """Return True when ``record`` adds information over the latest row.

    Compared against the *latest* row for the same id (see the
    module docstring): new id, or changed title/price/status/
    promotion dates. A row identical to the latest row is a
    duplicate run, not history.
    """
    old = latest.get(str(record["id"]))
    if old is None:
        return True
    return any(
        str(old.get(field, "")) != str(record[field]) for field in _COMPARE_FIELDS
    )


def save_records(records: list[OfferRecord], csv_path: Path) -> tuple[Path, int]:
    """Append only new/changed records; returns (path, rows added)."""
    if not records:
        return csv_path, 0
    existing = _load_existing(csv_path)
    latest = _latest_by_id(existing)
    new_rows: list[dict[str, object]] = []
    for record in records:
        data = record.to_dict()
        if _is_new(data, latest):
            new_rows.append(data)
            latest[str(data["id"])] = {
                field: str(data.get(field, "")) for field in CSV_FIELDS
            }
    if not new_rows:
        return csv_path, 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = existing + [
        {field: str(row.get(field, "")) for field in CSV_FIELDS} for row in new_rows
    ]
    fd, tmp_name = tempfile.mkstemp(
        dir=str(csv_path.parent), prefix=csv_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
        os.replace(tmp_name, csv_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return csv_path, len(new_rows)
