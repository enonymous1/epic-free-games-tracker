from __future__ import annotations

import csv
from pathlib import Path

from epic_free_games_tracker.catalog import CSV_FIELDS, game_to_record, to_records
from epic_free_games_tracker.models import Game
from epic_free_games_tracker.store import save_records


def _read(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_save_creates_file_with_header(
    sample_games: list[Game], tmp_path: Path
) -> None:
    csv_path = tmp_path / "out" / "games.csv"
    path, added = save_records(to_records(sample_games), csv_path)
    assert path == csv_path
    assert added == 3
    rows = _read(csv_path)
    assert len(rows) == 3
    assert list(rows[0].keys()) == CSV_FIELDS


def test_second_identical_run_adds_nothing(
    sample_games: list[Game], tmp_path: Path
) -> None:
    csv_path = tmp_path / "games.csv"
    save_records(to_records(sample_games), csv_path)
    _, added = save_records(to_records(sample_games), csv_path)
    assert added == 0
    assert len(_read(csv_path)) == 3


def test_changed_price_adds_a_row(sample_games: list[Game], tmp_path: Path) -> None:
    csv_path = tmp_path / "games.csv"
    records = to_records(sample_games)
    save_records(records, csv_path)
    changed = game_to_record(sample_games[0], date_found="2026-10-28T00:00:00")
    changed_dict = changed.to_dict()
    # Simulate a price change by editing the record's price fields via
    # a fresh record built from the same game is not possible (frozen
    # dataclass), so rewrite through the store with a modified copy.
    import dataclasses

    modified = dataclasses.replace(changed, original_price="$29.99")
    _, added = save_records([modified], csv_path)
    assert added == 1
    assert len(_read(csv_path)) == 4
    assert changed_dict["title"] == "Example Quest"


def test_older_csv_missing_columns_does_not_crash(
    sample_games: list[Game], tmp_path: Path
) -> None:
    csv_path = tmp_path / "games.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "id"])
        writer.writeheader()
        writer.writerow({"title": "Example Quest", "id": sample_games[0].id})
    _, added = save_records(to_records(sample_games), csv_path)
    assert added == 3
    assert len(_read(csv_path)) == 4


def test_empty_records_write_nothing(tmp_path: Path) -> None:
    csv_path = tmp_path / "games.csv"
    _, added = save_records([], csv_path)
    assert added == 0
    assert not csv_path.exists()
