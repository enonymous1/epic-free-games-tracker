"""Pydantic models for the Epic free-games promotions feed.

The feed is a JSON document, not scraped HTML. Field names in the payload
are camelCase; the models use snake_case names with aliases and accept
construction by either name. Unknown payload fields are ignored so a new
field Epic adds tomorrow does not break a run.

Why a shared base class: every model previously repeated the same
``model_config`` line, so a config change meant ten edits and one
missed model. ``EpicBaseModel`` is the single place for that config.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EpicBaseModel(BaseModel):
    """Shared config for every feed model: aliases + ignore unknowns."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class PriceInfo(EpicBaseModel):
    """Price totals for one offer, in minor units."""

    original_price: int = Field(..., alias="originalPrice")
    discount_price: int = Field(..., alias="discountPrice")
    discount: int = 0
    currency_code: str = Field("USD", alias="currencyCode")


class TotalPrice(EpicBaseModel):
    """Wrapper holding the single ``totalPrice`` object."""

    total_price: PriceInfo = Field(..., alias="totalPrice")


class DiscountSetting(EpicBaseModel):
    """One promotion discount setting, as reported by the feed."""

    discount_type: str = Field(..., alias="discountType")
    discount_percentage: int = Field(..., alias="discountPercentage")


class PromotionalOffer(EpicBaseModel):
    """One dated promotional offer window."""

    start_date: datetime = Field(..., alias="startDate")
    end_date: datetime = Field(..., alias="endDate")
    discount_setting: DiscountSetting | None = Field(None, alias="discountSetting")


class PromotionData(EpicBaseModel):
    """A list of offers under one promotion key."""

    promotional_offers: list[PromotionalOffer] = Field([], alias="promotionalOffers")


class Promotions(EpicBaseModel):
    """Current and upcoming promotion lists for a game."""

    promotional_offers: list[PromotionData] = Field([], alias="promotionalOffers")
    upcoming_promotional_offers: list[PromotionData] = Field(
        [], alias="upcomingPromotionalOffers"
    )


class Image(EpicBaseModel):
    """One key image (type + URL) for a game."""

    type: str
    url: str


class Seller(EpicBaseModel):
    """A game's seller. Either field may be absent in the feed."""

    name: str | None = None
    id: str | None = None


class Category(EpicBaseModel):
    """One category path for a game."""

    path: str = ""


class Tag(EpicBaseModel):
    """One tag id for a game."""

    id: str = ""


class Game(EpicBaseModel):
    """One element from the feed's ``searchStore`` list."""

    title: str
    id: str
    namespace: str
    description: str | None = None
    offer_type: str = Field(..., alias="offerType")
    price: TotalPrice | None = None
    promotions: Promotions | None = None
    seller: Seller | None = None
    key_images: list[Image] = Field([], alias="keyImages")
    effective_date: datetime | None = Field(None, alias="effectiveDate")
    viewable_date: datetime | None = Field(None, alias="viewableDate")
    expiry_date: datetime | None = Field(None, alias="expiryDate")
    categories: list[Category] = []
    tags: list[Tag] = []
    custom_attributes: list[dict[str, Any]] = Field([], alias="customAttributes")
    url_slug: str | None = Field(None, alias="urlSlug")
    product_slug: str | None = Field(None, alias="productSlug")
    items: list[dict[str, Any]] = []

    def is_free(self) -> bool:
        """Return True when the current price is zero."""
        if not self.price:
            return False
        return self.price.total_price.discount_price == 0

    def is_upcoming_free(self) -> bool:
        """Return True when an upcoming promotion is a 100% discount."""
        if not self.promotions:
            return False
        for promo_data in self.promotions.upcoming_promotional_offers:
            for offer in promo_data.promotional_offers:
                setting = offer.discount_setting
                if (
                    setting is not None
                    and setting.discount_type == "PERCENTAGE"
                    and setting.discount_percentage == 100
                ):
                    return True
        return False

    def get_promotion_dates(self) -> dict[str, datetime] | None:
        """First current promotion dates, else first upcoming ones.

        Display-only convenience; the record builder in ``catalog.py``
        uses its own status-aware version, so keep both in sync if
        the selection rule ever changes (see the promotion comment
        there about first-wins vs earliest-ending).
        """
        if not self.promotions:
            return None
        for promo_list in (
            self.promotions.promotional_offers,
            self.promotions.upcoming_promotional_offers,
        ):
            for promo_data in promo_list:
                if promo_data.promotional_offers:
                    offer = promo_data.promotional_offers[0]
                    return {"start": offer.start_date, "end": offer.end_date}
        return None


class SearchStore(EpicBaseModel):
    """The feed element list container."""

    elements: list[Game] = []


class Catalog(EpicBaseModel):
    """The catalog container holding the search store."""

    search_store: SearchStore = Field(default_factory=SearchStore, alias="searchStore")


class EpicData(EpicBaseModel):
    """The ``data`` container of the feed document."""

    catalog: Catalog = Field(default_factory=Catalog, alias="Catalog")


class EpicResponse(EpicBaseModel):
    """The feed document, typed instead of a ``dict[str, Any]`` traversal.

    Why typed: the old ``data.get("Catalog", {}).get(...)`` chain
    raised ``AttributeError`` when ``Catalog`` was not a dict, and
    the CLI only catches ``ValueError``/``OSError``/``HTTPError``,
    so that shape error surfaced as a raw traceback. A typed model
    turns it into a ``ValidationError`` (a ``ValueError`` subclass)
    that the CLI reports cleanly.
    """

    data: EpicData = Field(default_factory=EpicData)

    def get_games(self) -> list[Game]:
        """Return validated games, in feed order."""
        return list(self.data.catalog.search_store.elements)
