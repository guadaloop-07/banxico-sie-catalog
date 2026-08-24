"""Read-only queries over a local catalog SQLite snapshot."""

from __future__ import annotations

import sqlite3
from pathlib import Path

RECORD_COLUMNS = """
    s.id, s.title, s.sector, s.table_id, s.table_title, s.source_url,
    s.extracted_at, s.period, s.frequency, s.units, s.figure_type
"""


class CatalogError(Exception):
    """Raised when a catalog snapshot cannot be queried."""


def _connect(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise CatalogError(f"Catalog snapshot not found: {database_path}")
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as error:
        raise CatalogError(f"Could not open catalog snapshot {database_path}: {error}") from error


def _records(rows: list[sqlite3.Row]) -> list[dict[str, str | None]]:
    return [dict(row) for row in rows]


def search(
    database_path: Path,
    query: str,
    *,
    limit: int = 20,
    sector: str | None = None,
    table_id: str | None = None,
    frequency: str | None = None,
    series_id: str | None = None,
) -> list[dict[str, str | None]]:
    """Return FTS-ranked catalog records matching a query and optional filters."""
    filters: list[str] = []
    values: list[str | int] = [query]
    for column, value in (
        ("s.sector", sector),
        ("s.table_id", table_id),
        ("s.frequency", frequency),
        ("s.id", series_id),
    ):
        if value is not None:
            filters.append(f"{column} = ?")
            values.append(value)

    where_clause = f" AND {' AND '.join(filters)}" if filters else ""
    values.append(limit)
    statement = f"""
        SELECT {RECORD_COLUMNS}
        FROM series_search
        JOIN series AS s ON s.id = series_search.id
        WHERE series_search MATCH ?{where_clause}
        ORDER BY bm25(series_search), s.id
        LIMIT ?
    """
    try:
        with _connect(database_path) as database:
            return _records(database.execute(statement, values).fetchall())
    except sqlite3.Error as error:
        raise CatalogError(f"Could not query catalog snapshot {database_path}: {error}") from error


def show(database_path: Path, series_id: str) -> dict[str, str | None] | None:
    """Return a complete catalog record by its exact SIE series ID."""
    statement = f"SELECT {RECORD_COLUMNS} FROM series AS s WHERE s.id = ?"
    try:
        with _connect(database_path) as database:
            row = database.execute(statement, [series_id]).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as error:
        raise CatalogError(f"Could not query catalog snapshot {database_path}: {error}") from error
