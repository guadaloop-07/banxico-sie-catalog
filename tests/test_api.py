from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from banxico_sie_catalog.api import MAX_SERIES_PER_BATCH, BanxicoAPIError, SIEAPIClient


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_validate_batches_requests_and_keeps_api_results_separate() -> None:
    requests = []
    delays = []

    def opener(request, timeout):
        requests.append(request)
        requested = request.full_url.rsplit("/", 1)[-1].split(",")
        return _Response(
            {"bmx": {"series": [{"idSerie": item, "titulo": item} for item in requested]}}
        )

    ids = [f"SF{index}" for index in range(MAX_SERIES_PER_BATCH + 1)]
    report = SIEAPIClient(
        token="secret", opener=opener, sleep=delays.append, delay_seconds=2
    ).validate(ids)

    assert [request.get_header("Bmx-token") for request in requests] == ["secret", "secret"]
    assert [len(request.full_url.rsplit("/", 1)[-1].split(",")) for request in requests] == [20, 1]
    assert delays == [2]
    assert report["invalid_ids"] == []
    assert len(report["validated_series"]) == len(ids)
    assert "scraped_provenance" not in report


def test_validate_reports_rate_limit_failure() -> None:
    def opener(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    report = SIEAPIClient(token="secret", opener=opener).validate(["SF1"])

    assert report["failures"] == [
        {
            "series_ids": ["SF1"],
            "error": "the API rate limit was reached; increase --delay and retry later",
        }
    ]


def test_validate_requires_environment_or_injected_secret(monkeypatch) -> None:
    monkeypatch.delenv("BMX_TOKEN", raising=False)

    with pytest.raises(BanxicoAPIError, match="BMX_TOKEN is not configured"):
        SIEAPIClient().validate(["SF1"])
