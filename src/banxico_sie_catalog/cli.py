from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .catalog import CatalogError, search, show
from .crawler import CrawlError, SIECrawler
from .export import write_snapshot
from .report import write_crawl_report
from .validation import SnapshotValidationError


def _positive_integer(value: str) -> int:
    integer = int(value)
    if integer < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return integer


def _non_negative_integer(value: str) -> int:
    integer = int(value)
    if integer < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return integer


def _print_records(records: list[dict[str, str | None]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return
    for record in records:
        print(f"{record['id']}\t{record['title']}\t{record['sector']}\t{record['table_id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local catalog from Banco de México SIE.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    crawl = subparsers.add_parser("crawl", help="crawl SIE and write a catalog snapshot")
    crawl.add_argument("--output-dir", type=Path, default=Path("data"))
    crawl.add_argument("--delay", type=float, default=1.0, help="seconds between uncached requests")
    crawl.add_argument("--limit-sectors", type=int, help="limit sectors; useful for smoke tests")
    crawl.add_argument(
        "--retries", type=_non_negative_integer, default=2, help="retries per failed request"
    )
    crawl.add_argument(
        "--previous-snapshot",
        type=Path,
        help="catalog JSON snapshot used to report additions, removals, and metadata changes",
    )
    crawl.add_argument(
        "--require-complete",
        action="store_true",
        help="fail without writing a snapshot if any sector or table URL could not be fetched",
    )

    search_parser = subparsers.add_parser("search", help="search a local catalog snapshot")
    search_parser.add_argument("query", help="free-text FTS query")
    search_parser.add_argument("--database", type=Path, default=Path("data/catalog.sqlite"))
    search_parser.add_argument("--limit", type=_positive_integer, default=20)
    search_parser.add_argument("--sector")
    search_parser.add_argument("--table", dest="table_id")
    search_parser.add_argument("--frequency")
    search_parser.add_argument("--series-id")
    search_parser.add_argument("--json", action="store_true", dest="as_json")

    show_parser = subparsers.add_parser("show", help="show one catalog record by SIE series ID")
    show_parser.add_argument("series_id")
    show_parser.add_argument("--database", type=Path, default=Path("data/catalog.sqlite"))
    show_parser.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args()
    if args.command == "crawl":
        crawler = SIECrawler(delay_seconds=args.delay, max_retries=args.retries)
        try:
            records, report = crawler.crawl_with_report(args.limit_sectors)
        except CrawlError as error:
            crawler.report.failed_urls.append(error.failure)
            crawler.report.finished_at = crawler.report.finished_at or datetime.now(UTC).isoformat()
            write_crawl_report(crawler.report, args.output_dir)
            print(error)
            return 2
        write_crawl_report(report, args.output_dir)
        if args.require_complete and report.failed_urls:
            print("Crawl did not complete; see crawl-report.json for failed URLs.")
            return 2
        try:
            write_snapshot(records, args.output_dir, args.previous_snapshot)
        except SnapshotValidationError as error:
            print(error)
            return 2
        print(
            f"Wrote {len(records)} series to {args.output_dir} "
            f"({len(report.failed_urls)} failed URLs)"
        )
        return 0
    try:
        if args.command == "search":
            records = search(
                args.database,
                args.query,
                limit=args.limit,
                sector=args.sector,
                table_id=args.table_id,
                frequency=args.frequency,
                series_id=args.series_id,
            )
            if not records:
                print("No catalog records matched the query.")
                return 1
            _print_records(records, args.as_json)
            return 0

        record = show(args.database, args.series_id)
        if record is None:
            print(f"No catalog record found for series ID: {args.series_id}")
            return 1
        if args.as_json:
            print(json.dumps(record, ensure_ascii=False, indent=2))
        else:
            for field, value in record.items():
                print(f"{field}: {value}")
        return 0
    except CatalogError as error:
        print(error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
