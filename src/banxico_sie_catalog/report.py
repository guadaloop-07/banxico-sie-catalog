"""Machine-readable reports produced by a catalog crawl."""

from __future__ import annotations

import json
from pathlib import Path

from .crawler import CrawlReport


def write_crawl_report(report: CrawlReport, output_dir: Path) -> Path:
    """Write crawl request and parse outcomes beside the generated snapshot."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "crawl-report.json"
    path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path
