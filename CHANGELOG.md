# Changelog

## 2.0.0 — 2026-10-27

Rebuilt from the original `WebScraping` project (Epic Games Store free-games
tracker, July 2026) as a single installable package. The original had three
overlapping implementations of the same feed; this release keeps one.

### Added

- Installable `epic_free_games_tracker` package (src layout, Python 3.10+)
  with the `epic-free-games` CLI and `python -m epic_free_games_tracker`.
- `argparse` CLI: `--all`, `--free` (default), `--bundles`, `--discounted`,
  `--input` (offline sample / saved payload), `--output`, `--no-save`,
  `--debug`, `--locale`, `--country`, `--timeout`, `--version`.
- `examples/sample_response.json`: a fictional three-game feed payload for
  offline demos and tests. No live store data is shipped.
- Test suite (mocked HTTP, no network in tests), GitHub Actions CI
  (Python 3.10–3.13, Ubuntu + Windows), MIT LICENSE, hardened `.gitignore`,
  `.gitattributes` (LF endings).

### Fixed

- The documented entry point now runs: the original `python src/main.py`
  failed with an `ImportError` (relative import beyond the top-level
  package, no `src/__init__.py`).
- Store URLs now come from the feed's `urlSlug` (sometimes a hash, which
  is a valid slug), with `productSlug` and a title slug as fallbacks.
  Building a slug from the title produced broken URLs.
- Discount percentages are computed from the prices, not copied from a
  promotion's `discountSetting` (which reports 0% for free games).
- The tracker's CSV saving is wired up (it was dead code); saving no
  longer crashes on an older CSV missing columns, and duplicate runs
  add no rows.
- Elements with no promotions are kept for `--all` instead of dropped,
  with status `No promotion`. Display no longer crashes on a missing
  description.
- The httpx client is closed (context manager) and retries transient
  5xx responses, matching the old `requests` clients.
- Proxy and CA-bundle settings are resolved from the environment
  explicitly instead of relying on httpx's `trust_env` parsing, which
  crashes on some `NO_PROXY` values (IPv6 entries such as `[::1]`).
- `requests` is no longer needed: everything uses httpx.

### Changed (breaking)

- One output file by default (`output/epic_free_games.csv`) instead of
  three different locations, and one CSV schema (the tracker's 35
  columns). The stale committed CSVs from January 2025 are not shipped;
  `output/` is gitignored.
- `--debug` now saves the raw payload *and* continues to display and
  save results; the originals stopped after saving the debug file.
- Fetch failures now exit non-zero (1) instead of printing "No games
  found" and exiting 0.
- The project is renamed from `WebScraping` to
  `epic-free-games-tracker`: it reads a public JSON feed, it does not
  scrape HTML. Not affiliated with Epic Games.
