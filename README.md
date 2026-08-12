# banxico-sie-catalog

A small, reproducible pipeline that builds a searchable catalog of Banco de México’s SIE time series by crawling its public information structure, normalizing series metadata, and producing versioned SQLite and JSON snapshots for downstream tools and MCP servers.

## Status

This is the first, catalog-only phase. It crawls the public SIE hierarchy (sector →
table → series), normalizes the discovered metadata, and writes portable JSON and
SQLite snapshots. It does not download observations and it does not require a
Banxico API token.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
banxico-sie-catalog crawl --output-dir data --delay 1
```

The command creates `data/catalog.json`, `data/catalog.sqlite`, and a
timestamped manifest. `data/` is intentionally ignored by Git: snapshots should
be published as release artifacts or in a dedicated data repository.

## Query a local snapshot

Search the SQLite full-text index without crawling SIE again:

```bash
banxico-sie-catalog search "tipo de cambio" --database data/catalog.sqlite --limit 10
banxico-sie-catalog search FIX --sector "Tipos de cambio" --json
banxico-sie-catalog show SF43718 --database data/catalog.sqlite --json
```

`search` supports exact filters for `--sector`, `--table`, `--frequency`, and
`--series-id`. It exits with status 1 when no records match and status 2 when
the snapshot is missing or cannot be queried.

## Development

```bash
pytest
ruff check .
ruff format --check .
```

The parser is covered with saved HTML fixtures. When the SIE changes, add the
new HTML as a fixture before changing parser behaviour.

## Data provenance and operating rules

- The public SIE is the source of catalog metadata; each record retains its
  source URL and extraction timestamp.
- The crawler is deliberately polite: it uses a descriptive User-Agent, caches
  fetched pages in memory during a run, and waits between requests.
- Do not run broad crawls interactively or on every MCP request. Refresh a
  snapshot on a scheduled cadence (for example, monthly).
- The documented collection endpoint is currently unavailable in the deployed
  SIE API. Series-specific API routes may be used later to validate known IDs.
