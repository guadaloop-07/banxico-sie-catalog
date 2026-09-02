"""Read-only MCP server for a local Banco de México SIE catalog snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from .api import BanxicoAPIError, SIEAPIClient
from .catalog import CatalogError, list_sectors, list_tables, search, show

MAX_SEARCH_RESULTS = 100


def _snapshot_metadata(database_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Return portable version and provenance metadata for the loaded snapshot."""
    metadata: dict[str, Any] = {
        "database": str(database_path),
        "manifest": None,
        "provenance": None,
    }
    if not manifest_path.is_file():
        return metadata
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"Could not read catalog manifest {manifest_path}: {error}") from error
    if not isinstance(manifest, dict):
        raise CatalogError(f"Catalog manifest must contain an object: {manifest_path}")
    metadata["manifest"] = {
        key: manifest.get(key) for key in ("generated_at", "record_count", "schema_version")
    }
    provenance_path = manifest_path.with_name("provenance.json")
    if provenance_path.is_file():
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CatalogError(
                f"Could not read snapshot provenance {provenance_path}: {error}"
            ) from error
        if not isinstance(provenance, dict):
            raise CatalogError(f"Snapshot provenance must contain an object: {provenance_path}")
        metadata["provenance"] = provenance
    return metadata


def _result(database_path: Path, manifest_path: Path, **payload: Any) -> dict[str, Any]:
    return {"snapshot": _snapshot_metadata(database_path, manifest_path), **payload}


def create_server(
    database_path: Path,
    manifest_path: Path | None = None,
    *,
    api_client: SIEAPIClient | None = None,
) -> MCPServer:
    """Create a local catalog server with optional token-backed live data tools."""
    snapshot = database_path.resolve()
    manifest = (manifest_path or snapshot.with_name("manifest.json")).resolve()
    client = api_client or SIEAPIClient()
    mcp = MCPServer("Banxico SIE Catalog")

    @mcp.tool()
    def search_series(
        query: str,
        limit: int = 20,
        sector: str | None = None,
        table_id: str | None = None,
        frequency: str | None = None,
        series_id: str | None = None,
    ) -> dict[str, Any]:
        """Search the local catalog. This never crawls SIE or uses a Banxico token."""
        if not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise ValueError(f"limit must be between 1 and {MAX_SEARCH_RESULTS}")
        return _result(
            snapshot,
            manifest,
            records=search(
                snapshot,
                query,
                limit=limit,
                sector=sector,
                table_id=table_id,
                frequency=frequency,
                series_id=series_id,
            ),
        )

    @mcp.tool()
    def get_series(series_id: str) -> dict[str, Any]:
        """Look up one SIE series by its exact ID in the local catalog."""
        return _result(snapshot, manifest, record=show(snapshot, series_id))

    @mcp.tool()
    def get_sectors() -> dict[str, Any]:
        """List the sectors present in the local catalog snapshot."""
        return _result(snapshot, manifest, sectors=list_sectors(snapshot))

    @mcp.tool()
    def get_tables(sector: str | None = None) -> dict[str, Any]:
        """List catalog tables, optionally filtering by their exact sector name."""
        return _result(snapshot, manifest, tables=list_tables(snapshot, sector=sector))

    @mcp.tool()
    def get_latest_observation(series_id: str) -> dict[str, Any]:
        """Get the latest API observation for a catalog series. Requires local BMX_TOKEN."""
        record = show(snapshot, series_id)
        if record is None:
            raise ValueError(f"No catalog record found for series ID: {series_id}")
        try:
            live_data = client.latest_observation(series_id)
        except BanxicoAPIError as error:
            return _result(
                snapshot,
                manifest,
                catalog_record=record,
                error={"code": "live_data_unavailable", "message": str(error)},
            )
        return _result(snapshot, manifest, catalog_record=record, live_data=live_data)

    @mcp.tool()
    def get_observations(series_id: str, start_date: str, end_date: str) -> dict[str, Any]:
        """Get API observations in an inclusive YYYY-MM-DD range. Requires local BMX_TOKEN."""
        record = show(snapshot, series_id)
        if record is None:
            raise ValueError(f"No catalog record found for series ID: {series_id}")
        try:
            live_data = client.observations(series_id, start_date, end_date)
        except BanxicoAPIError as error:
            return _result(
                snapshot,
                manifest,
                catalog_record=record,
                error={"code": "live_data_unavailable", "message": str(error)},
            )
        return _result(snapshot, manifest, catalog_record=record, live_data=live_data)

    return mcp


def main() -> None:
    """Run the read-only server over stdio for an MCP host."""
    parser = argparse.ArgumentParser(description="Serve a local Banxico SIE catalog over MCP.")
    parser.add_argument("--database", type=Path, default=Path("data/catalog.sqlite"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    create_server(args.database, args.manifest).run()


if __name__ == "__main__":
    main()
