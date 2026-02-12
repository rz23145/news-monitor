const API_BASE = "";

let allItems = [];
let sortKey = "published_at";
let sortOrder = "desc";
let page = 1;
let perPage = 25;
let searchQuery = "";

function debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

async function api(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(r.statusText);
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
  if (stats.last_run && stats.last_run.finished_at) {
    lastRun = formatDate(stats.last_run.finished_at);
  } else if (stats.generated_at) {
    lastRun = "Static: " + formatDate(stats.generated_at);
  }
  document.getElementById("stat-last-run").textContent = lastRun;
}

function getFilters() {
  const ticker = document.getElementById("filter-ticker").value;
  const source = document.getElementById("filter-source").value;
  const since = document.getElementById("filter-since").value;
  return {
    ticker: ticker || undefined,
    source: source || undefined,
    since: since || undefined,
  };
}

function applyFiltersAndFetch() {
  const filters = getFilters();
  setLoading(true);
  hideError();
  loadItems(filters)
    .then((data) => {
      allItems = data.items || [];
      applySearchAndSort();
      setLoading(false);
      renderTablePage();
      renderCardList();
      updatePagination();
    })
    .catch((e) => {
      setLoading(false);
      showError("Failed to load data. " + (e.message || "Is the backend running?"));
      document.getElementById("table-body").innerHTML = "";
      document.getElementById("empty-state").hidden = false;
      document.getElementById("pagination").innerHTML = "";
    });
}

function getFilteredAndSortedItems() {
  let items = allItems.slice();
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    items = items.filter(
      (i) =>
        (i.title || "").toLowerCase().includes(q) ||
        (i.summary || "").toLowerCase().includes(q)
    );
  }
  const key = sortKey === "origin_source" ? "origin_source" : sortKey;
  items.sort((a, b) => {
    let va = a[key] || "";
    let vb = b[key] || "";
    if (key === "published_at") {
      va = va || "0";
      vb = vb || "0";
    }
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return sortOrder === "desc" ? -cmp : cmp;
  });
  return items;
}

function getPaginatedItems() {
  const full = getFilteredAndSortedItems();
  const start = (page - 1) * perPage;
  return { pageItems: full.slice(start, start + perPage), fullCount: full.length };
}

function renderTablePage() {
  const tbody = document.getElementById("table-body");
  const emptyEl = document.getElementById("empty-state");
  const { pageItems: items, fullCount } = getPaginatedItems();
  const full = getFilteredAndSortedItems();

  document.querySelectorAll(".sortable").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === sortKey) th.classList.add("sort-" + sortOrder);
  });

  if (!items.length) {
    tbody.innerHTML = "";
    emptyEl.hidden = false;
    return;
  }
  emptyEl.hidden = true;

  tbody.innerHTML = items
    .map((item) => {
      const title = item.title || item.headline || "";
      const url = item.url || "#";
      const summary = item.summary || "";
      const ticker = item.ticker || "";
      const source = item.origin_source || item.source || "";
      const idx = full.indexOf(item);
      return `
        <tr data-index="${idx}">
          <td><span class="badge">${escapeHtml(ticker)}</span></td>
          <td><time title="${escapeHtml(formatDate(item.published_at))}">${relativeTime(item.published_at)}</time></td>
          <td><span class="badge">${escapeHtml(source)}</span></td>
          <td class="col-headline"><a href="${escapeHtml(url)}" class="headline-link" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(title) || "—"}</a></td>
          <td class="summary-cell">${escapeHtml(summary) || "—"}</td>
        </tr>
      `;
    })
    .join("");

  const fullList = getFilteredAndSortedItems();
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const idx = parseInt(tr.dataset.index, 10);
      const item = fullList[idx];
      if (item) openDetailModal(item);
    });
  });
}

function renderCardList() {
  const container = document.getElementById("card-list");
  if (!container) return;
  const { pageItems: items } = getPaginatedItems();
  if (items.length === 0) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = items
    .map((item) => {
      const title = item.title || item.headline || "";
      const url = item.url || "#";
      const summary = item.summary || "";
      return `
        <article class="card-item" data-url="${escapeHtml(url)}" data-title="${escapeHtml(title)}" data-summary="${escapeHtml(summary)}" data-ticker="${escapeHtml(item.ticker || "")}" data-source="${escapeHtml(item.origin_source || item.source || "")}" data-published="${escapeHtml(item.published_at || "")}">
          <span class="badge">${escapeHtml(item.ticker || "")}</span>
          <span class="badge">${escapeHtml(item.origin_source || item.source || "")}</span>
          <time title="${escapeHtml(formatDate(item.published_at))}">${relativeTime(item.published_at)}</time>
          <a href="${escapeHtml(url)}" class="headline-link" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(title) || "—"}</a>
          <p class="summary-cell">${escapeHtml(summary) || "—"}</p>
        </article>
      `;
    })
    .join("");

  container.querySelectorAll(".card-item").forEach((el) => {
    el.addEventListener("click", () => {
      openDetailModal({
        title: el.dataset.title,
        url: el.dataset.url,
        summary: el.dataset.summary,
        ticker: el.dataset.ticker,
        origin_source: el.dataset.source,
        published_at: el.dataset.published,
      });
    });
  });
}

function updatePagination() {
  const total = getFilteredAndSortedItems().length;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);

  document.getElementById("pagination-info").textContent =
    total === 0 ? "0 items" : `Showing ${start}–${end} of ${total}`;

  const nav = document.getElementById("pagination");
  if (totalPages <= 1) {
    nav.innerHTML = "";
    return;
  }
  const pages = new Set([1, totalPages]);
  for (let i = Math.max(1, page - 2); i <= Math.min(totalPages, page + 2); i++) pages.add(i);
  const sorted = [...pages].sort((a, b) => a - b);
  let html = "";
  html += `<button type="button" data-page="1" ${page === 1 ? "disabled" : ""}>First</button>`;
  html += `<button type="button" data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>Prev</button>`;
  sorted.forEach((i, idx) => {
    if (idx > 0 && sorted[idx - 1] < i - 1) html += `<span class="pagination-ellipsis">…</span>`;
    html += `<button type="button" data-page="${i}" class="${i === page ? "active" : ""}">${i}</button>`;
  });
  html += `<button type="button" data-page="${page + 1}" ${page === totalPages ? "disabled" : ""}>Next</button>`;
  html += `<button type="button" data-page="${totalPages}" ${page === totalPages ? "disabled" : ""}>Last</button>`;
  nav.innerHTML = html;

  nav.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      page = parseInt(btn.dataset.page, 10);
      renderTablePage();
      renderCardList();
      updatePagination();
    });
  });
}

function openDetailModal(item) {
  const modal = document.getElementById("detail-modal");
  document.getElementById("detail-ticker").textContent = item.ticker ? "Ticker: " + item.ticker : "";
  document.getElementById("detail-meta").textContent =
    (item.origin_source || item.source || "") + " · " + formatDate(item.published_at);
  document.getElementById("detail-headline").textContent = item.title || item.headline || "—";
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
    const key = th.dataset.sort;
    th.addEventListener("click", () => {
      if (sortKey === key) sortOrder = sortOrder === "desc" ? "asc" : "desc";
      else {
        sortKey = key;
        sortOrder = key === "published_at" ? "desc" : "asc";
      }
      page = 1;
      renderTablePage();
      renderCardList();
      updatePagination();
    });
  });
}

async function loadItems(params = {}) {
  const q = new URLSearchParams();
  if (params.ticker) q.append("ticker", params.ticker);
  if (params.source) q.append("source", params.source);
  if (params.since) q.set("since", params.since);
  q.set("limit", "3000");
  const path = "/api/items" + (q.toString() ? "?" + q.toString() : "");
  return api(path);
}

async function init() {
  document.getElementById("error-dismiss").addEventListener("click", hideError);
  document.querySelector(".modal-backdrop").addEventListener("click", closeDetailModal);
  document.querySelector(".modal-close").addEventListener("click", closeDetailModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDetailModal();
  });

  document.getElementById("filter-ticker").addEventListener("change", () => {
    page = 1;
    applyFiltersAndFetch();
  });
  document.getElementById("filter-source").addEventListener("change", () => {
    page = 1;
    applyFiltersAndFetch();
  });
  document.getElementById("filter-since").addEventListener("change", () => {
    page = 1;
    applyFiltersAndFetch();
  });
  document.getElementById("filter-search").addEventListener(
    "input",
    debounce(() => {
      searchQuery = document.getElementById("filter-search").value.trim();
      page = 1;
      renderTablePage();
      renderCardList();
      updatePagination();
    }, 250)
  );
  document.getElementById("per-page").addEventListener("change", (e) => {
    perPage = parseInt(e.target.value, 10);
    page = 1;
    renderTablePage();
    renderCardList();
    updatePagination();
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
    showError("Failed to load. " + (e.message || "Is the backend running?"));
    setLoading(false);
  }
}

init();
