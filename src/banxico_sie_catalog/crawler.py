from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Series
from .parser import parse_sectors, parse_series, parse_tables

SIE_HOME = "https://www.banxico.org.mx/SieInternet/"
USER_AGENT = "banxico-sie-catalog/0.1 (+https://github.com/your-org/banxico-sie-catalog)"


@dataclass(frozen=True, slots=True)
class CrawlFailure:
    url: str
    error: str
    attempts: int


@dataclass(slots=True)
class CrawlReport:
    started_at: str
    finished_at: str | None = None
    fetched_pages: int = 0
    parsed_series: int = 0
    skipped_urls: list[str] = field(default_factory=list)
    failed_urls: list[CrawlFailure] = field(default_factory=list)
    retry_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class CrawlError(Exception):
    """Raised when the crawler cannot fetch a required page."""

    def __init__(self, failure: CrawlFailure) -> None:
        super().__init__(
            f"Could not fetch {failure.url} after {failure.attempts} attempts: {failure.error}"
        )
        self.failure = failure


def _decode_html(payload: bytes) -> str:
    """Decode current SIE pages, which are served with mixed legacy encodings."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("latin-1")


class SIECrawler:
    def __init__(
        self,
        delay_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._cache: dict[str, str] = {}
        self.report = CrawlReport(started_at=datetime.now(UTC).isoformat())

    def fetch(self, url: str) -> str:
        if url in self._cache:
            return self._cache[url]
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"})
        for attempt in range(1, self.max_retries + 2):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                    html = _decode_html(response.read())
            except (HTTPError, URLError, OSError) as error:
                if attempt > self.max_retries:
                    raise CrawlError(CrawlFailure(url, str(error), attempt)) from error
                self.report.retry_count += 1
                time.sleep(self.backoff_seconds * 2 ** (attempt - 1))
                continue
            self._cache[url] = html
            self.report.fetched_pages += 1
            time.sleep(self.delay_seconds)
            return html
        raise AssertionError("unreachable")

    def crawl(self, limit_sectors: int | None = None) -> list[Series]:
        records, _ = self.crawl_with_report(limit_sectors)
        return records

    def crawl_with_report(
        self, limit_sectors: int | None = None
    ) -> tuple[list[Series], CrawlReport]:
        self.report = CrawlReport(started_at=datetime.now(UTC).isoformat())
        home = self.fetch(SIE_HOME)
        sectors = parse_sectors(home, SIE_HOME)
        if limit_sectors is not None:
            sectors = sectors[:limit_sectors]

        extracted_at = datetime.now(UTC).isoformat()
        catalog: dict[str, Series] = {}
        for sector in sectors:
            try:
                directory = self.fetch(sector.url)
            except CrawlError as error:
                self.report.skipped_urls.append(sector.url)
                self.report.failed_urls.append(error.failure)
                continue
            for table in parse_tables(directory, sector.url, sector.name):
                try:
                    table_html = self.fetch(table.url)
                except CrawlError as error:
                    self.report.skipped_urls.append(table.url)
                    self.report.failed_urls.append(error.failure)
                    continue
                for series in parse_series(table_html, table, extracted_at):
                    catalog.setdefault(series.id, series)
        records = sorted(catalog.values(), key=lambda item: item.id)
        self.report.parsed_series = len(records)
        self.report.finished_at = datetime.now(UTC).isoformat()
        return records, self.report
