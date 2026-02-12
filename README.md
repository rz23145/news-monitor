# News Monitor

Financial news monitor: fetch from Yahoo Finance & Google News RSS, store in SQLite, view in a web dashboard or export CSV/JSON.

---

## Copy-paste: first-time setup

Run these in order from the project folder.

```bash
cd /path/to/news-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp config.example.json config.json
```

**What that did:** Created a virtualenv, installed dependencies and the `monitor` CLI, and copied a config file you can edit (tickers, etc.).

---

## Copy-paste: fetch news once

```bash
python3 -m monitor.cli run --config config.json --db news.db
```

**Terminal output you’ll see:** Log lines, then a summary like:
- `Cycle summary: fetched=20 inserted=21 duplicates=1180 errors=0 duration=9.50s`
- `Per-source counts: {'yahoo_rss': 200, 'google_news_rss': 1001}`
- `Per-ticker counts: {'AAPL': 120, 'MSFT': 121, ...}`
- `Auto-exported to /path: out.csv, out.json, out_grouped_by_ticker.json`

**Files created in the project folder:**

| File | What it is |
|------|------------|
| `news.db` | SQLite database of all articles (used by the dashboard and export). |
| `out.csv` | Last 24h of articles in CSV (ticker, published_at, source, headline, url, summary, first_seen_at). |
| `out.json` | Last 24h of articles as a flat JSON array. |
| `out_grouped_by_ticker.json` | Last 24h grouped by ticker: `{"items_by_ticker": {"AAPL": [...], "MSFT": [...]}}`. |

---

## Copy-paste: run the web dashboard

```bash
source .venv/bin/activate
python3 -m uvicorn web.backend.main:app --reload --port 8001
```

If you see **Address already in use**:

```bash
lsof -ti :8001 | xargs kill -9
```

Then run the uvicorn command again.

**Open in browser:** **http://localhost:8001** (redirects to the app at `/app/`).

**What the dashboard does:** Shows total items, items in last 24h, and last run time. Dropdowns let you pick **Ticker** (e.g. AAPL) and **Source** (e.g. yahoo_rss). Choose time range, optional search, click **Apply** to see the table of articles. Data auto-refreshes every 15 minutes.

---

## Other useful commands (copy-paste)

**Fetch news every 15 minutes (leave running):**
```bash
python3 -m monitor.cli run --config config.json --db news.db --loop
```

**Different interval (e.g. 5 minutes):**
```bash
python3 -m monitor.cli run --config config.json --db news.db --loop --interval 300
```

**Print stats (total items, last run, etc.):**
```bash
python3 -m monitor.cli stats --db news.db
```
*Output:* One line with total items, tickers, sources, last run time.

**Export last 24h to JSON:**
```bash
python3 -m monitor.cli export --db news.db --format json --since 24h > my_export.json
```

**Export last 24h to CSV (one ticker):**
```bash
python3 -m monitor.cli export --db news.db --format csv --since 24h --ticker AAPL > aapl.csv
```

**Skip auto-export on run:**
```bash
python3 -m monitor.cli run --config config.json --db news.db --no-auto-export
```

**Help:**
```bash
python3 -m monitor.cli run --help
python3 -m monitor.cli export --help
python3 -m monitor.cli stats --help
```

---

## Outputs summary

| Command | Terminal output | Files created/updated |
|--------|-----------------|----------------------|
| `run` (once or loop) | Cycle summary, per-source and per-ticker counts, auto-export path | `news.db`, `out.csv`, `out.json`, `out_grouped_by_ticker.json` (unless `--no-auto-export`) |
| `stats` | Total items, distinct tickers/sources, last run time | None |
| `export` | Nothing (writes to stdout unless you redirect) | Only if you redirect, e.g. `> out.json` |

---

## Config and tickers

- **Config file:** `config.json` (copy of `config.example.json`). Safe to edit.
- **Add/change tickers:** Edit the `tickers` list in `config.json`. Optionally set `company_names` for better Google News results.

---

## Features

- Async RSS (Yahoo Finance, Google News) with retries and throttling
- SQLite storage with deduplication
- CLI: one-off run, loop, export (JSON/CSV), stats
- Web dashboard: filter by ticker/source/time, search, table view, auto-refresh every 15 min
- Optional: Docker, cron, systemd, GitHub Actions (see below)

---

## Deployment

**Docker:**
```bash
docker build -f docker/Dockerfile -t news-monitor .
docker run --rm -v "$(pwd)/data:/data" -v "$(pwd)/config.json:/app/config.json:ro" \
  -e NEWS_DB_PATH=/data/news.db \
  news-monitor run --config /app/config.json --db /data/news.db
```

**Docker Compose:**
```bash
mkdir -p docker/data
cp config.example.json config.json
docker compose -f docker/docker-compose.yml up --build
```

**Cron (every 15 min):**
```cron
*/15 * * * * cd /path/to/news-monitor && .venv/bin/python -m monitor.cli run --config config.json --db news.db >> monitor.log 2>&1
```

**GitHub Actions:** `.github/workflows/monitor.yml` can run on a schedule; DB is emitted as an artifact.

---

## API (when dashboard is running)

- **http://localhost:8001/docs** — OpenAPI docs
- **GET /api/stats** — Total items, items last 24h, last run, counts by ticker/source
- **GET /api/items?since=24h&limit=5** — Items with optional `ticker`, `source`, `since`, `q`, `limit`, `offset`, `sort`

---

## Testing

```bash
pytest
```

---

## Troubleshooting

- **Address already in use:** `lsof -ti :8001 | xargs kill -9` then restart uvicorn.
- **SSL errors (macOS):** `pip install -e .` pulls in `certifi`; the app uses it. If needed: `export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"`.
- **Empty or blocked feeds:** Check `config.json` tickers; reduce `NEWS_CONCURRENCY` or increase `NEWS_MIN_HOST_DELAY_SECONDS`; set a realistic `NEWS_USER_AGENT`.
- **SQLite locked:** Don’t run multiple writers (e.g. two `--loop` processes) against the same `news.db`.
