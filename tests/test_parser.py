from pathlib import Path

from banxico_sie_catalog.crawler import _decode_html
from banxico_sie_catalog.models import Table
from banxico_sie_catalog.parser import parse_sectors, parse_series, parse_tables

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_sectors() -> None:
    sectors = parse_sectors(
        (FIXTURES / "home.html").read_text(), "https://example.test/SieInternet/"
    )
    assert [sector.name for sector in sectors] == [
        "Banco de México",
        "Tasas y precios de referencia",
    ]


def test_parse_tables() -> None:
    tables = parse_tables(
        (FIXTURES / "directory.html").read_text(), "https://example.test/", "Banco de México"
    )
    assert [table.id for table in tables] == ["CF100", "CF101"]


def test_parse_series_with_table_metadata() -> None:
    table = Table("CF100", "Intervención", "Banco de México", "https://example.test/CF100")
    series = parse_series((FIXTURES / "table.html").read_text(), table, "2026-08-10T00:00:00+00:00")
    assert len(series) == 1
    assert series[0].id == "SF99999"
    assert series[0].title == "Saldo cuentas corrientes"
    assert series[0].frequency == "Diaria"
    assert series[0].units == "Millones de Pesos"


def test_parse_series_handles_options_links_and_duplicate_ids() -> None:
    table = Table("CF200", "Alterno", "Otro sector", "https://example.test/CF200")
    series = parse_series(
        (FIXTURES / "table-alternate.html").read_text(), table, "2026-08-10T00:00:00+00:00"
    )
    assert [(record.id, record.title) for record in series] == [
        ("SF123", "Serie por enlace"),
        ("SP456", "Serie por opción"),
    ]
    assert series[1].frequency == "Mensual"


def test_decodes_legacy_sie_bytes() -> None:
    assert _decode_html(b"M\xe9xico") == "México"
