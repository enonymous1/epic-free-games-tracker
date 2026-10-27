"""Conversion from feed models to flat offer records, plus filtering.

This keeps the richest field set from the original tracker (35 CSV
columns) while fixing the bugs found in the audit:

* Store URLs come from the feed's ``urlSlug``. That value is sometimes a
  hash, which is a valid store slug; building a slug from the title
  produced broken URLs such as ``lisa:-the-definitive-edition``.
* The discount percentage shown is computed from the prices, not copied
  from a promotion's ``discountSetting``. The feed reports 0% there for
  currently-free games and 20% for a game discounted 80%.
* Elements with no promotions are kept for ``--all`` instead of silently
  dropped, with status ``No promotion``; the free/bundle/discounted
  filters still apply on top.
* ``description`` may be ``None`` in the feed; records normalise it to
  ``""`` so display and CSV code never crash on ``None[:200]``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from .models import Game

CSV_FIELDS: list[str] = [
    "title",
    "id",
    "namespace",
    "description",
    "developer",
    "developer_id",
    "original_price",
    "discount_price",
    "currency_code",
    "discount_percentage",
    "price_type",
    "effective_date",
    "viewable_date",
    "expiry_date",
    "start_date",
    "end_date",
    "status",
    "offer_type",
    "is_bundle",
    "bundle_items",
    "store_url",
    "product_slug",
    "thumbnail",
    "images",
    "categories",
    "tags",
    "discount_rules",
    "custom_attributes",
    "all_categories",
    "all_tags",
    "date_found",
]


def slugify(text: str) -> str:
    """Lowercase slug with punctuation (including ``:``) as hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug


def format_price(cents: int) -> str:
    return f"${cents / 100:.2f}"


def store_url_for(game: Game) -> str:
    """Store URL from ``urlSlug``, else the first ``productSlug`` segment.

    ``productSlug`` can be ``"slug/home"``; only its first segment is a
    store slug. Falls back to a slug built from the title.
    """
    slug = game.url_slug
    if not slug and game.product_slug:
        slug = game.product_slug.split("/", 1)[0]
    if not slug:
        slug = slugify(game.title)
    return f"https://store.epicgames.com/en-US/p/{slug}"


def main_image_url(game: Game) -> str:
    for image in game.key_images:
        if image.type in ("OfferImageWide", "Thumbnail"):
            return image.url
    return ""


@dataclass(frozen=True)
class OfferRecord:
    """One game, flattened for display and CSV export."""

    title: str
    id: str
    namespace: str
    description: str
    developer: str
    developer_id: str
    original_price: str
    discount_price: str
    currency_code: str
    discount_percentage: float
    price_type: str
    effective_date: str
    viewable_date: str
    expiry_date: str
    start_date: str
    end_date: str
    status: str
    offer_type: str
    is_bundle: bool
    bundle_items: int
    store_url: str
    product_slug: str
    thumbnail: str
    images: str
    categories: str
    tags: str
    discount_rules: str
    custom_attributes: str
    all_categories: str
    all_tags: str
    date_found: str = field(default_factory=lambda: datetime.now().isoformat())
    # Display/filtering only; not a CSV column.
    upcoming_free: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "id": self.id,
            "namespace": self.namespace,
            "description": self.description,
            "developer": self.developer,
            "developer_id": self.developer_id,
            "original_price": self.original_price,
            "discount_price": self.discount_price,
            "currency_code": self.currency_code,
            "discount_percentage": self.discount_percentage,
            "price_type": self.price_type,
            "effective_date": self.effective_date,
            "viewable_date": self.viewable_date,
            "expiry_date": self.expiry_date,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "offer_type": self.offer_type,
            "is_bundle": self.is_bundle,
            "bundle_items": self.bundle_items,
            "store_url": self.store_url,
            "product_slug": self.product_slug,
            "thumbnail": self.thumbnail,
            "images": self.images,
            "categories": self.categories,
            "tags": self.tags,
            "discount_rules": self.discount_rules,
            "custom_attributes": self.custom_attributes,
            "all_categories": self.all_categories,
            "all_tags": self.all_tags,
            "date_found": self.date_found,
        }


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _promotion_status(game: Game) -> tuple[str, str, str]:
    """(status, start_date, end_date) from current, then upcoming, promos."""
    if game.promotions is not None:
        for promo_list, status in (
            (game.promotions.promotional_offers, "Available Now"),
            (game.promotions.upcoming_promotional_offers, "Coming Soon"),
        ):
            for promo_data in promo_list:
                if promo_data.promotional_offers:
                    offer = promo_data.promotional_offers[0]
                    return (
                        status,
                        offer.start_date.isoformat(),
                        offer.end_date.isoformat(),
                    )
    return "No promotion", "", ""


def _discount_rules(game: Game) -> str:
    rules: list[dict[str, object]] = []
    if game.promotions is not None:
        for promo_list in (
            game.promotions.promotional_offers,
            game.promotions.upcoming_promotional_offers,
        ):
            for promo_data in promo_list:
                for offer in promo_data.promotional_offers:
                    if offer.discount_setting is not None:
                        rules.append(
                            {
                                "type": offer.discount_setting.discount_type,
                                "percentage": (
                                    offer.discount_setting.discount_percentage
                                ),
                                "start": offer.start_date.isoformat(),
                                "end": offer.end_date.isoformat(),
                            }
                        )
    return json.dumps(rules)


def game_to_record(game: Game, *, date_found: str | None = None) -> OfferRecord:
    """Convert one validated feed element to a flat record."""
    seller = game.seller or {}
    if game.price is not None:
        total = game.price.total_price
        original = total.original_price
        discount = total.discount_price
        currency = total.currency_code
        percentage = (
            round((original - discount) / original * 100, 2) if original > 0 else 0.0
        )
        if discount == 0:
            price_type = "free"
        elif percentage > 0:
            price_type = "discounted"
        else:
            price_type = "paid"
        original_price = format_price(original)
        discount_price = format_price(discount)
    else:
        currency = "USD"
        percentage = 0.0
        price_type = "unknown"
        original_price = ""
        discount_price = ""

    status, start_date, end_date = _promotion_status(game)
    images = {
        image.type: image.url for image in game.key_images if image.type and image.url
    }
    return OfferRecord(
        title=game.title,
        id=game.id,
        namespace=game.namespace,
        description=game.description or "",
        developer=str(seller.get("name", "Unknown Developer")),
        developer_id=str(seller.get("id", "")),
        original_price=original_price,
        discount_price=discount_price,
        currency_code=currency,
        discount_percentage=percentage,
        price_type=price_type,
        effective_date=_iso(game.effective_date),
        viewable_date=_iso(game.viewable_date),
        expiry_date=_iso(game.expiry_date),
        start_date=start_date,
        end_date=end_date,
        status=status,
        offer_type=game.offer_type,
        is_bundle=game.offer_type == "BUNDLE",
        bundle_items=len(game.items),
        store_url=store_url_for(game),
        product_slug=game.product_slug or "",
        thumbnail=main_image_url(game),
        images=json.dumps(images),
        categories=json.dumps([cat.get("path", "") for cat in game.categories if cat]),
        tags=json.dumps([tag.get("id", "") for tag in game.tags if tag]),
        discount_rules=_discount_rules(game),
        custom_attributes=json.dumps(game.custom_attributes),
        all_categories=json.dumps(game.categories),
        all_tags=json.dumps(game.tags),
        date_found=date_found or datetime.now().isoformat(),
        upcoming_free=game.is_upcoming_free(),
    )


def to_records(games: list[Game]) -> list[OfferRecord]:
    return [game_to_record(game) for game in games]


def filter_records(records: list[OfferRecord], *, kind: str) -> list[OfferRecord]:
    """Filter by ``all`` / ``free`` / ``bundle`` / ``discounted``.

    ``free`` means currently free or upcoming-free, matching the
    original tracker's default. Unknown ``kind`` values are a caller
    error, not a silent empty result.
    """
    if kind == "all":
        return list(records)
    if kind == "free":
        return [
            record
            for record in records
            if record.price_type == "free" or _is_upcoming_free_record(record)
        ]
    if kind == "bundle":
        return [record for record in records if record.is_bundle]
    if kind == "discounted":
        return [
            record
            for record in records
            if record.discount_percentage > 0 and record.price_type != "free"
        ]
    raise ValueError(f"unknown filter kind: {kind!r}")


def _is_upcoming_free_record(record: OfferRecord) -> bool:
    """Upcoming-free, as recorded at conversion time."""
    return record.upcoming_free


def filter_games(games: list[Game], *, kind: str) -> list[Game]:
    """Filter validated games before conversion (free needs model data)."""
    if kind == "all":
        return list(games)
    if kind == "free":
        return [game for game in games if game.is_free() or game.is_upcoming_free()]
    if kind == "bundle":
        return [game for game in games if game.offer_type == "BUNDLE"]
    if kind == "discounted":
        records = to_records(games)
        kept_ids = {record.id for record in filter_records(records, kind="discounted")}
        return [game for game in games if game.id in kept_ids]
    raise ValueError(f"unknown filter kind: {kind!r}")
