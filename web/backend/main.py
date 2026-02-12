"""
FastAPI backend for news monitor dashboard.
Reads from SQLite (default) or from out_grouped_by_ticker.json in static mode.

Run: python3 -m uvicorn web.backend.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from repo root without pip install
_WEB_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _WEB_DIR.parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

WEB_DIR = _WEB_DIR
REPO_ROOT = _REPO_ROOT

# --- Pydantic response models ---


class NewsItemOut(BaseModel):
    id: int
    ticker: str
    published_at: str
    source: str
    headline: str
    summary: str | None
    url: str


class ItemsResponse(BaseModel):
    items: list[NewsItemOut]
    count: int


class StatsResponse(BaseModel):
    total_items: int
    items_last_24h: int
    last_run: str | None
    by_ticker: dict[str, int]
    by_source: dict[str, int]


app = FastAPI(title="News Monitor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db_path() -> str:
    return os.environ.get("NEWS_DB_PATH", str(REPO_ROOT / "news.db"))


def _static_mode() -> bool:
    return os.environ.get("NEWS_UI_MODE", "").lower() in ("1", "true", "yes", "static")


def _static_json_path() -> Path:
    p = os.environ.get("NEWS_UI_JSON_PATH", str(REPO_ROOT / "out_grouped_by_ticker.json"))
    return Path(p)


def _load_static_data():
    path = _static_json_path()
    if not path.exists():
        return {"items_by_ticker": {}, "generated_at": None, "since": None, "count": 0}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_since(value: str) -> str | None:
    from datetime import datetime, timedelta, timezone

    value = value.strip().lower()
    now = datetime.now(timezone.utc)
    if value.endswith("h") and value[:-1].isdigit():
        hours = int(value[:-1])
        return (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.endswith("d") and value[:-1].isdigit():
        days = int(value[:-1])
        return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _row_to_news_item_out(row: dict, idx: int) -> NewsItemOut:
    """Build NewsItemOut from DB row or static item dict."""
    return NewsItemOut(
        id=row.get("id") or idx,
        ticker=row.get("ticker") or "",
        published_at=row.get("published_at") or "",
        source=row.get("origin_source") or row.get("source") or "",
        headline=row.get("title") or row.get("headline") or "",
        summary=row.get("summary"),
        url=row.get("url") or "",
    )


def _query_db(since_iso=None, ticker=None, limit=None, desc=True, sort="published_at"):
    from monitor.storage import connect, export_items

    db_path = _db_path()
    if not Path(db_path).exists():
        return []
    conn = connect(db_path)
    try:
        rows = export_items(conn, since_iso, ticker, limit, desc=desc, sort=sort)
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_all_items_static():
    data = _load_static_data()
    items = []
    for ticker, list_items in data.get("items_by_ticker", {}).items():
        for it in list_items:
            it["ticker"] = ticker
            items.append(it)
    return items


@app.get("/api/items", response_model=ItemsResponse)
def api_items(
    ticker: list[str] | None = Query(None, description="Filter by ticker(s)"),
    source: list[str] | None = Query(None, description="Filter by origin_source(s)"),
    since: str | None = Query(None, description="e.g. 24h, 7d"),
    q: str | None = Query(None, description="Search headline/summary"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    sort: str = Query("published_at_desc", description="published_at_desc or published_at_asc"),
):
    """List news items with optional filters. Returns stable shape { items, count }."""
    since_iso = _parse_since(since) if since else None
    tickers = [t for t in (ticker or []) if t]
    sources = [s for s in (source or []) if s]
    if sort not in ("published_at_desc", "published_at_asc"):
        sort = "published_at_desc"
    desc = sort == "published_at_desc"

    if _static_mode():
        items = _get_all_items_static()
        if since_iso:
            items = [i for i in items if (i.get("published_at") or "") >= since_iso]
        if tickers:
            items = [i for i in items if i.get("ticker") in tickers]
        if sources:
            items = [i for i in items if (i.get("origin_source") or i.get("source")) in sources]
        if q:
            ql = q.lower()
            items = [
                i
                for i in items
                if ql in (i.get("title") or "").lower()
                or ql in (i.get("headline") or "").lower()
                or ql in (i.get("summary") or "").lower()
            ]
        items.sort(key=lambda x: x.get("published_at") or "", reverse=desc)
    else:
        fetch_limit = min(5000, offset + limit)
        items = _query_db(
            since_iso,
            tickers[0] if len(tickers) == 1 else None,
            limit=fetch_limit,
            desc=desc,
            sort="published_at",
        )
        if len(tickers) > 1:
            items = [i for i in items if i.get("ticker") in tickers]
        if sources:
            items = [i for i in items if (i.get("origin_source") or i.get("source")) in sources]
        if q:
            ql = q.lower()
            items = [
                i
                for i in items
                if ql in (i.get("title") or "").lower()
                or ql in (i.get("summary") or "").lower()
            ]
        items.sort(key=lambda x: x.get("published_at") or "", reverse=desc)

    total = len(items)
    page = items[offset : offset + limit]
    out = [ _row_to_news_item_out(r, offset + i) for i, r in enumerate(page) ]
    return ItemsResponse(items=out, count=total)


@app.get("/api/stats", response_model=StatsResponse)
def api_stats():
    """Aggregate stats: total_items, items_last_24h, last_run (ISO), by_ticker, by_source."""
    since_24h = _parse_since("24h")
    last_run_iso: str | None = None
    by_ticker: dict[str, int] = {}
    by_source: dict[str, int] = {}

    if _static_mode():
        data = _load_static_data()
        items = _get_all_items_static()
        for i in items:
            t = i.get("ticker") or ""
            s = i.get("origin_source") or i.get("source") or ""
            by_ticker[t] = by_ticker.get(t, 0) + 1
            by_source[s] = by_source.get(s, 0) + 1
        count_24h = (
            sum(1 for i in items if (i.get("published_at") or "") >= since_24h)
            if since_24h
            else 0
        )
        if data.get("generated_at"):
            last_run_iso = data["generated_at"]
        return StatsResponse(
            total_items=len(items),
            items_last_24h=count_24h,
            last_run=last_run_iso,
            by_ticker=by_ticker,
            by_source=by_source,
        )

    from monitor.storage import connect, latest_run, totals

    db_path = _db_path()
    if not Path(db_path).exists():
        return StatsResponse(
            total_items=0,
            items_last_24h=0,
            last_run=None,
            by_ticker={},
            by_source={},
        )
    conn = connect(db_path)
    try:
        total_row = totals(conn)
        run = latest_run(conn)
        if run and run.get("finished_at"):
            last_run_iso = str(run["finished_at"])
        items_24h = _query_db(since_24h, None, limit=10000, desc=True, sort="published_at")
        for i in items_24h:
            t = i.get("ticker") or ""
            s = i.get("origin_source") or i.get("source") or ""
            by_ticker[t] = by_ticker.get(t, 0) + 1
            by_source[s] = by_source.get(s, 0) + 1
        return StatsResponse(
            total_items=total_row["total_items"],
            items_last_24h=len(items_24h),
            last_run=last_run_iso,
            by_ticker=by_ticker,
            by_source=by_source,
        )
    finally:
        conn.close()


@app.get("/api/tickers")
def api_tickers():
    """List distinct tickers."""
    if _static_mode():
        data = _load_static_data()
        tickers = list(data.get("items_by_ticker", {}).keys())
        return {"tickers": sorted(tickers)}
    from monitor.storage import connect

    db_path = _db_path()
    if not Path(db_path).exists():
        return {"tickers": []}
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT ticker FROM news_items ORDER BY ticker")
        return {"tickers": [r[0] for r in cur.fetchall()]}
    finally:
        conn.close()


@app.get("/api/sources")
def api_sources():
    """List distinct sources (origin_source)."""
    if _static_mode():
        items = _get_all_items_static()
        sources = sorted(set(i.get("origin_source") or i.get("source") or "" for i in items))
        return {"sources": [s for s in sources if s]}
    from monitor.storage import connect

    db_path = _db_path()
    if not Path(db_path).exists():
        return {"sources": []}
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT origin_source FROM news_items ORDER BY origin_source")
        return {"sources": [r[0] for r in cur.fetchall()]}
    finally:
        conn.close()


# Serve frontend
FRONTEND_DIR = WEB_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
