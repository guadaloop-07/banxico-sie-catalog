# Connect the local catalog to Codex

For most users, the published installer is the supported path. It installs a
verified snapshot, stores the personal Banxico token in the desktop keyring, and
registers the local stdio MCP server with Codex.

## Standard setup

Requirements are Python 3.11+, Codex, a desktop Linux session with an available
system keyring, and a personal Banxico token.

```bash
python -m pip install \
  "https://github.com/guadaloop-07/banxico-sie-catalog/releases/download/v0.1.1/banxico_sie_catalog-0.1.1-py3-none-any.whl"

banxico-sie-catalog setup-codex --release v0.1.1
```

The command validates and stores the token in the system keyring, downloads and
validates the `v0.1.1` catalog snapshot, registers `banxico_sie_catalog`, and
offers monthly updates. It can also repair an existing registration.

The token is never written to `config.toml`, an MCP tool call, an `.env` file,
the snapshot, or a report. The MCP retrieves it from the system keyring when it
needs live data.

## Validate the connection

```bash
codex mcp list
banxico-sie-catalog doctor
```

Start a new Codex session, enter `/mcp`, and verify that `banxico_sie_catalog`
is connected. Then ask:

> Use `search_series` to find "tipo de cambio" and show the first three results.

The local catalog tools work against the downloaded snapshot:

- `search_series`
- `get_series`
- `get_sectors`
- `get_tables`

The live tools use the Banxico API and require the keyring token:

- `get_latest_observation(series_id)`
- `get_observations(series_id, start_date, end_date)`

Live requests first verify that the series exists in the local catalog. A result
also includes snapshot metadata; range dates use `YYYY-MM-DD`.

## Maintenance

```bash
# Non-secret status: keyring, token, installed catalog, and last update.
banxico-sie-catalog doctor

# Securely replace the saved token.
banxico-sie-catalog update-token

# Download, verify, and atomically activate the selected release.
banxico-sie-catalog update-now --release v0.1.1

# Enable the Linux per-user systemd timer for monthly verified updates.
banxico-sie-catalog updates-monthly --release v0.1.1
```

`updates-monthly` requires Linux with `systemd --user`; it schedules a timer and
does not keep a process running.

## Advanced: manual registration

Use this only when you need to choose the directory or register the MCP yourself.
Create a virtual environment, install the same `v0.1.1` wheel, and install the
verified snapshot:

```bash
mkdir banxico-sie-mcp && cd banxico-sie-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install \
  "https://github.com/guadaloop-07/banxico-sie-catalog/releases/download/v0.1.1/banxico_sie_catalog-0.1.1-py3-none-any.whl"
banxico-sie-catalog install-catalog v0.1.1 --output-dir snapshot
```

Store the token first with `banxico-sie-catalog update-token`, then register the
server with absolute paths:

```bash
codex mcp add banxico_sie_catalog -- \
  "$(pwd)/.venv/bin/banxico-sie-catalog-mcp" \
  --database "$(pwd)/snapshot/catalog.sqlite"
```

If manual configuration is necessary, copy the
[`codex-mcp.toml`](codex-mcp.toml) table into `~/.codex/config.toml` (or a
trusted project's `.codex/config.toml`) and replace the absolute paths. Do not
put the token in that file. Codex starts the server independently, so do not use
`~` or relative paths. See the [official Codex MCP documentation](https://developers.openai.com/codex/mcp/)
for available MCP configuration options.
