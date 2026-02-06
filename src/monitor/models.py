from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published_at: str
    published_at_inferred: bool
    url: str
    summary: Optional[str]
    ticker: str
    origin_source: str
    guid: Optional[str]
    dedup_key: str
