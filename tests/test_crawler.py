from __future__ import annotations

import json
from unittest.mock import patch
from urllib.error import URLError

from banxico_sie_catalog.crawler import CrawlReport, SIECrawler
from banxico_sie_catalog.report import write_crawl_report


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_fetch_retries_transient_errors() -> None:
    crawler = SIECrawler(delay_seconds=0, backoff_seconds=0, max_retries=2)
    responses = [URLError("temporary"), _Response(b"ok")]

    with (
        patch("banxico_sie_catalog.crawler.urlopen", side_effect=responses),
        patch("banxico_sie_catalog.crawler.time.sleep"),
    ):
        assert crawler.fetch("https://example.test") == "ok"

    assert crawler.report.retry_count == 1
    assert crawler.report.fetched_pages == 1


def test_crawl_reports_and_skips_failed_table_urls() -> None:
    home_url = "https://www.banxico.org.mx/SieInternet/"
    sector_url = f"{home_url}consultarDirectorioCuadros?sector=1"
    pages = {
        home_url: b'<a href="consultarDirectorioCuadros?sector=1">Sector</a>',
        sector_url: b'<a href="table?idCuadro=CF1">Tabla</a>',
    }

    def fake_urlopen(request, timeout):
        url = request.full_url
        if url in pages:
            return _Response(pages[url])
        raise URLError("unavailable")

    crawler = SIECrawler(delay_seconds=0, backoff_seconds=0, max_retries=1)
    with (
        patch("banxico_sie_catalog.crawler.urlopen", side_effect=fake_urlopen),
        patch("banxico_sie_catalog.crawler.time.sleep"),
    ):
        records, report = crawler.crawl_with_report()

    assert records == []
    assert report.fetched_pages == 2
    assert report.retry_count == 1
    assert report.parsed_series == 0
    assert report.skipped_urls == ["https://www.banxico.org.mx/SieInternet/table?idCuadro=CF1"]
    assert report.failed_urls[0].attempts == 2


def test_write_crawl_report_is_machine_readable(tmp_path) -> None:
    report = CrawlReport(started_at="2026-08-13T00:00:00+00:00", fetched_pages=3, parsed_series=12)

    path = write_crawl_report(report, tmp_path)

    assert json.loads(path.read_text()) == {
        "started_at": "2026-08-13T00:00:00+00:00",
        "finished_at": None,
        "fetched_pages": 3,
        "parsed_series": 12,
        "skipped_urls": [],
        "failed_urls": [],
        "retry_count": 0,
    }
