"""Conversion from feed models to flat offer records, plus filtering.

Why the record is flat: the CSV store needs one row per game, so
nested feed data (images, categories, discount rules) is serialised
to JSON strings here and only here. Display re-parses those strings;
that is a known cost of the CSV format, not a second data model.

Feed quirks fixed here, with regression tests for each:

* Store URLs come from the feed's ``urlSlug``. That value is sometimes
  a hash, which is a valid store slug; building a slug from the title
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
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .models import Game

STORE_BASE_URL = "https://store.epicgames.com/en-US/p"

PriceType = Literal["free", "discounted", "paid", "unknown"]
PromotionStatus = Literal["Available Now", "Coming Soon", "No promotion"]
FilterKind = Literal["all", "free", "bundle", "discounted"]

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
    """Lowercase slug for a title, used only as a URL fallback.

    Apostrophes are dropped, not hyphenated (``Them's`` -> ``thems``,
    matching Epic's own slugs), and non-ASCII letters are folded to
    ASCII (``Café`` -> ``cafe``) instead of becoming hyphens.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    folded = folded.replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def format_price(cents: int, currency_code: str = "USD") -> str:
    """Format minor units (cents for USD) as a display price.

    USD keeps the familiar ``$`` form that existing CSV readers and
    tests expect. Other currencies are prefixed with their code
    instead of a wrong ``$`` sign; a decimals-aware format is a
    future change, not a silent guess here.
    """
    amount = f"{cents / 100:.2f}"
    if currency_code == "USD":
        return f"${amount}"
    return f"{currency_code} {amount}"


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
    return f"{STORE_BASE_URL}/{slug}"


def main_image_url(game: Game) -> str:
    """First usable hero image, preferring the wide banner.

    Epic returns many image types per game (tall, wide, thumbnail,
    carousel, featured media). Only ``OfferImageWide`` and
    ``Thumbnail`` are stable enough for a terminal panel; anything
    else is noise for this display.
    """
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
    price_type: PriceType
    effective_date: str
    viewable_date: str
    expiry_date: str
    start_date: str
    end_date: str
    status: PromotionStatus
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
    date_found: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Display/filtering only; not a CSV column.
    upcoming_free: bool = False

    def to_dict(self) -> dict[str, object]:
        """CSV row, derived from ``CSV_FIELDS`` so it cannot drift.

        ``CSV_FIELDS`` is the single source of truth for columns;
        adding a field to the record without adding it here (or
        vice versa) is impossible by construction. ``upcoming_free``
        is deliberately absent: it is not in ``CSV_FIELDS``.
        """
        return {name: getattr(self, name) for name in CSV_FIELDS}


def _iso(value: datetime | None) -> str:
    """ISO-8601 string, or ``""`` for a missing date."""
    return value.isoformat() if value is not None else ""


def _promotion_status(game: Game) -> tuple[PromotionStatus, str, str]:
    """(status, start_date, end_date) from current, then upcoming, promos.

    Display choice, not a "next ending" calculation: current offers
    win over upcoming, and the first offer in each list wins. If an
    ending-soon view is ever built, it needs a real selection rule
    (e.g. earliest end date among active offers), not this helper.
    """
    if game.promotions is not None:
        for promo_list, status in (
            (game.promotions.promotional_offers, "Available Now"),
            (game.promotions.upcoming_promotional_offers, "Coming Soon"),
        ):
            for promo_data in promo_list:
                if promo_data.promotional_offers:
                    offer = promo_data.promotional_offers[0]
                    return (
                        status,  # type: ignore[return-value]
                        offer.start_date.isoformat(),
                        offer.end_date.isoformat(),
                    )
    return "No promotion", "", ""


def _discount_rules(game: Game) -> str:
    """Raw promotion settings as a JSON string, for the CSV column.

    These are the feed's settings, not the effective discount (see
    the module docstring). They are kept verbatim so a reader can
    see what Epic reported, separate from the computed percentage.
    """
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
    seller = game.seller
    if game.price is not None:
        total = game.price.total_price
        original = total.original_price
        discount = total.discount_price
        currency = total.currency_code
        percentage = (
            round((original - discount) / original * 100, 2) if original > 0 else 0.0
        )
        if discount == 0:
            price_type: PriceType = "free"
        elif percentage > 0:
            price_type = "discounted"
        else:
            price_type = "paid"
        original_price = format_price(original, currency)
        discount_price = format_price(discount, currency)
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
        developer=seller.name if seller and seller.name else "Unknown Developer",
        developer_id=seller.id if seller and seller.id else "",
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
        categories=json.dumps([cat.path for cat in game.categories]),
        tags=json.dumps([tag.id for tag in game.tags]),
        discount_rules=_discount_rules(game),
        custom_attributes=json.dumps(game.custom_attributes),
        all_categories=json.dumps([{"path": cat.path} for cat in game.categories]),
        all_tags=json.dumps([{"id": tag.id} for tag in game.tags]),
        date_found=date_found or datetime.now(timezone.utc).isoformat(),
        upcoming_free=game.is_upcoming_free(),
    )


def to_records(games: list[Game]) -> list[OfferRecord]:
    """Convert every validated game to a record, in feed order."""
    return [game_to_record(game) for game in games]


def filter_records(
    records: list[OfferRecord], *, kind: FilterKind
) -> list[OfferRecord]:
    """Filter records by kind; the single filter entry point.

    ``free`` means currently free or upcoming-free, matching the
    original tracker's default. Unknown ``kind`` values are a caller
    error, not a silent empty result. There is deliberately no
    parallel model-level filter: convert once, then filter records,
    so "free" is defined in exactly one place.
    """
    if kind == "all":
        return list(records)
    if kind == "free":
        return [
            record
            for record in records
            if record.price_type == "free" or record.upcoming_free
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
