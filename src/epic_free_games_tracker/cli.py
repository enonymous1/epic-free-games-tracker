"""Command-line interface: one entry point for the whole tracker.

Argument parsing only, then fetch -> convert -> filter -> save ->
display. Default output paths are relative to the current working
directory, not to the installed package: a wheel install has no
project root to write into, so the old package-relative defaults
wrote into the Python tree (or failed on a read-only install).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .catalog import FilterKind, filter_records, to_records
from .client import EpicStoreClient, load_games_from_file
from .display import display_game, display_summary
from .models import Game
from .store import save_records

DEFAULT_CSV_PATH = Path("output") / "epic_free_games.csv"
DEFAULT_DEBUG_DIR = Path("debug_logs")


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the ``epic-free-games`` command."""
    parser = argparse.ArgumentParser(
        prog="epic-free-games",
        description=("Track current and upcoming free games on the Epic Games Store."),
    )
    parser.add_argument("--version", action="version", version=__version__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        dest="all_games",
        action="store_true",
        help="show every element in the promotions feed",
    )
    group.add_argument(
        "--free",
        action="store_true",
        help="show free and upcoming-free games (default)",
    )
    group.add_argument("--bundles", action="store_true", help="show bundles only")
    group.add_argument(
        "--discounted", action="store_true", help="show discounted games only"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        metavar="FILE",
        help="read a saved feed payload (JSON) instead of fetching",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="CSV history file (default: output/epic_free_games.csv)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not write the CSV history file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="save the raw feed payload to debug_logs/ as well",
    )
    parser.add_argument(
        "--locale", default="en-US", help="feed locale (default: en-US)"
    )
    parser.add_argument("--country", default="US", help="feed country (default: US)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    return parser


def _filter_kind(args: argparse.Namespace) -> FilterKind:
    """Map the mutually exclusive filter flags to a filter kind."""
    if args.all_games:
        return "all"
    if args.bundles:
        return "bundle"
    if args.discounted:
        return "discounted"
    return "free"


def _fetch(args: argparse.Namespace) -> list[Game]:
    """Fetch from the feed, or load from ``--input`` when given."""
    if args.input is not None:
        return load_games_from_file(args.input)
    debug_dir = DEFAULT_DEBUG_DIR if args.debug else None
    with EpicStoreClient(timeout=args.timeout) as client:
        return client.get_games(
            locale=args.locale,
            country=args.country,
            debug_dir=debug_dir,
        )


def main(
    argv: list[str] | None = None,
    *,
    console: Console | None = None,
    error_console: Console | None = None,
) -> int:
    """Run the CLI; returns a process exit code (0 on success).

    ``console``/``error_console`` are injectable so tests can
    capture output without touching the module-level consoles,
    and so the display and error streams are genuinely separate:
    errors go to stderr, normal output to stdout, so a piped
    stdout is not polluted by an error message.
    """
    out = console or Console()
    err = error_console or Console(stderr=True)
    args = build_parser().parse_args(argv)
    out.print(
        Panel.fit("Epic Games Store Tracker", border_style="blue", padding=(1, 2))
    )
    try:
        games = _fetch(args)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        err.print(f"[red]Error fetching games: {exc}[/red]")
        return 1

    records = filter_records(to_records(games), kind=_filter_kind(args))
    if not records:
        err.print("[red]No games found.[/red]")
        return 0

    csv_path: Path | None = None
    added = 0
    if not args.no_save:
        csv_path = args.output or DEFAULT_CSV_PATH
        try:
            csv_path, added = save_records(records, csv_path)
        except OSError as exc:
            err.print(f"[red]Error saving CSV history: {exc}[/red]")
            return 1

    display_summary(out, records, csv_path, added)
    for record in records:
        display_game(out, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
