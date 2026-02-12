# Real-Time Financial News Monitoring System

Production-ready case study that monitors financial news for 10 equity tickers every 15 minutes from Yahoo Finance RSS and Google News RSS. It uses async concurrency, robust retries with backoff, deduplication, and SQLite storage. The CLI supports one-off runs, continuous looping, exports, and run statistics.

## Features
- Async RSS fetching with aiohttp, global concurrency, per-host throttling, and retries
- RSS parsing via feedparser with UTC-normalized timestamps
- SQLite storage with strong schema, indexes, and idempotent inserts
- Cross-source deduplication with stable hash keys
- Structured logging with per-cycle, per-source, and per-ticker stats
- JSON/CSV export for snapshots
- Docker, docker-compose, GitHub Actions schedule, cron, and systemd examples
- Unit tests for parsing and dedup logic (no network calls)

## Quickstart (local, step-by-step)
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
cp config.example.json config.json
python3 -m monitor.cli run --config config.json --db news.db
```
What you just created:
- `news.db` is the SQLite database in this folder.
- `config.json` is your local config (safe to edit).

## Run forever locally (updates every 15 minutes)
```bash
python3 -m monitor.cli run --config config.json --db news.db --loop
```
Want a different interval? Example 5 minutes:
```bash
python3 -m monitor.cli run --config config.json --db news.db --loop --interval 300
```

## Auto-generated exports
After every successful `run` (single cycle or each loop iteration), the CLI automatically generates in the repo root (current working directory):

- **out.csv** — last 24 hours, columns: ticker, published_at, source, headline, url, summary, first_seen_at; sorted by ticker ASC, published_at DESC
- **out.json** — last 24 hours, flat list of items
- **out_grouped_by_ticker.json** — last 24 hours, structure `items_by_ticker: { "AAPL": [...], "MSFT": [...] }`

To skip auto-export, pass **--no-auto-export**:

```bash
python3 -m monitor.cli run --config config.json --db news.db --no-auto-export
```

## Export sample
```bash
python3 -m monitor.cli export --db news.db --format json --since 24h > out.json
```
CSV exports are sorted by `published_at` descending by default. Use `--ticker` to filter.
Output files are created in this folder (repo root) unless you redirect elsewhere:
- `out.json` or `out.csv`

Existing export behavior is unchanged. Optional flags:
- `--sort ticker,published_desc` — sort by ticker ASC, published_at DESC; CSV uses columns headline, first_seen_at
- `--group-by ticker` (JSON only) — output `items_by_ticker: { "AAPL": [...], ... }`

## How to add tickers
Edit `config.json` and update the `tickers` list. Optionally add `company_names` entries to improve Google News queries.

## How dedup works (brief)
Each item generates a stable `dedup_key` by hashing a normalized URL (or guid), title, publisher, and a published date bucket. The database enforces uniqueness on this key using `INSERT OR IGNORE`, which ensures idempotent runs across tickers and sources.

## CLI usage
```bash
python3 -m monitor.cli run --help
python3 -m monitor.cli export --help
python3 -m monitor.cli stats --help
```
Additional export examples:
```bash
python3 -m monitor.cli export --db news.db --format json --since 24h --group-by ticker > out.json
python3 -m monitor.cli export --db news.db --format csv --since 24h --ticker AAPL > aapl.csv
```

## Where files are on your computer
Assuming you run commands from the repo folder:
- Database: `news.db`
- JSON export: `out.json` (or any filename you redirect to)
- CSV export: `out.csv` (or any filename you redirect to)
- Config: `config.json`

## How to see it working live
Run the loop in one terminal:
```bash
python3 -m monitor.cli run --config config.json --db news.db --loop
```
In another terminal, watch stats update:
```bash
watch -n 5 "python3 -m monitor.cli stats --db news.db"
```
Or preview recent rows:
```bash
watch -n 30 "python3 -m monitor.cli export --db news.db --format csv --since 1h | head -n 5"
```

## Configuration
Primary config lives in `config.json` (see `config.example.json`). You can override key settings with environment variables:
- `NEWS_DB_PATH`
- `NEWS_CONCURRENCY`
- `NEWS_INTERVAL_SECONDS`
- `NEWS_USER_AGENT`
- `NEWS_TIMEOUT_SECONDS`
- `NEWS_MAX_RETRIES`
- `NEWS_MIN_HOST_DELAY_SECONDS`
- `NEWS_GNEWS_HL`
- `NEWS_GNEWS_GL`
- `NEWS_GNEWS_CEID`

## Deployment

### Docker build/run
```bash
docker build -f docker/Dockerfile -t news-monitor .
docker run --rm -v "$(pwd)/data:/data" -v "$(pwd)/config.json:/app/config.json:ro" \
  -e NEWS_DB_PATH=/data/news.db \
  news-monitor run --config /app/config.json --db /data/news.db
```

### Docker Compose
```bash
mkdir -p docker/data
cp config.example.json config.json
docker compose -f docker/docker-compose.yml up --build
```

SQLite persistence is handled via the `docker/data` volume mount.

### Cron (every 15 minutes)
```cron
*/15 * * * * cd /path/to/news-monitor && /path/to/venv/bin/python -m monitor.cli run --config config.json --db news.db >> monitor.log 2>&1
```

### systemd unit + timer
Create `/etc/systemd/system/news-monitor.service`:
```ini
[Unit]
Description=Financial News Monitor

[Service]
WorkingDirectory=/path/to/news-monitor
ExecStart=/path/to/venv/bin/python -m monitor.cli run --config config.json --db news.db
Restart=on-failure
```

Create `/etc/systemd/system/news-monitor.timer`:
```ini
[Unit]
Description=Run Financial News Monitor every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now news-monitor.timer
```

### GitHub Actions schedule
`.github/workflows/monitor.yml` runs every 15 minutes. Since GitHub Actions runners are ephemeral, the SQLite database is uploaded as an artifact after each run. You can download artifacts to persist history, or replace the artifact step with S3 storage if needed.

## Run Dashboard
A production-style web dashboard for reading and filtering news. No charts—focused on the items table.

<!-- Screenshot: run the dashboard and add a file e.g. docs/dashboard-screenshot.png, then use: ![Dashboard](docs/dashboard-screenshot.png) -->

**Local mode** (reads from SQLite):

```bash
# From repo root (after pip install -e .)
python3 -m web.backend.main
```

Then open http://localhost:8000

**Static mode** (reads from pre-generated JSON, no DB):

```bash
export NEWS_UI_MODE=static
export NEWS_UI_JSON_PATH=out_grouped_by_ticker.json
python3 -m web.backend.main
```

### UI features
- **Stats row** — Total items, items in last 24h, last run time.
- **Filters** — Single-select Ticker and Source (with “All”), time range (1h, 6h, 24h, 7d, 30d), and a search box. Filters apply automatically (search is debounced 250ms); no Apply button.
- **Table** — Columns: Ticker (badge), Published (relative time; exact time in tooltip), Source (badge), Headline (link), Summary (truncated). Sortable column headers (click to toggle asc/desc; default: Published descending). Sticky header when scrolling. Row hover highlight. Click a row to open a **details modal** with full headline, summary, URL, and metadata.
- **Pagination** — 25 / 50 / 100 rows per page with First, Prev, Next, Last and page numbers.
- **Empty state** — Message with a hint to widen time range or clear filters when no items match.
- **Loading & errors** — Spinner while fetching; dismissible error banner if the API fails.
- **Responsive** — On narrow screens (≤700px) the table is replaced by a card list; filters stack into two then one column.

## Testing
```bash
pytest
```

## Troubleshooting
- RSS blocked or rate limited: reduce `NEWS_CONCURRENCY`, increase `NEWS_MIN_HOST_DELAY_SECONDS`, and verify your `NEWS_USER_AGENT`.
- SSL certificate errors (macOS): the app uses the `certifi` CA bundle by default. Ensure `pip install -e .` (or `certifi`) is installed. If problems persist, set `export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"` before running.
- Timeouts: increase `NEWS_TIMEOUT_SECONDS` or check network connectivity.
- Empty results: verify tickers and check feed URLs manually.
- SQLite locked: avoid running multiple loops against the same DB file.

## Design notes / trade-offs
- RSS sources only: avoids paid APIs, keeps the system lightweight.
- SQLite storage: simple, portable, and fast for this scale; swap for Postgres when needed.
- Concurrency limits: balances throughput with feed politeness to reduce blocks.
- Dedup strategy: deterministic hashing with a date bucket prevents repeat ingestion.
- Future improvements: sentiment tagging, alerting, message queues, and backfills.
