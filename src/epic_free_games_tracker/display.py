"""Rich terminal display for offer records."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from .catalog import OfferRecord


def _format_date(value: str) -> str:
    if not value:
        return "N/A"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return value


def _price_text(record: OfferRecord) -> str:
    if record.price_type == "free":
        return "FREE"
    if record.upcoming_free:
        return f"FREE (upcoming; {record.original_price} until then)"
    if record.price_type == "discounted":
        return (
            f"{record.original_price} -> {record.discount_price} "
            f"({record.discount_percentage}% off)"
        )
    if record.price_type == "paid":
        return record.original_price
    return "N/A"


def display_game(console: Console, record: OfferRecord) -> None:
    try:
        categories = json.loads(record.all_categories)
    except json.JSONDecodeError:
        categories = []
    category_names = ", ".join(
        str(cat.get("path", "")) for cat in categories if isinstance(cat, dict)
    )
    try:
        images = json.loads(record.images)
    except json.JSONDecodeError:
        images = {}
    image_names = ", ".join(images) if isinstance(images, dict) else ""
    bundle_info = (
        f"\n[bold purple]Bundle Items:[/bold purple] {record.bundle_items}"
        if record.is_bundle
        else ""
    )
    description = record.description[:200]
    if len(record.description) > 200:
        description += "..."
    console.print(
        Panel.fit(
            f"[bold cyan]Title:[/bold cyan] {record.title}\n"
            f"[bold green]Developer:[/bold green] {record.developer} "
            f"(ID: {record.developer_id})\n"
            f"[bold yellow]Price:[/bold yellow] {_price_text(record)} "
            f"({record.currency_code})\n"
            f"[bold magenta]Status:[/bold magenta] {record.status} "
            f"({record.offer_type}){bundle_info}\n"
            f"[bold blue]Dates:[/bold blue]\n"
            f"  Available: {_format_date(record.start_date)} to "
            f"{_format_date(record.end_date)}\n"
            f"  Released: {_format_date(record.effective_date)}\n"
            f"  Expires: {_format_date(record.expiry_date)}\n"
            f"[bold white]Categories:[/bold white] {category_names}\n"
            f"[bold white]Images:[/bold white] {image_names}\n"
            f"[bold white]Store Link:[/bold white] {record.store_url}\n"
            f"[bold white]Description:[/bold white] {description}",
            border_style="green",
            title=f"[blue]{record.offer_type}[/blue]",
        )
    )


def display_summary(
    console: Console,
    records: list[OfferRecord],
    csv_path: Path | None,
    added: int,
) -> None:
    console.print(f"\n[green]Found {len(records)} games[/green]")
    if csv_path is not None:
        console.print(f"[blue]Data saved to: {csv_path.absolute()}[/blue]")
        console.print(f"[blue]New entries added: {added}[/blue]")
    by_type = Counter(record.offer_type for record in records)
    by_status = Counter(record.status for record in records)
    console.print("\n[cyan]Offer Types:[/cyan]")
    for offer_type, count in sorted(by_type.items()):
        console.print(f"  {offer_type}: {count}")
    console.print("\n[cyan]Status Breakdown:[/cyan]")
    for status, count in sorted(by_status.items()):
        console.print(f"  {status}: {count}")
