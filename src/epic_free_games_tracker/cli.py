"""Command-line interface: one entry point for the whole tracker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .catalog import filter_games, to_records
from .client import EpicStoreClient, load_games_from_file
from .display import display_game, display_summary
from .models import Game
from .store import save_records

console = Console()


def build_parser() -> argparse.ArgumentParser:
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


def _filter_kind(args: argparse.Namespace) -> str:
    if args.all_games:
        return "all"
    if args.bundles:
        return "bundle"
    if args.discounted:
        return "discounted"
    return "free"


def _fetch(args: argparse.Namespace) -> list[Game]:
    if args.input is not None:
        return load_games_from_file(args.input)
    project_root = Path(__file__).resolve().parent.parent.parent
    debug_dir = project_root / "debug_logs" if args.debug else None
    with EpicStoreClient(timeout=args.timeout) as client:
        return client.get_games(
            locale=args.locale,
            country=args.country,
            debug_dir=debug_dir,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console.print(
        Panel.fit("Epic Games Store Tracker", border_style="blue", padding=(1, 2))
    )
    try:
        games = _fetch(args)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        console.print(f"[red]Error fetching games: {exc}[/red]")
        return 1

    kept = filter_games(games, kind=_filter_kind(args))
    records = to_records(kept)
    if not records:
        console.print("[red]No games found.[/red]")
        return 0

    csv_path: Path | None = None
    added = 0
    if not args.no_save:
        project_root = Path(__file__).resolve().parent.parent.parent
        csv_path = args.output or (project_root / "output" / "epic_free_games.csv")
        csv_path, added = save_records(records, csv_path)

    display_summary(console, records, csv_path, added)
    for record in records:
        display_game(console, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
