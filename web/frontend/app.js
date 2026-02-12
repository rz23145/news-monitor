// Same origin (e.g. frontend served by FastAPI): use "". For separate dev server (Vite on 5173/3000) set to "http://localhost:8000"
const API_BASE =
  typeof window !== "undefined" &&
  (window.location.port === "5173" || window.location.port === "3000")
    ? "http://localhost:8000"
    : "";

let allItems = [];
let totalCount = 0;
let sortKey = "published_at";
let sortOrder = "desc";
let page = 1;
let perPage = 25;

function debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

async function api(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText);
  }
  return r.json();
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function relativeTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sec = Math.floor((now - d) / 1000);
    if (sec < 60) return "just now";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
    if (sec < 604800) return Math.floor(sec / 86400) + "d ago";
    return formatDate(iso);
  } catch {
    return iso;
  }
}

function escapeHtml(s) {
  if (!s) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function showError(msg) {
  const banner = document.getElementById("error-banner");
  const text = document.getElementById("error-text");
  text.textContent = msg;
  banner.hidden = false;
}

function hideError() {
  document.getElementById("error-banner").hidden = true;
}

function setLoading(loading) {
  document.getElementById("loading").hidden = !loading;
  document.getElementById("skeleton").hidden = !loading;
  document.getElementById("table-wrap").hidden = loading;
  const cardList = document.getElementById("card-list");
  if (cardList) cardList.style.visibility = loading ? "hidden" : "";
}

function renderStats(stats) {
  document.getElementById("stat-total").textContent =
    stats.total_items != null ? String(stats.total_items) : "—";
  document.getElementById("stat-24h").textContent =
    stats.items_last_24h != null ? String(stats.items_last_24h) : "—";
  let lastRun = "—";
  if (stats.last_run != null && stats.last_run !== "") {
    lastRun = formatDate(stats.last_run);
  }
  document.getElementById("stat-last-run").textContent = lastRun;
}

function getFilters() {
  const tickerSel = document.getElementById("filter-ticker");
  const sourceSel = document.getElementById("filter-source");
  const tickers = Array.from(tickerSel.selectedOptions)
    .map((o) => o.value)
    .filter(Boolean);
  const sources = Array.from(sourceSel.selectedOptions)
    .map((o) => o.value)
    .filter(Boolean);
  const since = document.getElementById("filter-since").value;
  const q = document.getElementById("filter-search").value.trim() || null;
  return { tickers, sources, since: since || null, q };
}

function applyFiltersAndFetch() {
  const filters = getFilters();
  setLoading(true);
  hideError();
  const offset = (page - 1) * perPage;
  const sort =
    sortKey === "published_at"
      ? sortOrder === "desc"
        ? "published_at_desc"
        : "published_at_asc"
      : "published_at_desc";

  loadItems({
    tickers: filters.tickers.length ? filters.tickers : undefined,
    sources: filters.sources.length ? filters.sources : undefined,
    since: filters.since,
    q: filters.q,
    limit: perPage,
    offset,
    sort,
  })
    .then((data) => {
      allItems = data.items || [];
      totalCount = data.count != null ? data.count : 0;
      setLoading(false);
      renderTablePage();
      renderCardList();
      updatePagination();
    })
    .catch((e) => {
      setLoading(false);
      showError(e.message || "Failed to load data. Is the backend running?");
      document.getElementById("table-body").innerHTML = "";
      document.getElementById("empty-state").hidden = false;
      document.getElementById("pagination").innerHTML = "";
    });
}

function renderTablePage() {
  const tbody = document.getElementById("table-body");
  const emptyEl = document.getElementById("empty-state");

  document.querySelectorAll(".sortable").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === sortKey) th.classList.add("sort-" + sortOrder);
  });

  if (!allItems.length) {
    tbody.innerHTML = "";
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  tbody.innerHTML = allItems
    .map((item, idx) => {
      const headline = item.headline || item.title || "";
      const url = item.url || "#";
      const summary = item.summary || "";
      const ticker = item.ticker || "";
      const source = item.source || item.origin_source || "";
      return `
        <tr data-index="${idx}">
          <td><span class="badge">${escapeHtml(ticker)}</span></td>
          <td><time title="${escapeHtml(formatDate(item.published_at))}">${relativeTime(item.published_at)}</time></td>
          <td><span class="badge">${escapeHtml(source)}</span></td>
          <td class="col-headline"><a href="${escapeHtml(url)}" class="headline-link" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(headline) || "—"}</a></td>
          <td class="summary-cell" title="${escapeHtml(summary)}">${escapeHtml(summary) || "—"}</td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const idx = parseInt(tr.dataset.index, 10);
      const item = allItems[idx];
      if (item) openDetailModal(item);
    });
  });
}

function renderCardList() {
  const container = document.getElementById("card-list");
  if (!container) return;
  if (allItems.length === 0) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = allItems
    .map((item) => {
      const headline = item.headline || item.title || "";
      const url = item.url || "#";
      const summary = item.summary || "";
      return `
        <article class="card-item" data-index="${allItems.indexOf(item)}">
          <span class="badge">${escapeHtml(item.ticker || "")}</span>
          <span class="badge">${escapeHtml(item.source || item.origin_source || "")}</span>
          <time title="${escapeHtml(formatDate(item.published_at))}">${relativeTime(item.published_at)}</time>
          <a href="${escapeHtml(url)}" class="headline-link" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(headline) || "—"}</a>
          <p class="summary-cell">${escapeHtml(summary) || "—"}</p>
        </article>
      `;
    })
    .join("");

  container.querySelectorAll(".card-item").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.index, 10);
      const item = allItems[idx];
      if (item) openDetailModal(item);
    });
  });
}

function updatePagination() {
  const totalPages = Math.max(1, Math.ceil(totalCount / perPage));
  const start = totalCount === 0 ? 0 : (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, totalCount);

  document.getElementById("pagination-info").textContent =
    totalCount === 0 ? "0 items" : `Showing ${start}–${end} of ${totalCount}`;

  const nav = document.getElementById("pagination");
  if (totalPages <= 1) {
    nav.innerHTML = "";
    return;
  }
  const pages = new Set([1, totalPages]);
  for (let i = Math.max(1, page - 2); i <= Math.min(totalPages, page + 2); i++)
    pages.add(i);
  const sorted = [...pages].sort((a, b) => a - b);
  let html = "";
  html += `<button type="button" data-page="1" ${page === 1 ? "disabled" : ""}>First</button>`;
  html += `<button type="button" data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>Prev</button>`;
  sorted.forEach((i, idx) => {
    if (idx > 0 && sorted[idx - 1] < i - 1)
      html += `<span class="pagination-ellipsis">…</span>`;
    html += `<button type="button" data-page="${i}" class="${i === page ? "active" : ""}">${i}</button>`;
  });
  html += `<button type="button" data-page="${page + 1}" ${page === totalPages ? "disabled" : ""}>Next</button>`;
  html += `<button type="button" data-page="${totalPages}" ${page === totalPages ? "disabled" : ""}>Last</button>`;
  nav.innerHTML = html;

  nav.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      page = parseInt(btn.dataset.page, 10);
      applyFiltersAndFetch();
    });
  });
}

function openDetailModal(item) {
  const modal = document.getElementById("detail-modal");
  document.getElementById("detail-ticker").textContent = item.ticker
    ? "Ticker: " + item.ticker
    : "";
  document.getElementById("detail-meta").textContent =
    (item.source || item.origin_source || "") + " · " + formatDate(item.published_at);
  document.getElementById("detail-headline").textContent =
    item.headline || item.title || "—";
  document.getElementById("detail-summary").textContent = item.summary || "—";
  const link = document.getElementById("detail-url");
  link.href = item.url || "#";
  link.textContent = item.url ? "Open article →" : "";
  modal.hidden = false;
}

function closeDetailModal() {
  document.getElementById("detail-modal").hidden = true;
}

function initSortableHeaders() {
  document.querySelectorAll(".data-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) sortOrder = sortOrder === "desc" ? "asc" : "desc";
      else {
        sortKey = key;
        sortOrder = key === "published_at" ? "desc" : "asc";
      }
      page = 1;
      applyFiltersAndFetch();
    });
  });
}

async function loadItems(params) {
  const q = new URLSearchParams();
  if (params.tickers && params.tickers.length)
    params.tickers.forEach((t) => q.append("ticker", t));
  if (params.sources && params.sources.length)
    params.sources.forEach((s) => q.append("source", s));
  if (params.since) q.set("since", params.since);
  if (params.q) q.set("q", params.q);
  q.set("limit", String(params.limit != null ? params.limit : perPage));
  q.set("offset", String(params.offset != null ? params.offset : 0));
  if (params.sort) q.set("sort", params.sort);
  const path = "/api/items?" + q.toString();
  const data = await api(path);
  return { items: data.items || [], count: data.count != null ? data.count : 0 };
}

function clearFilters() {
  document.getElementById("filter-ticker").selectedIndex = -1;
  const tickerOpts = document.getElementById("filter-ticker").options;
  for (let i = 0; i < tickerOpts.length; i++) tickerOpts[i].selected = false;
  document.getElementById("filter-source").selectedIndex = -1;
  const sourceOpts = document.getElementById("filter-source").options;
  for (let i = 0; i < sourceOpts.length; i++) sourceOpts[i].selected = false;
  document.getElementById("filter-since").value = "24h";
  document.getElementById("filter-search").value = "";
  page = 1;
  applyFiltersAndFetch();
}

async function init() {
  document.getElementById("error-dismiss").addEventListener("click", hideError);
  document
    .querySelector(".modal-backdrop")
    .addEventListener("click", closeDetailModal);
  document.querySelector(".modal-close").addEventListener("click", closeDetailModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDetailModal();
  });

  document.getElementById("btn-apply").addEventListener("click", () => {
    page = 1;
    applyFiltersAndFetch();
  });
  document.getElementById("btn-clear").addEventListener("click", clearFilters);
  document.getElementById("btn-refresh").addEventListener("click", () => {
    applyFiltersAndFetch();
  });

  document.getElementById("per-page").addEventListener("change", (e) => {
    perPage = parseInt(e.target.value, 10);
    page = 1;
    applyFiltersAndFetch();
  });

  initSortableHeaders();

  try {
    const [stats, tickers, sources] = await Promise.all([
      api("/api/stats"),
      api("/api/tickers"),
      api("/api/sources"),
    ]);
    renderStats(stats);
    const tickerSel = document.getElementById("filter-ticker");
    tickerSel.innerHTML = '<option value="">All</option>';
    (tickers.tickers || []).forEach((t) => {
      const o = document.createElement("option");
      o.value = t;
      o.textContent = t;
      tickerSel.appendChild(o);
    });
    const sourceSel = document.getElementById("filter-source");
    sourceSel.innerHTML = '<option value="">All</option>';
    (sources.sources || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      sourceSel.appendChild(o);
    });
    applyFiltersAndFetch();
  } catch (e) {
    showError(e.message || "Failed to load. Is the backend running?");
    setLoading(false);
  }
}

init();
