from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from monitor.config import Config
from monitor.http import HttpClient, create_session
from monitor.sources import build_tasks, parse_feed
from monitor.storage import RunStats, connect, initialize, insert_items, record_run

logger = logging.getLogger(__name__)


async def _fetch_and_parse(
    client: HttpClient,
    session,
    *,
    ticker: str,
    origin_source: str,
    url: str,
    extract_google_target: bool,
) -> Tuple[str, str, List]:
    xml_text = await client.fetch_text(session, url)
    if not xml_text:
        return ticker, origin_source, []
    items = parse_feed(
        xml_text,
        ticker=ticker,
        origin_source=origin_source,
        extract_google_target=extract_google_target,
    )
    return ticker, origin_source, items


async def run_cycle(config: Config, db_path: str) -> Dict[str, int]:
    start_time = time.monotonic()
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats_counter = Counter()
    per_ticker = Counter()
    per_source = Counter()

    client = HttpClient(
        concurrency=config.concurrency,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
        min_host_delay_seconds=config.min_host_delay_seconds,
        user_agent=config.user_agent,
    )

    tasks = list(build_tasks(config))

    async with create_session(client) as session:
        results = await asyncio.gather(
            *[
                _fetch_and_parse(
                    client,
                    session,
                    ticker=ticker,
                    origin_source=origin_source,
                    url=url,
                    extract_google_target=extract_google_target,
                )
                for ticker, origin_source, url, extract_google_target in tasks
            ]
        )

    all_items = []
    for ticker, origin_source, items in results:
        per_ticker[ticker] += len(items)
        per_source[origin_source] += len(items)
        all_items.extend(items)

    conn = connect(db_path)
    initialize(conn)
    insert_stats = insert_items(conn, all_items)
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    duration = time.monotonic() - start_time

    run_stats = RunStats(
        started_at=started_at,
        finished_at=finished_at,
        fetched=client.stats.fetched,
        inserted=insert_stats.inserted,
        duplicates=insert_stats.duplicates,
        errors=client.stats.errors,
        duration_seconds=duration,
    )
    record_run(conn, run_stats)
    conn.close()

    logger.info("Cycle summary: fetched=%s inserted=%s duplicates=%s errors=%s duration=%.2fs", run_stats.fetched, run_stats.inserted, run_stats.duplicates, run_stats.errors, duration)
    logger.info("Per-source counts: %s", dict(per_source))
    logger.info("Per-ticker counts: %s", dict(per_ticker))

    stats_counter.update(
        fetched=run_stats.fetched,
        inserted=run_stats.inserted,
        duplicates=run_stats.duplicates,
        errors=run_stats.errors,
    )
    return dict(stats_counter)
