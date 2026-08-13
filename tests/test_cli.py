from __future__ import annotations

import json

import pytest

from banxico_sie_catalog.cli import main
from banxico_sie_catalog.crawler import CrawlFailure, CrawlReport
from banxico_sie_catalog.export import write_snapshot
from banxico_sie_catalog.models import Series


def _snapshot(tmp_path):
    records = [
        Series(
            id="SF1",
            title="Tipo de cambio FIX FIX",
            sector="Tipos de cambio",
            table_id="CF1",
            table_title="Tipo de cambio",
            source_url="https://example.test/1",
            extracted_at="2026-08-12T00:00:00+00:00",
            frequency="Diaria",
        ),
        Series(
            id="SF2",
            title="FIX histórico",
            sector="Tipos de cambio",
            table_id="CF2",
            table_title="Histórico",
            source_url="https://example.test/2",
            extracted_at="2026-08-12T00:00:00+00:00",
            frequency="Mensual",
        ),
    ]
    write_snapshot(records, tmp_path)
    return tmp_path / "catalog.sqlite"


def test_search_returns_ranked_json_results(tmp_path, capsys, monkeypatch) -> None:
    database = _snapshot(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "banxico-sie-catalog",
            "search",
            "FIX",
            "--database",
            str(database),
            "--json",
        ],
    )

    assert main() == 0
    records = json.loads(capsys.readouterr().out)
    assert [record["id"] for record in records] == ["SF1", "SF2"]
    assert records[0]["title"] == "Tipo de cambio FIX FIX"


@pytest.mark.parametrize(
    ("flag", "value", "expected_ids"),
    [
        ("--sector", "Tipos de cambio", ["SF1", "SF2"]),
        ("--table", "CF1", ["SF1"]),
        ("--frequency", "Diaria", ["SF1"]),
        ("--series-id", "SF1", ["SF1"]),
    ],
)
def test_search_filters_results(tmp_path, capsys, monkeypatch, flag, value, expected_ids) -> None:
    database = _snapshot(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "banxico-sie-catalog",
            "search",
            "FIX",
            "--database",
            str(database),
            flag,
            value,
            "--json",
        ],
    )

    assert main() == 0
    assert [record["id"] for record in json.loads(capsys.readouterr().out)] == expected_ids


def test_show_and_no_match_exit_codes(tmp_path, capsys, monkeypatch) -> None:
    database = _snapshot(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["banxico-sie-catalog", "show", "SF2", "--database", str(database)]
    )
    assert main() == 0
    assert "id: SF2" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv", ["banxico-sie-catalog", "search", "absent", "--database", str(database)]
    )
    assert main() == 1
    assert capsys.readouterr().out == "No catalog records matched the query.\n"


def test_missing_snapshot_is_an_error(capsys, monkeypatch, tmp_path) -> None:
    database = tmp_path / "missing.sqlite"
    monkeypatch.setattr(
        "sys.argv", ["banxico-sie-catalog", "show", "SF1", "--database", str(database)]
    )

    assert main() == 2
    assert f"Catalog snapshot not found: {database}" in capsys.readouterr().out


def test_crawl_require_complete_does_not_write_snapshot(capsys, monkeypatch, tmp_path) -> None:
    class FailedCrawler:
        def __init__(self, **kwargs) -> None:
            self.report = CrawlReport(started_at="2026-08-13T00:00:00+00:00")

        def crawl_with_report(self, limit_sectors):
            self.report.failed_urls = [CrawlFailure("https://example.test", "unavailable", 3)]
            return [], self.report

    monkeypatch.setattr("banxico_sie_catalog.cli.SIECrawler", FailedCrawler)
    monkeypatch.setattr(
        "sys.argv",
        ["banxico-sie-catalog", "crawl", "--output-dir", str(tmp_path), "--require-complete"],
    )

    assert main() == 2
    assert "Crawl did not complete" in capsys.readouterr().out
    assert (tmp_path / "crawl-report.json").is_file()
    assert not (tmp_path / "catalog.json").exists()
