"""Shared fixtures: the fictional sample feed, loaded through real code."""

from __future__ import annotations

from pathlib import Path

import pytest

from epic_free_games_tracker.client import load_games_from_file
from epic_free_games_tracker.models import Game


@pytest.fixture()
def sample_games() -> list[Game]:
    sample = Path(__file__).parent.parent / "examples" / "sample_response.json"
    return load_games_from_file(sample)


@pytest.fixture()
def sample_payload() -> dict[str, object]:
    import json

    sample = Path(__file__).parent.parent / "examples" / "sample_response.json"
    payload: dict[str, object] = json.loads(sample.read_text(encoding="utf-8"))
    return payload
