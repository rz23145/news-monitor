from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class GoogleNewsConfig:
    hl: str = "en-US"
    gl: str = "US"
    ceid: str = "US:en"


@dataclass(frozen=True)
class Config:
    tickers: List[str]
    company_names: Dict[str, str]
    concurrency: int = 5
    interval_seconds: int = 900
    user_agent: str = "NewsMonitorBot/1.0 (+https://example.com)"
    timeout_seconds: int = 15
    max_retries: int = 3
    min_host_delay_seconds: float = 1.0
    google_news: GoogleNewsConfig = GoogleNewsConfig()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    tickers = [str(t).strip().upper() for t in raw.get("tickers", [])]
    tickers = [t for t in tickers if t]
    company_names = {k.upper(): str(v) for k, v in raw.get("company_names", {}).items()}

    google_news_raw = raw.get("google_news", {})
    google_news = GoogleNewsConfig(
        hl=str(google_news_raw.get("hl", "en-US")),
        gl=str(google_news_raw.get("gl", "US")),
        ceid=str(google_news_raw.get("ceid", "US:en")),
    )

    config = Config(
        tickers=tickers,
        company_names=company_names,
        concurrency=int(raw.get("concurrency", 5)),
        interval_seconds=int(raw.get("interval_seconds", 900)),
        user_agent=str(raw.get("user_agent", "NewsMonitorBot/1.0 (+https://example.com)")),
        timeout_seconds=int(raw.get("timeout_seconds", 15)),
        max_retries=int(raw.get("max_retries", 3)),
        min_host_delay_seconds=float(raw.get("min_host_delay_seconds", 1.0)),
        google_news=google_news,
    )

    return apply_env_overrides(config)


def apply_env_overrides(config: Config) -> Config:
    google_news = GoogleNewsConfig(
        hl=_env_str("NEWS_GNEWS_HL", config.google_news.hl),
        gl=_env_str("NEWS_GNEWS_GL", config.google_news.gl),
        ceid=_env_str("NEWS_GNEWS_CEID", config.google_news.ceid),
    )
    return Config(
        tickers=config.tickers,
        company_names=config.company_names,
        concurrency=_env_int("NEWS_CONCURRENCY", config.concurrency),
        interval_seconds=_env_int("NEWS_INTERVAL_SECONDS", config.interval_seconds),
        user_agent=_env_str("NEWS_USER_AGENT", config.user_agent),
        timeout_seconds=_env_int("NEWS_TIMEOUT_SECONDS", config.timeout_seconds),
        max_retries=_env_int("NEWS_MAX_RETRIES", config.max_retries),
        min_host_delay_seconds=_env_float("NEWS_MIN_HOST_DELAY_SECONDS", config.min_host_delay_seconds),
        google_news=google_news,
    )


def env_db_path(default: Optional[str] = None) -> Optional[str]:
    value = os.getenv("NEWS_DB_PATH")
    if value:
        return value
    return default
