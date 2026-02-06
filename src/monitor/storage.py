from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from monitor.models import NewsItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    published_at_inferred INTEGER NOT NULL,
    url TEXT NOT NULL,
    summary TEXT,
    ticker TEXT NOT NULL,
    origin_source TEXT NOT NULL,
    guid TEXT,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    fetched INTEGER NOT NULL,
    inserted INTEGER NOT NULL,
    duplicates INTEGER NOT NULL,
    errors INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_items_ticker ON news_items (ticker);
CREATE INDEX IF NOT EXISTS idx_news_items_origin ON news_items (origin_source);
CREATE INDEX IF NOT EXISTS idx_news_items_published ON news_items (published_at);
CREATE INDEX IF NOT EXISTS idx_news_items_first_seen ON news_items (first_seen_at);
"""


@dataclass
class InsertStats:
    inserted: int = 0
    duplicates: int = 0


@dataclass
class RunStats:
    started_at: str
    finished_at: str
    fetched: int
    inserted: int
    duplicates: int
    errors: int
    duration_seconds: float


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_items(conn: sqlite3.Connection, items: Iterable[NewsItem]) -> InsertStats:
    stats = InsertStats()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for item in items:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO news_items (
                dedup_key, title, source, published_at, published_at_inferred,
                url, summary, ticker, origin_source, guid, first_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.dedup_key,
                item.title,
                item.source,
                item.published_at,
                1 if item.published_at_inferred else 0,
                item.url,
                item.summary,
                item.ticker,
                item.origin_source,
                item.guid,
                now_iso,
            ),
        )
        if cursor.rowcount == 1:
            stats.inserted += 1
        else:
            stats.duplicates += 1
    conn.commit()
    return stats


def record_run(conn: sqlite3.Connection, stats: RunStats) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            started_at, finished_at, fetched, inserted, duplicates, errors, duration_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stats.started_at,
            stats.finished_at,
            stats.fetched,
            stats.inserted,
            stats.duplicates,
            stats.errors,
            stats.duration_seconds,
        ),
    )
    conn.commit()


def export_items(conn: sqlite3.Connection, since_iso: Optional[str]) -> List[sqlite3.Row]:
    if since_iso:
        cursor = conn.execute(
            "SELECT * FROM news_items WHERE published_at >= ? ORDER BY published_at DESC",
            (since_iso,),
        )
    else:
        cursor = conn.execute("SELECT * FROM news_items ORDER BY published_at DESC")
    return list(cursor.fetchall())


def latest_run(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    cursor = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    return cursor.fetchone()


def totals(conn: sqlite3.Connection) -> sqlite3.Row:
    cursor = conn.execute(
        """
        SELECT COUNT(*) AS total_items,
               COUNT(DISTINCT ticker) AS total_tickers,
               COUNT(DISTINCT origin_source) AS total_sources
        FROM news_items
        """
    )
    return cursor.fetchone()
