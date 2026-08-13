"""HTML parsers for the public SIE hierarchy.

The SIE is server-rendered but its markup is not a stable public API. Parsers
therefore extract from URLs and accessible attributes first, while retaining the
source URL in every output record for later audit.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

from .models import Sector, Series, Table

_SERIES_ID = re.compile(r"\bS[FP]\d+\b", re.IGNORECASE)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[dict[str, str], str]] = []
        self._attrs: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._attrs = {key: value or "" for key, value in attrs}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._attrs is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._attrs is not None:
            self.links.append((self._attrs, " ".join(self._text).strip()))
            self._attrs = None
            self._text = []


def _links(html: str) -> list[tuple[dict[str, str], str]]:
    parser = _LinkParser()
    parser.feed(html)
    return parser.links


def _query_id(url: str, key: str) -> str | None:
    return parse_qs(urlparse(url).query).get(key, [None])[0]


def parse_sectors(html: str, base_url: str) -> list[Sector]:
    sectors: dict[str, Sector] = {}
    for attrs, text in _links(html):
        href = attrs.get("href", "")
        if "sector=" not in href or "consultarDirectorioCuadros" not in href:
            continue
        url = urljoin(base_url, href)
        sector = Sector(name=" ".join(text.split()), url=url)
        sectors[sector.url] = sector
    return list(sectors.values())


def parse_tables(html: str, base_url: str, sector: str) -> list[Table]:
    tables: dict[str, Table] = {}
    for attrs, text in _links(html):
        href = attrs.get("href", "")
        table_id = _query_id(href, "idCuadro")
        if not table_id:
            continue
        url = urljoin(base_url, href)
        tables[table_id] = Table(
            id=table_id,
            title=" ".join(text.split()),
            sector=sector,
            url=url,
        )
    return list(tables.values())


def _clean(value: str) -> str | None:
    return " ".join(value.replace("\xa0", " ").split()).strip() or None


def _series_title(value: str) -> str | None:
    title = _clean(value)
    return re.sub(r"^Seleccionar serie\s+", "", title, flags=re.IGNORECASE) if title else None


def _metadata(html: str, label: str) -> str | None:
    pattern = re.compile(rf"{label}\s*[:：]\s*(?:</?[^>]+>\s*)*(?P<value>[^<\n]+)", re.I | re.S)
    match = pattern.search(html)
    return _clean(match.group("value")) if match else None


def parse_series(html: str, table: Table, extracted_at: str) -> list[Series]:
    """Extract series exposed as IDs in links or data/input attributes.

    The input-name fallback supports current SIE pages; title extraction is kept
    conservative so a change in markup does not silently invent metadata.
    """
    decoded_html = unescape(html)
    label_titles = {
        match.group("series").upper(): _series_title(re.sub(r"<[^>]+>", " ", match.group("title")))
        for match in re.finditer(
            r'<label[^>]*for="[^"]*(?P<series>S[FP]\d+)"[^>]*>(?P<title>.*?)</label>',
            decoded_html,
            re.IGNORECASE | re.DOTALL,
        )
    }
    candidates: list[tuple[str, str]] = []
    for attrs, text in _links(html):
        attrs_text = " ".join(attrs.values())
        match = _SERIES_ID.search(f"{attrs_text} {text}")
        if match:
            candidates.append((match.group(0).upper(), _clean(text) or match.group(0).upper()))

    for match in re.finditer(r"<(?:input|option)[^>]+>", decoded_html, re.I):
        tag = match.group(0)
        id_match = _SERIES_ID.search(tag)
        if id_match:
            series_id = id_match.group(0).upper()
            candidates.append((series_id, label_titles.get(series_id) or series_id))

    metadata = {
        "period": _metadata(decoded_html, "Per[ií]odo"),
        "frequency": _metadata(decoded_html, "Frecuencia"),
        "units": _metadata(decoded_html, "Unidades"),
        "figure_type": _metadata(decoded_html, "Cifra"),
    }
    found: dict[str, Series] = {}
    for series_id, title in candidates:
        found.setdefault(
            series_id,
            Series(
                id=series_id,
                title=title,
                sector=table.sector,
                table_id=table.id,
                table_title=table.title,
                source_url=table.url,
                extracted_at=extracted_at,
                **metadata,
            ),
        )
    return list(found.values())
