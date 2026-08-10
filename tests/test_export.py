import json
import sqlite3

from banxico_sie_catalog.export import write_snapshot
from banxico_sie_catalog.models import Series


def test_write_snapshot_creates_json_and_searchable_sqlite(tmp_path) -> None:
    record = Series(
        id="SF43718",
        title="FIX",
        sector="Tipos de cambio",
        table_id="CF1",
        table_title="Tipo de cambio",
        source_url="https://example.test",
        extracted_at="now",
    )
    write_snapshot([record], tmp_path)
    assert json.loads((tmp_path / "catalog.json").read_text())[0]["id"] == "SF43718"
    database = sqlite3.connect(tmp_path / "catalog.sqlite")
    try:
        result = database.execute(
            "SELECT id FROM series_search WHERE series_search MATCH 'FIX'"
        ).fetchone()
        assert result == ("SF43718",)
    finally:
        database.close()
