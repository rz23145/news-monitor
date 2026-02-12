"""
FastAPI backend for news monitor dashboard.
Serves API at /api/* and frontend at /app/. Open http://localhost:8001 (redirects to /app/).

Run from repo root: python3 -m uvicorn web.backend.main:app --reload --port 8001
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _WEB_DIR.parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

REPO_ROOT = _REPO_ROOT
WEB_DIR = _WEB_DIR


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
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db_path() -> str:
    return os.environ.get("NEWS_DB_PATH", str(REPO_ROOT / "news.db"))


def _parse_since(value: str):
    from datetime import datetime, timedelta, timezone
    value = (value or "").strip().lower()
    now = datetime.now(timezone.utc)
    if value.endswith("h") and value[:-1].isdigit():
        return (now - timedelta(hours=int(value[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
    if value.endswith("d") and value[:-1].isdigit():
        return (now - timedelta(days=int(value[:-1]))).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def _row_to_item(row: dict, idx: int) -> NewsItemOut:
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


@app.get("/api/items", response_model=ItemsResponse)
def api_items(
    ticker: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    since: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    sort: str = Query("published_at_desc"),
):
    since_iso = _parse_since(since) if since else None
    tickers = [t for t in (ticker or []) if t]
    sources = [s for s in (source or []) if s]
    desc = sort == "published_at_desc"
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
            i for i in items
            if ql in (i.get("title") or "").lower() or ql in (i.get("summary") or "").lower()
        ]
    items.sort(key=lambda x: x.get("published_at") or "", reverse=desc)
    total = len(items)
    page = items[offset : offset + limit]
    out = [_row_to_item(r, offset + i) for i, r in enumerate(page)]
    return ItemsResponse(items=out, count=total)


@app.get("/api/stats", response_model=StatsResponse)
def api_stats():
    since_24h = _parse_since("24h")
    last_run_iso: str | None = None
    by_ticker: dict[str, int] = {}
    by_source: dict[str, int] = {}
    db_path = _db_path()
    if not Path(db_path).exists():
        return StatsResponse(total_items=0, items_last_24h=0, last_run=None, by_ticker={}, by_source={})
    from monitor.storage import connect, latest_run, totals
    conn = connect(db_path)
    try:
        total_row = totals(conn)
        total_items_val = int(total_row["total_items"]) if total_row else 0
        run = latest_run(conn)
        if run:
            r = dict(run)
            if r.get("finished_at") is not None:
                last_run_iso = str(r["finished_at"])
        items_24h = _query_db(since_24h, None, limit=10000, desc=True, sort="published_at")
        for i in items_24h:
            t = i.get("ticker") or ""
            s = i.get("origin_source") or i.get("source") or ""
            by_ticker[t] = by_ticker.get(t, 0) + 1
            by_source[s] = by_source.get(s, 0) + 1
        return StatsResponse(
            total_items=total_items_val,
            items_last_24h=len(items_24h),
            last_run=last_run_iso,
            by_ticker=by_ticker,
            by_source=by_source,
        )
    finally:
        conn.close()


@app.get("/api/tickers")
def api_tickers():
    db_path = _db_path()
    if not Path(db_path).exists():
        return {"tickers": []}
    from monitor.storage import connect
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT ticker FROM news_items ORDER BY ticker")
        return {"tickers": [r[0] for r in cur.fetchall()]}
    finally:
        conn.close()


@app.get("/api/sources")
def api_sources():
    db_path = _db_path()
    if not Path(db_path).exists():
        return {"sources": []}
    from monitor.storage import connect
    conn = connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT origin_source FROM news_items ORDER BY origin_source")
        return {"sources": [r[0] for r in cur.fetchall()]}
    finally:
        conn.close()


# Frontend: redirect / to /app/ so /api routes are never overridden by static mount
FRONTEND_DIR = WEB_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse(url="/app/", status_code=302)
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
