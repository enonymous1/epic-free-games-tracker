"""Pydantic models for the Epic free-games promotions feed.

The feed is a JSON document, not scraped HTML. Field names in the payload
are camelCase; the models use snake_case names with aliases and accept
construction by either name. Unknown payload fields are ignored so a new
field Epic adds tomorrow does not break a run.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PriceInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    original_price: int = Field(..., alias="originalPrice")
    discount_price: int = Field(..., alias="discountPrice")
    discount: int = 0
    currency_code: str = Field("USD", alias="currencyCode")


class TotalPrice(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    total_price: PriceInfo = Field(..., alias="totalPrice")


class DiscountSetting(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    discount_type: str = Field(..., alias="discountType")
    discount_percentage: int = Field(..., alias="discountPercentage")


class PromotionalOffer(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    start_date: datetime = Field(..., alias="startDate")
    end_date: datetime = Field(..., alias="endDate")
    discount_setting: DiscountSetting | None = Field(None, alias="discountSetting")


class PromotionData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    promotional_offers: list[PromotionalOffer] = Field([], alias="promotionalOffers")


class Promotions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    promotional_offers: list[PromotionData] = Field([], alias="promotionalOffers")
    upcoming_promotional_offers: list[PromotionData] = Field(
        [], alias="upcomingPromotionalOffers"
    )


class Image(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    url: str


class Game(BaseModel):
    """One element from the feed's ``searchStore`` list."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str
    id: str
    namespace: str
    description: str | None = None
    offer_type: str = Field(..., alias="offerType")
    price: TotalPrice | None = None
    promotions: Promotions | None = None
    seller: dict[str, Any] | None = None
    key_images: list[Image] = Field([], alias="keyImages")
    effective_date: datetime | None = Field(None, alias="effectiveDate")
    viewable_date: datetime | None = Field(None, alias="viewableDate")
    expiry_date: datetime | None = Field(None, alias="expiryDate")
    categories: list[dict[str, Any]] = []
    tags: list[dict[str, Any]] = []
    custom_attributes: list[dict[str, Any]] = Field([], alias="customAttributes")
    url_slug: str | None = Field(None, alias="urlSlug")
    product_slug: str | None = Field(None, alias="productSlug")
    items: list[dict[str, Any]] = []

    def is_free(self) -> bool:
        """True when the current price is zero."""
        if not self.price:
            return False
        return self.price.total_price.discount_price == 0

    def is_upcoming_free(self) -> bool:
        """True when an upcoming promotion is a 100% discount."""
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
        """First current promotion dates, else first upcoming ones."""
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


class EpicResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    data: dict[str, Any]

    def get_games(self) -> list[Game]:
        elements = (
            self.data.get("Catalog", {}).get("searchStore", {}).get("elements", [])
        )
        return [Game.model_validate(game) for game in elements]
