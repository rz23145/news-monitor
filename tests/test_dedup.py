from datetime import datetime, timezone

from monitor.models import NewsItem
from monitor.sources import compute_dedup_key
from monitor.storage import connect, initialize, insert_items


def _make_item(title: str) -> NewsItem:
    published_at = datetime(2026, 2, 6, 12, 0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dedup_key = compute_dedup_key(
        url="https://example.com/story",
        title=title,
        source="Example News",
        published_at=published_at,
        guid=None,
    )
    return NewsItem(
        title=title,
        source="Example News",
        published_at=published_at,
        published_at_inferred=False,
        url="https://example.com/story",
        summary=None,
        ticker="TEST",
        origin_source="google_news_rss",
        guid=None,
        dedup_key=dedup_key,
    )


def test_dedup_insert_ignore():
    conn = connect(":memory:")
    initialize(conn)
    item = _make_item("Same title")
    stats = insert_items(conn, [item, item])
    assert stats.inserted == 1
    assert stats.duplicates == 1
    conn.close()
