# banxico-sie-catalog

A local, reproducible catalog of Banco de México SIE series, with an MCP server
for searching a verified snapshot and consulting live observations from the SIE
API. It produces and consumes versioned SQLite and JSON snapshots.

## Status

The published desktop experience installs a verified local catalog, registers a
local stdio MCP server with Codex, and supports both offline catalog queries and
live SIE observations. Catalog tools work from the local snapshot; live tools
use your personal Banxico token.

## Codex quick start

Requirements:

- Python 3.11 or newer
- Codex installed and available as `codex`
- A desktop Linux session with an available, unlocked system keyring
- A personal Banxico API token

Install the published wheel, then run the guided setup:

```bash
python -m pip install \
  "https://github.com/guadaloop-07/banxico-sie-catalog/releases/download/v0.1.1/banxico_sie_catalog-0.1.1-py3-none-any.whl"

banxico-sie-catalog setup-codex --release v0.1.1
```

Setup securely prompts for and validates your token, stores it in the system
keyring, downloads and validates the `v0.1.1` snapshot, registers the MCP with
Codex, and offers to enable monthly catalog updates. Start a new Codex session,
use `/mcp` to confirm `banxico_sie_catalog` is connected, then ask, for example:

> Use `search_series` to find "tipo de cambio" and show the first three results.

The MCP provides `search_series`, `get_series`, `get_sectors`, and `get_tables`
against the local snapshot, plus `get_latest_observation` and
`get_observations` for live SIE data. The live tools first verify that the
series is in the local catalog.

Your token is stored in the system keyring. Do not put it in `config.toml`, MCP
tool calls, `.env` files, snapshots, reports, or source control.

### Maintain the desktop installation

```bash
# Report keyring, token, snapshot, and update-state availability without revealing the token.
banxico-sie-catalog doctor

# Securely replace the stored Banxico token.
banxico-sie-catalog update-token

# Download, verify, and atomically activate a release now.
banxico-sie-catalog update-now --release v0.1.1

# Enable the per-user systemd timer for monthly verified updates.
banxico-sie-catalog updates-monthly --release v0.1.1
```

`updates-monthly` requires Linux with `systemd --user`; it is a timer, not a
continuously running process. Use `doctor` after setup or an update to diagnose
non-secret installation state.

## Advanced: manual MCP installation

Use this route when you need to choose the installation directory or register
the server yourself. It is not required for the standard Codex flow above.

```bash
mkdir banxico-sie-mcp && cd banxico-sie-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install \
  "https://github.com/guadaloop-07/banxico-sie-catalog/releases/download/v0.1.1/banxico_sie_catalog-0.1.1-py3-none-any.whl"
banxico-sie-catalog install-catalog v0.1.1 --output-dir snapshot
```

Register the server with absolute paths:

```bash
codex mcp add banxico_sie_catalog -- \
  "$(pwd)/.venv/bin/banxico-sie-catalog-mcp" \
  --database "$(pwd)/snapshot/catalog.sqlite"
```

For live observations in a manual installation, first run
`banxico-sie-catalog update-token`; the MCP reads the stored secret from the
system keyring. See [the detailed Codex MCP guide](docs/codex-mcp.md).

## Build or refresh a catalog (development)

To crawl the public SIE hierarchy (sector → table → series) and produce a new
snapshot from source:

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
