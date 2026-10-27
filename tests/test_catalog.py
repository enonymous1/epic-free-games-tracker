from __future__ import annotations

import pytest

from epic_free_games_tracker.catalog import (
    filter_games,
    filter_records,
    game_to_record,
    slugify,
    store_url_for,
    to_records,
)
from epic_free_games_tracker.models import Game


def test_slugify_strips_punctuation() -> None:
    assert slugify("LISA: The Definitive Edition") == "lisa-the-definitive-edition"
    assert slugify("Them's Fightin' Herds") == "them-s-fightin-herds"


def test_store_url_uses_url_slug_even_when_hash(
    sample_games: list[Game],
) -> None:
    racer = sample_games[1]
    assert racer.url_slug == "aabbccddeeff00112233445566778899"
    assert store_url_for(racer) == (
        "https://store.epicgames.com/en-US/p/aabbccddeeff00112233445566778899"
    )


def test_store_url_falls_back_to_title_slug(
    sample_games: list[Game],
) -> None:
    bundle = sample_games[2]
    assert bundle.url_slug is None
    assert store_url_for(bundle) == (
        "https://store.epicgames.com/en-US/p/example-no-promotion-edition"
    )


def test_upcoming_free_flag_set_at_conversion(
    sample_games: list[Game],
) -> None:
    assert game_to_record(sample_games[0]).upcoming_free is False
    assert game_to_record(sample_games[1]).upcoming_free is True


def test_record_keeps_no_promotion_game(sample_games: list[Game]) -> None:
    record = game_to_record(sample_games[2])
    assert record.status == "No promotion"
    assert record.price_type == "unknown"
    assert record.description == ""
    assert record.developer == "Unknown Developer"
    assert record.is_bundle is True
    assert record.bundle_items == 1


def test_discount_percentage_computed_from_prices(
    sample_games: list[Game],
) -> None:
    # The feed reports discountPercentage 0 for the free game; the
    # computed discount is 100%, not the promotion setting.
    record = game_to_record(sample_games[0])
    assert record.discount_percentage == 100.0
    assert record.price_type == "free"
    assert record.original_price == "$24.99"
    assert record.discount_price == "$0.00"


def test_filters(sample_games: list[Game]) -> None:
    assert [g.title for g in filter_games(sample_games, kind="all")] == [
        "Example Quest",
        "Example Racer 2",
        "Example: No Promotion Edition",
    ]
    assert [g.title for g in filter_games(sample_games, kind="free")] == [
        "Example Quest",
        "Example Racer 2",
    ]
    assert [g.title for g in filter_games(sample_games, kind="bundle")] == [
        "Example: No Promotion Edition"
    ]
    assert filter_games(sample_games, kind="discounted") == []
    with pytest.raises(ValueError):
        filter_games(sample_games, kind="bogus")


def test_filter_records_free_uses_promotion_rules(
    sample_games: list[Game],
) -> None:
    records = to_records(sample_games)
    assert [r.title for r in filter_records(records, kind="free")] == [
        "Example Quest",
        "Example Racer 2",
    ]
