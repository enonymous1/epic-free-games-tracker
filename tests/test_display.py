from __future__ import annotations

import dataclasses

from rich.console import Console

from epic_free_games_tracker.catalog import game_to_record
from epic_free_games_tracker.display import _format_date, display_game
from epic_free_games_tracker.models import Game


def test_format_date_labels_utc() -> None:
    assert _format_date("2026-10-22T15:00:00+00:00") == "2026-10-22 15:00 UTC"
    assert _format_date("") == "N/A"
    assert _format_date("not-a-date") == "not-a-date"


def test_feed_markup_is_printed_literally(sample_games: list[Game]) -> None:
    record = dataclasses.replace(
        game_to_record(sample_games[0]), title="[red]Injected[/red]"
    )
    recording = Console(record=True, width=120)
    display_game(recording, record)
    text = recording.export_text()
    assert "[red]Injected[/red]" in text
