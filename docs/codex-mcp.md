# Connect the local catalog to Codex

This guide configures the local stdio server with absolute paths. The catalog
search tools work entirely offline and do not require `BMX_TOKEN`.

## Prerequisites

Follow the [local Python setup](../README.md#local-setup-with-python) to create
the virtual environment and unpack a catalog release. In the examples below,
the resulting directory is `/absolute/path/to/banxico-sie-mcp`.

Before configuring Codex, confirm both paths exist:

```bash
test -x /absolute/path/to/banxico-sie-mcp/.venv/bin/banxico-sie-catalog-mcp
test -f /absolute/path/to/banxico-sie-mcp/snapshot/catalog.sqlite
```

## Add the server with the Codex CLI

Run this command after replacing the two absolute paths:

```bash
codex mcp add banxico_sie_catalog -- \
  /absolute/path/to/banxico-sie-mcp/.venv/bin/banxico-sie-catalog-mcp \
  --database /absolute/path/to/banxico-sie-mcp/snapshot/catalog.sqlite
```

To configure it manually instead, copy the
[`codex-mcp.toml`](codex-mcp.toml) table into `~/.codex/config.toml` (or a
trusted project's `.codex/config.toml`) and replace every absolute path.
Do not use `~` or relative paths: Codex starts the server as a separate process.

The configuration is shared by the Codex CLI, IDE extension, and ChatGPT
desktop app on the same host. For the available configuration options, see the
[official Codex MCP documentation](https://developers.openai.com/codex/mcp/).

## Validate the connection

```bash
codex mcp list
```

The output should list `banxico_sie_catalog`. Start a new Codex session, enter
`/mcp`, and verify that the server is connected. Then ask Codex:

> Use `search_series` to find "tipo de cambio" and show the first three results.

A successful result includes catalog records and snapshot metadata. If the
server is not connected, verify the two paths above, then restart Codex after
editing its configuration.

## Optional live observations

The default setup exposes the four local catalog tools only. To enable
`get_latest_observation` and `get_observations`, set `BMX_TOKEN` in the
environment that starts Codex and uncomment `env_vars = ["BMX_TOKEN"]` in the
template. Do not put the token directly in `config.toml`, tool calls, or the
snapshot.
