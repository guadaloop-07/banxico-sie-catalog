"""Quality gates and change reports for catalog snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .models import Series

REQUIRED_FIELDS = ("id", "title", "sector", "table_id", "table_title", "source_url", "extracted_at")
OPTIONAL_METADATA_FIELDS = ("period", "frequency", "units", "figure_type")
_DIFF_EXCLUDED_FIELDS = {"extracted_at"}


class SnapshotValidationError(Exception):
    """Raised when a catalog snapshot does not pass quality gates."""

    def __init__(self, report: dict[str, object]) -> None:
        super().__init__("Catalog snapshot validation failed.")
        self.report = report


def _error(code: str, message: str, series_id: str | None = None) -> dict[str, str]:
    result = {"code": code, "message": message}
    if series_id is not None:
        result["series_id"] = series_id
    return result


def _warning(series_id: str, fields: list[str]) -> dict[str, object]:
    return {
        "code": "incomplete_metadata",
        "series_id": series_id,
        "missing_fields": fields,
    }


def _parse_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _valid_source_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _changes(
    records: list[Series], previous_records: list[dict[str, object]] | None
) -> dict[str, object]:
    if previous_records is None:
        return {"additions": [], "removals": [], "changed_records": []}

    current = {record.id: asdict(record) for record in records}
    previous = {str(record["id"]): record for record in previous_records}
    changed_records = []
    for series_id in sorted(current.keys() & previous.keys()):
        fields = sorted(
            key
            for key, value in current[series_id].items()
            if key not in _DIFF_EXCLUDED_FIELDS and previous[series_id].get(key) != value
        )
        if fields:
            changed_records.append({"series_id": series_id, "changed_fields": fields})
    return {
        "additions": sorted(current.keys() - previous.keys()),
        "removals": sorted(previous.keys() - current.keys()),
        "changed_records": changed_records,
    }


def validate_snapshot(
    records: list[Series],
    previous_records: list[dict[str, object]] | None = None,
    previous_snapshot: str | None = None,
) -> dict[str, object]:
    """Return a machine-readable report of snapshot errors, warnings, and changes."""
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for record in records:
        data = asdict(record)
        for field in REQUIRED_FIELDS:
            if not isinstance(data[field], str) or not data[field].strip():
                errors.append(_error("required_field", f"{field} is required", record.id))
        if record.id in seen_ids:
            errors.append(_error("duplicate_id", "id must be unique", record.id))
        seen_ids.add(record.id)
        if record.source_url and not _valid_source_url(record.source_url):
            errors.append(_error("source_url", "source_url must be an HTTP(S) URL", record.id))
        if record.extracted_at and not _parse_timestamp(record.extracted_at):
            errors.append(
                _error("extracted_at", "extracted_at must be an ISO 8601 timestamp", record.id)
            )
        missing_metadata = [field for field in OPTIONAL_METADATA_FIELDS if not data[field]]
        if missing_metadata:
            warnings.append(_warning(record.id, missing_metadata))

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "record_count": len(records),
        "previous_snapshot": previous_snapshot,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "changes": _changes(records, previous_records),
    }


def load_snapshot_records(snapshot_path: Path) -> list[dict[str, object]]:
    """Load catalog records from a prior JSON snapshot for change comparison."""
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SnapshotValidationError(
            {"errors": [_error("previous_snapshot", f"could not read {snapshot_path}: {error}")]}
        ) from error
    except json.JSONDecodeError as error:
        raise SnapshotValidationError(
            {"errors": [_error("previous_snapshot", f"invalid JSON in {snapshot_path}: {error}")]}
        ) from error
    if not isinstance(payload, list) or not all(
        isinstance(record, dict) and "id" in record for record in payload
    ):
        raise SnapshotValidationError(
            {"errors": [_error("previous_snapshot", "must be a catalog JSON array with IDs")]}
        )
    return payload


def write_validation_report(report: dict[str, object], output_dir: Path) -> Path:
    """Write a validation report next to a catalog snapshot."""
    path = output_dir / "validation-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
