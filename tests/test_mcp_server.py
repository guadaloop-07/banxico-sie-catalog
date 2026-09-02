from __future__ import annotations

import asyncio
import json

from mcp import Client

from banxico_sie_catalog.api import SIEAPIClient
from banxico_sie_catalog.export import write_snapshot
from banxico_sie_catalog.mcp_server import create_server
from banxico_sie_catalog.models import Series


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _snapshot(tmp_path):
    write_snapshot(
        [
            Series(
                id="SF1",
                title="Tipo de cambio FIX",
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
        ],
        tmp_path,
    )
    (tmp_path / "provenance.json").write_text(
        json.dumps({"repository": "example/repository", "workflow_run_id": "123"}), encoding="utf-8"
    )
    return tmp_path / "catalog.sqlite"


def _structured(result):
    return result.structured_content


def test_mcp_tools_expose_a_stable_read_only_catalog_contract(tmp_path) -> None:
    async def scenario() -> None:
        server = create_server(_snapshot(tmp_path))
        async with Client(server) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "search_series",
                "get_series",
                "get_sectors",
                "get_tables",
                "get_latest_observation",
                "get_observations",
            }

            searched = _structured(await client.call_tool("search_series", {"query": "FIX"}))
            assert {record["id"] for record in searched["records"]} == {"SF1", "SF2"}
            assert searched["snapshot"]["manifest"]["schema_version"] == 1
            assert searched["snapshot"]["provenance"]["workflow_run_id"] == "123"

            record = _structured(await client.call_tool("get_series", {"series_id": "SF2"}))
            assert record["record"]["frequency"] == "Mensual"

            sectors = _structured(await client.call_tool("get_sectors", {}))
            assert sectors["sectors"] == [
                {"name": "Tipos de cambio", "table_count": 2, "series_count": 2}
            ]

            tables = _structured(
                await client.call_tool("get_tables", {"sector": "Tipos de cambio"})
            )
            assert [table["table_id"] for table in tables["tables"]] == ["CF1", "CF2"]

    asyncio.run(scenario())


def test_mcp_live_tools_require_catalog_series_and_return_api_provenance(tmp_path) -> None:
    def opener(request, timeout):
        if request.full_url.endswith("/datos/oportuno"):
            payload = {
                "bmx": {
                    "series": [
                        {"titulo": "FIX", "datos": [{"fecha": "26/08/2026", "dato": "18.1234"}]}
                    ]
                }
            }
        else:
            payload = {
                "bmx": {
                    "series": [
                        {"titulo": "FIX", "datos": [{"fecha": "01/08/2026", "dato": "18.0"}]}
                    ]
                }
            }
        return _Response(payload)

    async def scenario() -> None:
        server = create_server(
            _snapshot(tmp_path), api_client=SIEAPIClient(token="secret", opener=opener)
        )
        async with Client(server) as client:
            latest = _structured(
                await client.call_tool("get_latest_observation", {"series_id": "SF1"})
            )
            assert latest["catalog_record"]["title"] == "Tipo de cambio FIX"
            assert latest["live_data"]["observation"] == {"date": "26/08/2026", "value": "18.1234"}
            assert "secret" not in str(latest)

            ranged = _structured(
                await client.call_tool(
                    "get_observations",
                    {"series_id": "SF1", "start_date": "2026-08-01", "end_date": "2026-08-02"},
                )
            )
            assert ranged["live_data"]["observations"] == [{"date": "01/08/2026", "value": "18.0"}]

    asyncio.run(scenario())


def test_mcp_live_tools_return_an_actionable_error_without_a_token(tmp_path) -> None:
    async def scenario() -> None:
        server = create_server(_snapshot(tmp_path), api_client=SIEAPIClient(token=""))
        async with Client(server) as client:
            result = await client.call_tool("get_latest_observation", {"series_id": "SF1"})
            assert not result.is_error
            error = _structured(result)["error"]
            assert error["code"] == "live_data_unavailable"
            assert "BMX_TOKEN is not configured" in error["message"]

    asyncio.run(scenario())
