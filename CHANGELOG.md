# Changelog

## 2.0.1 — 2026-10-31

Staff-review fixes (see the review file delivered with v2.0.0).
No behaviour change for a normal run except where noted.

### Fixed

- Default output/debug paths are now relative to the current
  working directory (`./output/epic_free_games.csv`,
  `./debug_logs/`), not to the installed package. A wheel
  install previously wrote into (or failed on) the Python tree.
- CSV history is written atomically (temp file + `os.replace`)
  and de-duplication compares against the *latest* row per id,
  not the first: a price returning to a previously seen value
  now adds a row again, and a failed run leaves the old file
  intact.
- Errors go to stderr (not stdout) and a CSV save failure now
  exits 1 with a clean message instead of a traceback.
- Feed text is escaped before Rich rendering, so a title
  containing markup prints literally instead of breaking a
  panel. Promotion dates are labelled UTC, and `date_found`
  and debug timestamps are UTC ISO-8601.
- The client retries 429 (honouring `Retry-After`) as well as
  5xx, with jittered backoff; retry sleeps are injectable for
  tests.
- `slugify` drops apostrophes (`Them's` -> `thems`, matching
  Epic's slugs) and folds non-ASCII letters instead of
  hyphenating them.
- A non-dict `Catalog`/`searchStore` now raises a validation
  error the CLI reports cleanly, instead of an uncaught
  `AttributeError`.

### Changed

- `filter_games` (model-level) is removed: convert once with
  `to_records`, then filter records with `filter_records`.
  `OfferRecord.to_dict()` is derived from `CSV_FIELDS`, so the
  CSV schema cannot drift from the record.
- `price_type` and `status` are now `Literal` types, and all
  feed models share an `EpicBaseModel` (aliases + ignore
  unknowns). `EpicResponse` is fully typed instead of a
  `dict` traversal, and `seller`/`categories`/`tags` are typed
  models.
- Version is now single-source: `pyproject.toml` reads it from
  `epic_free_games_tracker.__version__`. Dependency bounds
  gain upper limits; `pytest-cov` joins the dev extras.
- Ruff now selects `S`, `SIM`, and `D` (with an explicit
  `py310` target) and mypy checks `src` and `tests`. CI is
  split into a single lint job, a test matrix with a coverage
  gate (80%), and a weekly scheduled live smoke check.
- README rewritten with Description, Prerequisites,
  Installation, Local Development, and Deployment sections,
  plus `docs/assets/` visuals (architecture SVG, terminal
  SVG from a real sample run, CSV-history image, demo GIF)
  and `docs/architecture.md` as the diagram source.

### Known limitations (unchanged, documented)

- `NO_PROXY` is still not honoured: when a proxy is set, it
  is used for the feed host too.
- The record still carries parsed structures only at the
  store boundary: `images`/`categories`/`tags`/`discount_rules`
  are JSON strings inside the CSV, re-parsed on display.
- No `Settings`/`App` split, JSON renderer, or SQLite/JSONL
  store yet — those are the next step, not this release.

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
