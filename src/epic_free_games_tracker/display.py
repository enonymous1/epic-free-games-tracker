"""Rich terminal display for offer records.

Feed text is data, not markup: every interpolated string is
escaped with :func:`rich.markup.escape` before it reaches a
panel, so a game title containing ``[red]`` or ``[/]`` prints
literally instead of breaking the panel layout or injecting
markup. The labels themselves are still markup; only the
values are escaped.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from .catalog import OfferRecord


def _format_date(value: str) -> str:
    """Format an ISO date for display, labelled UTC when it has one.

    Feed dates are UTC ISO strings. Parsing keeps the offset and
    the output adds a ``UTC`` label so a reader never mistakes
    them for local time. Unparseable values pass through unchanged
    rather than crashing the panel.
    """
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _price_text(record: OfferRecord) -> str:
    """Human-readable price line for a record."""
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


def _json_string(record_value: str, default: object) -> object:
    """Parse a JSON column, falling back to ``default`` on bad data."""
    try:
        return json.loads(record_value)
    except json.JSONDecodeError:
        return default


def display_game(console: Console, record: OfferRecord) -> None:
    """Print one game as a Rich panel."""
    categories = _json_string(record.all_categories, [])
    if not isinstance(categories, list):
        categories = []
    category_names = ", ".join(
        str(cat.get("path", "")) for cat in categories if isinstance(cat, dict)
    )
    images = _json_string(record.images, {})
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
            f"[bold cyan]Title:[/bold cyan] {escape(record.title)}\n"
            f"[bold green]Developer:[/bold green] "
            f"{escape(record.developer)} (ID: {escape(record.developer_id)})\n"
            f"[bold yellow]Price:[/bold yellow] {escape(_price_text(record))} "
            f"({escape(record.currency_code)})\n"
            f"[bold magenta]Status:[/bold magenta] {escape(record.status)} "
            f"({escape(record.offer_type)}){bundle_info}\n"
            f"[bold blue]Dates:[/bold blue]\n"
            f"  Available: {_format_date(record.start_date)} to "
            f"{_format_date(record.end_date)}\n"
            f"  Released: {_format_date(record.effective_date)}\n"
            f"  Expires: {_format_date(record.expiry_date)}\n"
            f"[bold white]Categories:[/bold white] {escape(category_names)}\n"
            f"[bold white]Images:[/bold white] {escape(image_names)}\n"
            f"[bold white]Store Link:[/bold white] {escape(record.store_url)}\n"
            f"[bold white]Description:[/bold white] {escape(description)}",
            border_style="green",
            title=f"[blue]{escape(record.offer_type)}[/blue]",
        )
    )


def display_summary(
    console: Console,
    records: list[OfferRecord],
    csv_path: Path | None,
    added: int,
) -> None:
    """Print the count, CSV outcome, and type/status breakdowns."""
    console.print(f"\n[green]Found {len(records)} games[/green]")
    if csv_path is not None:
        console.print(f"[blue]Data saved to: {csv_path.absolute()}[/blue]")
        console.print(f"[blue]New entries added: {added}[/blue]")
    by_type = Counter(record.offer_type for record in records)
    by_status = Counter(record.status for record in records)
    console.print("\n[cyan]Offer Types:[/cyan]")
    for offer_type, count in sorted(by_type.items()):
        console.print(f"  {escape(offer_type)}: {count}")
    console.print("\n[cyan]Status Breakdown:[/cyan]")
    for status, count in sorted(by_status.items()):
        console.print(f"  {escape(status)}: {count}")
