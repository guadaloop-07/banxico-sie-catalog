import json
import sqlite3

import pytest

from banxico_sie_catalog.export import write_snapshot
from banxico_sie_catalog.models import Series
from banxico_sie_catalog.validation import SnapshotValidationError, validate_snapshot


def test_write_snapshot_creates_json_and_searchable_sqlite(tmp_path) -> None:
    record = Series(
        id="SF43718",
        title="FIX",
        sector="Tipos de cambio",
        table_id="CF1",
        table_title="Tipo de cambio",
        source_url="https://example.test",
        extracted_at="2026-08-12T00:00:00+00:00",
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
    report = json.loads((tmp_path / "validation-report.json").read_text())
    assert report["valid"] is True
    assert report["previous_snapshot"] is None
    assert report["warnings"][0]["missing_fields"] == [
        "period",
        "frequency",
        "units",
        "figure_type",
    ]


def test_write_snapshot_rejects_invalid_records_and_writes_report(tmp_path) -> None:
    record = Series(
        id="SF1",
        title="",
        sector="Sector",
        table_id="CF1",
        table_title="Table",
        source_url="not-a-url",
        extracted_at="not-a-timestamp",
    )

    with pytest.raises(SnapshotValidationError):
        write_snapshot([record], tmp_path)

    report = json.loads((tmp_path / "validation-report.json").read_text())
    assert report["valid"] is False
    assert {error["code"] for error in report["errors"]} == {
        "required_field",
        "source_url",
        "extracted_at",
    }
    assert not (tmp_path / "catalog.json").exists()
    assert not (tmp_path / "catalog.sqlite").exists()


def test_validate_snapshot_reports_duplicates_and_changes() -> None:
    prior = [
        {
            "id": "SF1",
            "title": "Original title",
            "sector": "Sector",
            "table_id": "CF1",
            "table_title": "Table",
            "source_url": "https://example.test/1",
            "extracted_at": "2026-08-01T00:00:00+00:00",
            "period": None,
            "frequency": None,
            "units": None,
            "figure_type": None,
        },
        {"id": "SF2"},
    ]
    records = [
        Series(
            id="SF1",
            title="Updated title",
            sector="Sector",
            table_id="CF1",
            table_title="Table",
            source_url="https://example.test/1",
            extracted_at="2026-08-12T00:00:00+00:00",
        ),
        Series(
            id="SF1",
            title="Duplicate",
            sector="Sector",
            table_id="CF2",
            table_title="Other table",
            source_url="https://example.test/2",
            extracted_at="2026-08-12T00:00:00+00:00",
        ),
        Series(
            id="SF3",
            title="New series",
            sector="Sector",
            table_id="CF3",
            table_title="New table",
            source_url="https://example.test/3",
            extracted_at="2026-08-12T00:00:00+00:00",
        ),
    ]

    report = validate_snapshot(records, prior)

    assert report["valid"] is False
    assert report["changes"] == {
        "additions": ["SF3"],
        "removals": ["SF2"],
        "changed_records": [
            {
                "series_id": "SF1",
                "changed_fields": ["source_url", "table_id", "table_title", "title"],
            }
        ],
    }
    assert [error["code"] for error in report["errors"]] == ["duplicate_id"]


def test_write_snapshot_reports_changes_from_a_prior_catalog(tmp_path) -> None:
    prior_snapshot = tmp_path / "prior.json"
    prior_snapshot.write_text(
        json.dumps(
            [
                {
                    "id": "SF1",
                    "title": "Prior title",
                    "sector": "Sector",
                    "table_id": "CF1",
                    "table_title": "Table",
                    "source_url": "https://example.test/1",
                    "extracted_at": "2026-08-01T00:00:00+00:00",
                    "period": None,
                    "frequency": None,
                    "units": None,
                    "figure_type": None,
                }
            ]
        )
    )
    record = Series(
        id="SF1",
        title="Current title",
        sector="Sector",
        table_id="CF1",
        table_title="Table",
        source_url="https://example.test/1",
        extracted_at="2026-08-12T00:00:00+00:00",
    )

    write_snapshot([record], tmp_path / "current", prior_snapshot)

    report = json.loads((tmp_path / "current" / "validation-report.json").read_text())
    assert report["previous_snapshot"] == str(prior_snapshot)
    assert report["changes"]["changed_records"] == [
        {"series_id": "SF1", "changed_fields": ["title"]}
    ]
