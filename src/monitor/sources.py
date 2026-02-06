from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, quote_plus, urlparse, urlunparse

import feedparser
from dateutil import parser as date_parser

from monitor.config import Config
from monitor.models import NewsItem

logger = logging.getLogger(__name__)


YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
GNEWS_RSS = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"


def build_yahoo_url(ticker: str) -> str:
    return YAHOO_RSS.format(ticker=quote_plus(ticker))


def build_google_news_url(ticker: str, company_name: Optional[str], config: Config) -> str:
    if company_name:
        query = f"{ticker} {company_name} stock"
    else:
        query = f"{ticker} stock OR {ticker} shares"
    return GNEWS_RSS.format(
        query=quote_plus(query),
        hl=quote_plus(config.google_news.hl),
        gl=quote_plus(config.google_news.gl),
        ceid=quote_plus(config.google_news.ceid),
    )


def parse_feed(
    xml_text: str,
    *,
    ticker: str,
    origin_source: str,
    extract_google_target: bool = False,
) -> List[NewsItem]:
    parsed = feedparser.parse(xml_text)
    items: List[NewsItem] = []
    for entry in parsed.entries:
        try:
            item = _parse_entry(
                entry,
                ticker=ticker,
                origin_source=origin_source,
                extract_google_target=extract_google_target,
            )
            items.append(item)
        except Exception as exc:  # pragma: no cover - defensive, logs only
            logger.warning("Failed to parse entry for %s: %s", ticker, exc)
    return items


def _parse_entry(
    entry: dict,
    *,
    ticker: str,
    origin_source: str,
    extract_google_target: bool,
) -> NewsItem:
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    guid = (entry.get("id") or entry.get("guid") or None)
    summary = (entry.get("summary") or entry.get("description") or None)
    source = _extract_source(entry, origin_source)

    if extract_google_target:
        link = extract_google_news_target(link) or link

    published_at, inferred = _parse_published(entry)
    published_at_iso = published_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    dedup_key = compute_dedup_key(
        url=link,
        title=title,
        source=source,
        published_at=published_at_iso,
        guid=guid,
    )

    return NewsItem(
        title=title or "(untitled)",
        source=source,
        published_at=published_at_iso,
        published_at_inferred=inferred,
        url=link,
        summary=summary,
        ticker=ticker,
        origin_source=origin_source,
        guid=guid,
        dedup_key=dedup_key,
    )


def _extract_source(entry: dict, origin_source: str) -> str:
    if "source" in entry and isinstance(entry["source"], dict):
        return str(entry["source"].get("title") or origin_source)
    if "publisher" in entry:
        return str(entry.get("publisher"))
    return origin_source


def _parse_published(entry: dict) -> tuple[datetime, bool]:
    published = entry.get("published") or entry.get("updated") or entry.get("pubDate")
    if published:
        try:
            dt = date_parser.parse(published)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, False
        except Exception:
            pass
    return datetime.now(timezone.utc), True


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="")
    normalized = urlunparse(cleaned)
    if normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def compute_dedup_key(*, url: str, title: str, source: str, published_at: str, guid: Optional[str]) -> str:
    normalized_url = normalize_url(url)
    date_bucket = published_at.split("T", 1)[0] if published_at else "unknown"
    payload = "|".join(
        [
            guid or "",
            normalized_url,
            title.lower(),
            source.lower(),
            date_bucket,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_google_news_target(url: str) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc != "news.google.com":
        return None
    query = parse_qs(parsed.query or "")
    target = query.get("url", [None])[0]
    if not target:
        return None
    target_parsed = urlparse(target)
    if target_parsed.scheme in {"http", "https"}:
        return target
    return None


def build_tasks(config: Config) -> Iterable[tuple[str, str, str, bool]]:
    for ticker in config.tickers:
        yahoo_url = build_yahoo_url(ticker)
        yield ticker, "yahoo_rss", yahoo_url, False
        company_name = config.company_names.get(ticker)
        gnews_url = build_google_news_url(ticker, company_name, config)
        yield ticker, "google_news_rss", gnews_url, True
