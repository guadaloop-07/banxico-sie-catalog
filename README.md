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

## Validate known series through the API

API enrichment is optional and never changes scraped catalog provenance. Supply
the API token only through the `BMX_TOKEN` environment variable, then validate
explicit known IDs in batches of at most 20:

```bash
export BMX_TOKEN="your-secret-token"
banxico-sie-catalog enrich SF43718 SF46410 --output data/api-validation.json
```

The API-only report records returned metadata, invalid IDs, failed batches, and
its own validation timestamp. It never writes the token to a snapshot or report.

## Serve a snapshot over MCP

### Local setup with Python

Create an isolated environment and install the released server version:

```bash
mkdir banxico-sie-mcp && cd banxico-sie-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/guadaloop-07/banxico-sie-catalog.git@v0.1.0"
```

Download and unpack the catalog release (or download the ZIP from the release page in a browser):

```bash
gh release download v0.1.0 --repo guadaloop-07/banxico-sie-catalog --dir downloads
unzip downloads/banxico-sie-catalog-v0.1.0-snapshot.zip -d snapshot
```

Start the local read-only server with the absolute SQLite path. The MCP client should be configured to run this exact command:

```bash
banxico-sie-catalog-mcp --database "$(pwd)/snapshot/catalog.sqlite"
```

No Banxico token is needed at runtime: the server only reads the downloaded catalog. Keep the virtual environment and snapshot directory together so upgrading is just a matter of replacing `snapshot/` with a newer validated release.

The optional MCP server always exposes the four local catalog tools without a
token: `search_series`, `get_series`, `get_sectors`, and `get_tables`. It also
registers two read-only tools for live SIE observations; invoking either one
requires `BMX_TOKEN`. Every response includes snapshot
metadata from `manifest.json`; when `provenance.json` is beside the manifest,
that workflow provenance is included too. Pass `--manifest` when the manifest
is stored elsewhere.

### Consult live observations with your Banxico token

The catalog tools remain available without a token and without network access.
To retrieve the latest value or an observation range from the SIE API, set
`BMX_TOKEN` in the environment that starts the MCP server. Without it, a live
tool returns an actionable configuration error. Do not put the token in an MCP
tool call, a project configuration file, or a snapshot.

```bash
export BMX_TOKEN="your-secret-token"
banxico-sie-catalog-mcp --database /absolute/path/to/catalog.sqlite
```

The MCP server first confirms that the requested ID exists in the local catalog,
then exposes two additional read-only tools:

- `get_latest_observation(series_id)` returns the latest published observation.
- `get_observations(series_id, start_date, end_date)` returns an inclusive date
  range; dates must use `YYYY-MM-DD`.

Each live response includes the catalog record, the API response title, the
requested range when applicable, and a UTC query timestamp. Values are preserved
as published by SIE, including non-numeric markers such as `N/E`.

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
