from __future__ import annotations

import argparse
import json
import logging
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
    rows = export_items(conn, since_iso)
    conn.close()

    if args.format == "json":
        payload = [dict(row) for row in rows]
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        import csv

        writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
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
    run_parser.set_defaults(func=cmd_run)

    export_parser = subparsers.add_parser("export", help="Export items as JSON or CSV")
    export_parser.add_argument("--db", help="SQLite DB path")
    export_parser.add_argument("--format", choices=["json", "csv"], required=True)
    export_parser.add_argument("--since", help="Filter items since duration (24h/7d) or ISO-8601")
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
