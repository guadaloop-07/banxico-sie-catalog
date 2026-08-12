from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .models import Series
from .validation import (
    SnapshotValidationError,
    load_snapshot_records,
    validate_snapshot,
    write_validation_report,
)


def write_snapshot(
    records: list[Series], output_dir: Path, previous_snapshot: Path | None = None
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        previous_records = load_snapshot_records(previous_snapshot) if previous_snapshot else None
    except SnapshotValidationError as error:
        report = validate_snapshot(records)
        report["valid"] = False
        report["errors"] = error.report["errors"]
        write_validation_report(report, output_dir)
        raise SnapshotValidationError(report) from error
    report = validate_snapshot(
        records, previous_records, str(previous_snapshot) if previous_snapshot else None
    )
    write_validation_report(report, output_dir)
    if not report["valid"]:
        raise SnapshotValidationError(report)

    payload = [asdict(record) for record in records]
    (output_dir / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "record_count": len(payload),
                "schema_version": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    database = sqlite3.connect(output_dir / "catalog.sqlite")
    try:
        database.executescript(
            """
            DROP TABLE IF EXISTS series;
            CREATE TABLE series (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, sector TEXT NOT NULL,
              table_id TEXT NOT NULL, table_title TEXT NOT NULL, source_url TEXT NOT NULL,
              extracted_at TEXT NOT NULL, period TEXT, frequency TEXT, units TEXT,
              figure_type TEXT
            );
            CREATE VIRTUAL TABLE series_search USING fts5(id, title, sector, table_title);
            """
        )
        values = [
            (
                item.id,
                item.title,
                item.sector,
                item.table_id,
                item.table_title,
                item.source_url,
                item.extracted_at,
                item.period,
                item.frequency,
                item.units,
                item.figure_type,
            )
            for item in records
        ]
        database.executemany("INSERT INTO series VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        database.executemany(
            "INSERT INTO series_search VALUES (?, ?, ?, ?)",
            [(item.id, item.title, item.sector, item.table_title) for item in records],
        )
        database.commit()
    finally:
        database.close()
