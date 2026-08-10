from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class Sector:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class Table:
    id: str
    title: str
    sector: str
    url: str


@dataclass(frozen=True, slots=True)
class Series:
    id: str
    title: str
    sector: str
    table_id: str
    table_title: str
    source_url: str
    extracted_at: str
    period: str | None = None
    frequency: str | None = None
    units: str | None = None
    figure_type: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)
