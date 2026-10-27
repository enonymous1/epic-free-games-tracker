# Epic Free Games Tracker

See which games are free right now, and which are coming free next, on the Epic Games Store — from one command, with a CSV history you can actually re-run without duplicating every row.

It reads Epic's public `freeGamesPromotions` JSON feed. It does not scrape HTML pages, it needs no account or API key, and it is not affiliated with Epic Games.

## Quick start

```bash
pip install -e .
epic-free-games --help
```

Try it without the network, on the fictional sample payload:

```bash
epic-free-games --input examples/sample_response.json --no-save
```

Then live, free games only (the default):

```bash
epic-free-games
```

That prints each game in a Rich panel and saves new or changed rows to `output/epic_free_games.csv`. Running it again adds nothing unless something changed.

## Usage

| Flag | What it does |
| --- | --- |
| `--free` | Free now and upcoming-free games (default) |
| `--all` | Every element in the feed, including ones with no promotion |
| `--bundles` | Bundles only |
| `--discounted` | Discounted (but not free) games only |
| `--output PATH` | CSV history file (default `output/epic_free_games.csv`) |
| `--no-save` | Print only, do not write the CSV |
| `--debug` | Also save the raw feed payload to `debug_logs/` |
| `--input FILE` | Read a saved feed payload instead of fetching |
| `--locale`, `--country` | Feed locale/country (defaults `en-US` / `US`) |
| `--timeout SECONDS` | HTTP timeout (default 30) |
| `--version` | Print the version |

```bash
epic-free-games --all --output output/all_games.csv
epic-free-games --bundles --no-save
epic-free-games --debug
python -m epic_free_games_tracker --free
```

Fetch failures exit with code 1. An empty feed prints "No games found" and exits 0.

## How it works

One httpx client fetches the feed (retries transient 5xx responses, three attempts), Pydantic models validate every element, and each element becomes one flat record with 35 columns: title, ids, description, developer, prices in dollars and cents-derived discount percentage, promotion dates and status, offer type, bundle info, store URL, thumbnail, images, categories, tags, discount rules, and custom attributes.

Two details worth knowing:

- **Store URLs use the feed's `urlSlug`.** That value is sometimes a hash, which is a valid Epic store slug. Building a slug from the title broke URLs (the original produced `lisa:-the-definitive-edition`); the fallback chain is `urlSlug`, then the first segment of `productSlug`, then a slug built from the title.
- **Discount percentages are computed from the prices.** The promotion's `discountSetting` reports 0% for currently-free games, so copying it printed "PERCENTAGE 0%" for a free game. The raw settings are still kept in the `discount_rules` CSV column.

CSV saving is de-duplicated: a row is added only when its id is new, or when its title, price, status, or promotion dates changed since the last run.

## Development

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest -q
```

Tests use mocked HTTP and the fictional sample payload only; no test hits the network.

## Origin

Rebuilt in October 2026 from `WebScraping`, a July 2026 project that had three overlapping implementations of this same feed. See [CHANGELOG.md](CHANGELOG.md) for what changed, including the breaking changes. The stale CSV snapshots from the original are not shipped.

## License

MIT. See [LICENSE](LICENSE).
