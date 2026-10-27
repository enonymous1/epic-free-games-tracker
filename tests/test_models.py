from __future__ import annotations

import pytest
from pydantic import ValidationError

from epic_free_games_tracker.models import EpicResponse, Game


def test_all_sample_elements_validate(sample_games: list[Game]) -> None:
    assert [game.title for game in sample_games] == [
        "Example Quest",
        "Example Racer 2",
        "Example: No Promotion Edition",
    ]


def test_is_free_and_upcoming_free(sample_games: list[Game]) -> None:
    quest, racer, bundle = sample_games
    assert quest.is_free() is True
    assert quest.is_upcoming_free() is False
    assert racer.is_free() is False
    assert racer.is_upcoming_free() is True
    assert bundle.is_free() is False
    assert bundle.is_upcoming_free() is False


def test_promotion_dates_current_then_upcoming(
    sample_games: list[Game],
) -> None:
    quest, racer, bundle = sample_games
    quest_dates = quest.get_promotion_dates()
    assert quest_dates is not None
    assert quest_dates["start"].isoformat() == "2026-10-22T15:00:00+00:00"
    racer_dates = racer.get_promotion_dates()
    assert racer_dates is not None
    assert racer_dates["start"].isoformat() == "2026-12-10T17:00:00+00:00"
    assert bundle.get_promotion_dates() is None


def test_extra_payload_fields_are_ignored() -> None:
    game = Game.model_validate(
        {
            "title": "Example",
            "id": "x",
            "namespace": "ns",
            "offerType": "BASE_GAME",
            "brandNewFieldEpicMightAdd": {"nested": True},
            "price": {
                "totalPrice": {
                    "originalPrice": 100,
                    "discountPrice": 100,
                    "currencyCode": "USD",
                    "futurePriceField": 1,
                }
            },
        }
    )
    assert game.title == "Example"


def test_missing_required_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Game.model_validate({"title": "Example", "id": "x"})


def test_response_with_no_elements() -> None:
    response = EpicResponse.model_validate(
        {"data": {"Catalog": {"searchStore": {"elements": []}}}}
    )
    assert response.get_games() == []
