from __future__ import annotations

import argparse
from pathlib import Path

from .crawler import SIECrawler
from .export import write_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local catalog from Banco de México SIE.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    crawl = subparsers.add_parser("crawl", help="crawl SIE and write a catalog snapshot")
    crawl.add_argument("--output-dir", type=Path, default=Path("data"))
    crawl.add_argument("--delay", type=float, default=1.0, help="seconds between uncached requests")
    crawl.add_argument("--limit-sectors", type=int, help="limit sectors; useful for smoke tests")

    args = parser.parse_args()
    if args.command == "crawl":
        records = SIECrawler(delay_seconds=args.delay).crawl(args.limit_sectors)
        write_snapshot(records, args.output_dir)
        print(f"Wrote {len(records)} series to {args.output_dir}")
