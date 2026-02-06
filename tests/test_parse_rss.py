from pathlib import Path

from monitor.sources import parse_feed


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_yahoo_feed():
    xml = (FIXTURES / "yahoo_sample.xml").read_text(encoding="utf-8")
    items = parse_feed(xml, ticker="AAPL", origin_source="yahoo_rss", extract_google_target=False)
    assert len(items) == 1
    item = items[0]
    assert item.ticker == "AAPL"
    assert item.origin_source == "yahoo_rss"
    assert item.source == "yahoo_rss"
    assert item.published_at.endswith("Z")
    assert item.published_at_inferred is False
    assert "apple-earnings" in (item.guid or "")


def test_parse_google_feed_extracts_target():
    xml = (FIXTURES / "gnews_sample.xml").read_text(encoding="utf-8")
    items = parse_feed(xml, ticker="TSLA", origin_source="google_news_rss", extract_google_target=True)
    assert len(items) == 1
    item = items[0]
    assert item.ticker == "TSLA"
    assert item.origin_source == "google_news_rss"
    assert item.source == "Example News"
    assert item.url == "https://example.com/tesla-shares-rise"
