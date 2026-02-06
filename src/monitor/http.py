from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class HttpStats:
    fetched: int = 0
    errors: int = 0


class HttpClient:
    def __init__(
        self,
        *,
        concurrency: int,
        timeout_seconds: int,
        max_retries: int,
        min_host_delay_seconds: float,
        user_agent: str,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_retries = max_retries
        self._min_host_delay_seconds = min_host_delay_seconds
        self._user_agent = user_agent
        self._host_locks: Dict[str, asyncio.Lock] = {}
        self.stats = HttpStats()

    async def fetch_text(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        async with self._semaphore:
            return await self._fetch_with_retries(session, url)

    async def _fetch_with_retries(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        for attempt in range(self._max_retries + 1):
            try:
                await self._polite_delay(url)
                async with session.get(url, timeout=self._timeout) as response:
                    if response.status == 429:
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message="rate limited",
                        )
                    response.raise_for_status()
                    text = await response.text()
                    self.stats.fetched += 1
                    return text
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                self.stats.errors += 1
                if attempt >= self._max_retries:
                    logger.warning("Fetch failed for %s after retries: %s", url, exc)
                    return None
                delay = self._backoff_delay(attempt)
                logger.info("Retrying %s in %.2fs (attempt %s)", url, delay, attempt + 1)
                await asyncio.sleep(delay)
        return None

    async def _polite_delay(self, url: str) -> None:
        host = urlparse(url).netloc
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last_time = getattr(lock, "_last_request", 0.0)
            wait = self._min_host_delay_seconds - (now - last_time)
            if wait > 0:
                await asyncio.sleep(wait)
            setattr(lock, "_last_request", time.monotonic())

    def _backoff_delay(self, attempt: int) -> float:
        base = min(2 ** attempt, 30)
        jitter = random.uniform(0.1, 0.6)
        return base + jitter

    def headers(self) -> Dict[str, str]:
        return {"User-Agent": self._user_agent}


def create_session(client: HttpClient) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(headers=client.headers())
