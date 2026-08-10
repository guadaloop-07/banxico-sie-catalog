from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from .models import Series
from .parser import parse_sectors, parse_series, parse_tables

SIE_HOME = "https://www.banxico.org.mx/SieInternet/"
USER_AGENT = "banxico-sie-catalog/0.1 (+https://github.com/your-org/banxico-sie-catalog)"


def _decode_html(payload: bytes) -> str:
    """Decode current SIE pages, which are served with mixed legacy encodings."""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("latin-1")


class SIECrawler:
    def __init__(self, delay_seconds: float = 1.0, timeout_seconds: float = 30.0) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, str] = {}

    def fetch(self, url: str) -> str:
        if url in self._cache:
            return self._cache[url]
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"})
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            html = _decode_html(response.read())
        self._cache[url] = html
        time.sleep(self.delay_seconds)
        return html

    def crawl(self, limit_sectors: int | None = None) -> list[Series]:
        home = self.fetch(SIE_HOME)
        sectors = parse_sectors(home, SIE_HOME)
        if limit_sectors is not None:
            sectors = sectors[:limit_sectors]

        extracted_at = datetime.now(UTC).isoformat()
        catalog: dict[str, Series] = {}
        for sector in sectors:
            for table in parse_tables(self.fetch(sector.url), sector.url, sector.name):
                for series in parse_series(self.fetch(table.url), table, extracted_at):
                    catalog.setdefault(series.id, series)
        return sorted(catalog.values(), key=lambda item: item.id)
