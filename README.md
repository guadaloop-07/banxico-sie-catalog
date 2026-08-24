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

The command creates `data/catalog.json`, `data/catalog.sqlite`, a timestamped
manifest, `data/validation-report.json`, and `data/crawl-report.json`. `data/`
is intentionally ignored by Git: snapshots should be published as release
artifacts or in a dedicated data repository.

Snapshots must have required series metadata, unique IDs, HTTP(S) source URLs,
and ISO 8601 extraction timestamps. Missing period, frequency, units, or figure
type is reported as a warning rather than blocking the snapshot. Compare a
new catalog with a prior JSON snapshot as part of the crawl:

```bash
banxico-sie-catalog crawl --output-dir data-next --previous-snapshot data/catalog.json
```

The validation report records additions, removals, and changed metadata fields.
It ignores `extracted_at`, since a new extraction time alone is not a catalog
change. If validation fails, only the report is written; the catalog JSON and
SQLite snapshot are left untouched.

The crawler retries transient request failures twice with exponential backoff.
It records fetched pages, parsed series, retries, skipped URLs, and structured
failed URLs in `crawl-report.json`; a failed sector or table is reported and
does not prevent other pages from being crawled. Use `--retries 1` to reduce
the retry count during a smoke test.

## Scheduled refreshes and artifact retention

The `Catalog refresh` GitHub Actions workflow runs monthly and can be started
manually. It runs a complete crawl with `--require-complete`, validates the
result, compares it with the most recent non-expired catalog artifact when one
exists, and publishes a uniquely named artifact containing the JSON, SQLite,
manifest, validation report, crawl report, and workflow provenance. Artifacts
are retained for 90 days; download a particular workflow run's artifact when a
consumer needs a reproducible snapshot version.

The refresh refuses to publish a new catalog when crawling or validation fails,
so the previous successful artifact remains available. Review the validation and
crawl reports before changing consumers to a newer snapshot.

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

## Serve a snapshot over MCP

The optional MCP server exposes only the chosen local SQLite snapshot: it never
crawls SIE and does not use a Banxico token. Install the project, then configure
an MCP host to run the following command with an absolute snapshot path:

```bash
banxico-sie-catalog-mcp --database /absolute/path/to/catalog.sqlite
```

It provides four read-only tools with stable object responses: `search_series`,
`get_series`, `get_sectors`, and `get_tables`. Every response includes snapshot
metadata from `manifest.json`; when `provenance.json` is beside the manifest,
that workflow provenance is included too. Pass `--manifest` when the manifest
is stored elsewhere.

## Development

```bash
pytest
ruff check .
ruff format --check .
```

The parser is covered with saved HTML fixtures. When the SIE changes, add the
new HTML as a fixture before changing parser behaviour.

### Crawler maintenance

The parser supports SIE sector and table links, plus series IDs exposed in
links, inputs, or options. It normalizes whitespace, retains the first record
when an ID is repeated in a page, and treats unavailable optional metadata as
validation warnings. When markup changes, save a sanitized page that captures
the new layout in `tests/fixtures/`, add a parser assertion for the expected
IDs and metadata, then update the parser. Review `crawl-report.json` after each
refresh: failed URLs require investigation before treating the snapshot as a
complete portal catalog.

## Data provenance and operating rules

- The public SIE is the source of catalog metadata; each record retains its
  source URL and extraction timestamp.
- The crawler is deliberately polite: it uses a descriptive User-Agent, caches
  fetched pages in memory during a run, and waits between requests.
- Do not run broad crawls interactively or on every MCP request. Refresh a
  snapshot on a scheduled cadence (for example, monthly).
- The documented collection endpoint is currently unavailable in the deployed
  SIE API. Series-specific API routes may be used later to validate known IDs.
