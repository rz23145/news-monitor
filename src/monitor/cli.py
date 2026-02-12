from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from monitor.config import env_db_path, load_config
from monitor.runner import run_cycle
from monitor.storage import connect, export_items, latest_run, totals


def setup_logging(log_file: Optional[str]) -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )


def auto_export_after_run(db_path: str) -> None:
    """Generate out.csv, out.json, out_grouped_by_ticker.json (last 24h) in cwd."""
    since_iso = parse_since("24h")
    conn = connect(db_path)
    try:
        rows_flat = export_items(
            conn, since_iso, None, None, desc=True, sort="ticker,published_desc"
        )
        items = [dict(r) for r in rows_flat]

        cwd = os.getcwd()
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # out.csv — improved columns, sort ticker ASC, published_at DESC
        csv_path = os.path.join(cwd, "out.csv")
        _write_auto_csv(csv_path, rows_flat)

        # out.json — flat list
        json_path = os.path.join(cwd, "out.json")
        payload = {
            "generated_at": generated_at,
            "since": "24h",
            "count": len(items),
            "items": items,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")

        # out_grouped_by_ticker.json
        grouped_path = os.path.join(cwd, "out_grouped_by_ticker.json")
        items_by_ticker = {}
        for item in items:
            items_by_ticker.setdefault(item["ticker"], []).append(item)
        grouped_payload = {
            "generated_at": generated_at,
            "since": "24h",
            "count": len(items),
            "items_by_ticker": items_by_ticker,
        }
        with open(grouped_path, "w", encoding="utf-8") as f:
            json.dump(grouped_payload, f, indent=2)
            f.write("\n")

        logging.info("Auto-exported to %s: out.csv, out.json, out_grouped_by_ticker.json", cwd)
    finally:
        conn.close()


def _write_auto_csv(path: str, rows: list) -> None:
    """Write CSV with columns: ticker, published_at, source, headline, url, summary, first_seen_at."""
    import csv

    fieldnames = [
        "ticker",
        "published_at",
        "source",
        "headline",
        "url",
        "summary",
        "first_seen_at",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            r = dict(row)
            writer.writerow({
                "ticker": r.get("ticker"),
                "published_at": r.get("published_at"),
                "source": r.get("source"),
                "headline": r.get("title"),
                "url": r.get("url"),
                "summary": r.get("summary") or "",
                "first_seen_at": r.get("first_seen_at"),
            })


def parse_since(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip().lower()
    now = datetime.now(timezone.utc)
    if value.endswith("h") and value[:-1].isdigit():
        hours = int(value[:-1])
        return (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.endswith("d") and value[:-1].isdigit():
        days = int(value[:-1])
        return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid --since value. Use 24h, 7d, or ISO-8601.") from None


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    db_path = args.db or env_db_path("news.db")

    if not config.tickers:
        logging.error("No tickers configured. Update config.json.")
        return 2

    while True:
        logging.info("Starting fetch cycle")
        stats = run_cycle_sync(config, db_path)
        logging.info("Cycle complete: %s", stats)
            if not args.no_auto_export:
            auto_export_after_run(db_path)
        if not args.loop:
            break
        time.sleep(args.interval or config.interval_seconds)
    return 0


def run_cycle_sync(config, db_path: str) -> dict:
    return asyncio_run(run_cycle(config, db_path))


def asyncio_run(coro):
    try:
        import asyncio

        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)


def cmd_export(args: argparse.Namespace) -> int:
    db_path = args.db or env_db_path("news.db")
    conn = connect(db_path)
    since_iso = parse_since(args.since)
    sort = getattr(args, "sort", "published_at") or "published_at"
    if sort not in ("published_at", "ticker,published_desc"):
        raise argparse.ArgumentTypeError(
            "Only --sort published_at or --sort ticker,published_desc is supported."
        )
    if args.group_by and args.format != "json":
        raise argparse.ArgumentTypeError("--group-by is only supported for JSON output.")

    rows = export_items(
        conn, since_iso, args.ticker, args.limit, desc=args.desc, sort=sort
    )
    conn.close()

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.format == "json":
            generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            items = [dict(row) for row in rows]
            if args.group_by == "ticker":
                items_by_ticker = {}
                for item in items:
                    items_by_ticker.setdefault(item["ticker"], []).append(item)
                payload = {
                    "generated_at": generated_at,
                    "since": args.since,
                    "count": len(items),
                    "items_by_ticker": items_by_ticker,
                }
            else:
                payload = {
                    "generated_at": generated_at,
                    "since": args.since,
                    "count": len(items),
                    "items": items,
                }
            json.dump(payload, out, indent=2)
            out.write("\n")
        else:
            import csv

            use_improved_csv = sort == "ticker,published_desc"
            if use_improved_csv:
                fieldnames = [
                    "ticker",
                    "published_at",
                    "source",
                    "headline",
                    "url",
                    "summary",
                    "first_seen_at",
                ]
                if not args.include_summary:
                    fieldnames.remove("summary")
            else:
                fieldnames = [
                    "ticker",
                    "published_at",
                    "source",
                    "publisher",
                    "title",
                    "url",
                    "summary",
                    "dedup_key",
                    "fetched_at",
                ]
                if not args.include_summary:
                    fieldnames.remove("summary")
            writer = csv.DictWriter(
                out,
                fieldnames=fieldnames,
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                record = dict(row)
                if use_improved_csv:
                    output = {
                        "ticker": record.get("ticker"),
                        "published_at": record.get("published_at"),
                        "source": record.get("source"),
                        "headline": record.get("title"),
                        "url": record.get("url"),
                        "summary": record.get("summary", "") if args.include_summary else "",
                        "first_seen_at": record.get("first_seen_at"),
                    }
                    if not args.include_summary:
                        output.pop("summary", None)
                else:
                    output = {
                        "ticker": record.get("ticker"),
                        "published_at": record.get("published_at"),
                        "source": record.get("source"),
                        "publisher": record.get("source"),
                        "title": record.get("title"),
                        "url": record.get("url"),
                        "summary": record.get("summary"),
                        "dedup_key": record.get("dedup_key"),
                        "fetched_at": record.get("first_seen_at"),
                    }
                    if not args.include_summary:
                        output.pop("summary", None)
                writer.writerow(output)
    finally:
        if args.output:
            out.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db_path = args.db or env_db_path("news.db")
    conn = connect(db_path)
    run = latest_run(conn)
    total = totals(conn)
    conn.close()

    if run:
        logging.info(
            "Last run: started_at=%s finished_at=%s fetched=%s inserted=%s duplicates=%s errors=%s duration=%.2fs",
            run["started_at"],
            run["finished_at"],
            run["fetched"],
            run["inserted"],
            run["duplicates"],
            run["errors"],
            run["duration_seconds"],
        )
    else:
        logging.info("No runs recorded yet.")

    logging.info(
        "Totals: items=%s tickers=%s sources=%s",
        total["total_items"],
        total["total_tickers"],
        total["total_sources"],
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Real-Time Financial News Monitoring System",
    )
    parser.add_argument("--log-file", dest="log_file", help="Optional log file path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Fetch RSS feeds once or in a loop")
    run_parser.add_argument("--config", required=True, help="Path to config.json")
    run_parser.add_argument("--db", help="SQLite DB path")
    run_parser.add_argument("--loop", action="store_true", help="Run forever with sleep interval")
    run_parser.add_argument("--interval", type=int, help="Override sleep interval (seconds)")
    run_parser.add_argument(
        "--no-auto-export",
        action="store_true",
        help="Skip auto-generating out.csv, out.json, out_grouped_by_ticker.json after run",
    )
    run_parser.set_defaults(func=cmd_run)

    export_parser = subparsers.add_parser("export", help="Export items as JSON or CSV")
    export_parser.add_argument("--db", help="SQLite DB path")
    export_parser.add_argument("--format", choices=["json", "csv"], required=True)
    export_parser.add_argument("--since", help="Filter items since duration (24h/7d) or ISO-8601")
    export_parser.add_argument("--ticker", help="Filter by ticker (e.g., AAPL)")
    export_parser.add_argument("--group-by", choices=["ticker"], help="Group JSON output by ticker")
    export_parser.add_argument(
        "--sort",
        default="published_at",
        help="Sort: published_at (default) or ticker,published_desc",
    )
    export_sort = export_parser.add_mutually_exclusive_group()
    export_sort.add_argument("--desc", action="store_true", help="Sort descending (default)")
    export_sort.add_argument("--asc", dest="desc", action="store_false", help="Sort ascending")
    export_parser.set_defaults(desc=True)
    export_parser.add_argument("--limit", type=int, help="Limit number of items")
    export_parser.add_argument(
        "--include-summary",
        action="store_true",
        help="Include summary column in CSV output",
    )
    export_parser.add_argument("-o", "--output", help="Write output to file (default: stdout)")
    export_parser.set_defaults(func=cmd_export)

    stats_parser = subparsers.add_parser("stats", help="Show latest run stats and totals")
    stats_parser.add_argument("--db", help="SQLite DB path")
    stats_parser.set_defaults(func=cmd_stats)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_file)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
