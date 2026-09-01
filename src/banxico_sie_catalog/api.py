"""Optional validation and enrichment through the Banco de México SIE API."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"
MAX_SERIES_PER_BATCH = 20


class BanxicoAPIError(Exception):
    """Raised when the SIE API cannot validate a requested series batch."""


@dataclass(frozen=True)
class BatchFailure:
    series_ids: list[str]
    error: str

    def as_dict(self) -> dict[str, object]:
        return {"series_ids": self.series_ids, "error": self.error}


def _batches(series_ids: Iterable[str]) -> list[list[str]]:
    ids = list(dict.fromkeys(series_ids))
    return [
        ids[index : index + MAX_SERIES_PER_BATCH]
        for index in range(0, len(ids), MAX_SERIES_PER_BATCH)
    ]


class SIEAPIClient:
    """Read SIE metadata and observations without exposing the API token."""

    def __init__(
        self,
        token: str | None = None,
        *,
        opener: Callable[..., object] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        delay_seconds: float = 1.0,
    ) -> None:
        self.token = token if token is not None else os.environ.get("BMX_TOKEN")
        self.opener = opener
        self.sleep = sleep
        self.delay_seconds = delay_seconds

    def validate(self, series_ids: Iterable[str]) -> dict[str, object]:
        """Validate known IDs in API batches and return API-only provenance."""
        if not self.token:
            raise BanxicoAPIError(
                "BMX_TOKEN is not configured; set it in the environment or inject a secret."
            )
        batches = _batches(series_ids)
        report: dict[str, object] = {
            "validated_at": datetime.now(UTC).isoformat(),
            "api_base_url": API_BASE_URL,
            "requested_ids": [series_id for batch in batches for series_id in batch],
            "validated_series": [],
            "invalid_ids": [],
            "failures": [],
        }
        for index, batch in enumerate(batches):
            try:
                series = self._fetch_batch(batch)
            except BanxicoAPIError as error:
                report["failures"].append(BatchFailure(batch, str(error)).as_dict())
                continue
            found_ids = {str(item.get("idSerie")) for item in series if item.get("idSerie")}
            report["validated_series"].extend(series)
            report["invalid_ids"].extend(
                series_id for series_id in batch if series_id not in found_ids
            )
            if index < len(batches) - 1 and self.delay_seconds:
                self.sleep(self.delay_seconds)
        return report

    def latest_observation(self, series_id: str) -> dict[str, object]:
        """Return the latest published observation for one SIE series."""
        if not self.token:
            raise BanxicoAPIError("BMX_TOKEN is not configured; set it in the environment.")
        series = self._fetch_batch([f"{series_id}/datos/oportuno"])
        if len(series) != 1:
            raise BanxicoAPIError(f"API response contained invalid data for series {series_id}")
        observations = _observations(series[0], series_id)
        if not observations:
            raise BanxicoAPIError(f"SIE returned no latest observation for series {series_id}")
        return {
            "queried_at": datetime.now(UTC).isoformat(),
            "series_id": series_id,
            "api_title": series[0].get("titulo"),
            "observation": observations[0],
        }

    def observations(self, series_id: str, start_date: str, end_date: str) -> dict[str, object]:
        """Return SIE observations for an inclusive ISO 8601 date range."""
        if not self.token:
            raise BanxicoAPIError("BMX_TOKEN is not configured; set it in the environment.")
        start = _iso_date(start_date, "start_date")
        end = _iso_date(end_date, "end_date")
        if end < start:
            raise BanxicoAPIError("end_date must be on or after start_date")
        series = self._fetch_batch([f"{series_id}/datos/{start}/{end}"])
        if len(series) != 1:
            raise BanxicoAPIError(f"API response contained invalid data for series {series_id}")
        return {
            "queried_at": datetime.now(UTC).isoformat(),
            "series_id": series_id,
            "api_title": series[0].get("titulo"),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "observations": _observations(series[0], series_id),
        }

    def _fetch_batch(self, series_ids: list[str]) -> list[dict[str, object]]:
        request = Request(
            f"{API_BASE_URL}/{','.join(series_ids)}",
            headers={"Bmx-Token": self.token or "", "Accept": "application/json"},
        )
        try:
            with self.opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            messages = {
                401: "authentication failed; verify BMX_TOKEN",
                403: "access was denied; verify BMX_TOKEN permissions",
                404: "the requested API resource is unavailable",
                429: "the API rate limit was reached; increase --delay and retry later",
            }
            raise BanxicoAPIError(
                messages.get(error.code, f"API request failed with HTTP {error.code}")
            ) from error
        except URLError as error:
            raise BanxicoAPIError(f"API is unavailable; retry later ({error.reason})") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BanxicoAPIError(f"API returned an invalid response: {error}") from error
        try:
            series = payload["bmx"]["series"]
        except (KeyError, TypeError) as error:
            raise BanxicoAPIError("API response did not contain series metadata") from error
        if not isinstance(series, list) or not all(isinstance(item, dict) for item in series):
            raise BanxicoAPIError("API response contained invalid series metadata")
        return series


def _iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise BanxicoAPIError(f"{field_name} must use ISO 8601 format YYYY-MM-DD") from error


def _observations(series: dict[str, object], series_id: str) -> list[dict[str, object]]:
    observations = series.get("datos")
    if not isinstance(observations, list) or not all(
        isinstance(item, dict) for item in observations
    ):
        raise BanxicoAPIError(f"API response did not contain observations for series {series_id}")
    return [{"date": item.get("fecha"), "value": item.get("dato")} for item in observations]
