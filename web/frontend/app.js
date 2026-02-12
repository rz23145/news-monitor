(function () {
  "use strict";

  const API_BASE =
    typeof window !== "undefined" &&
    (window.location.port === "5173" || window.location.port === "3000")
      ? "http://localhost:8001"
      : "";

  let allItems = [];
  let totalCount = 0;
  let sortKey = "published_at";
  let sortOrder = "desc";
  let page = 1;
  let perPage = 25;
  const AUTO_REFRESH_MS = 15 * 60 * 1000; // 15 minutes
  let autoRefreshTimer = null;

  function api(path) {
    return fetch(API_BASE + path)
      .then(function (r) {
        return r.text().then(function (text) {
          if (!r.ok) throw new Error(text || r.statusText);
          try {
            return JSON.parse(text);
          } catch (_) {
            throw new Error("Server returned invalid JSON");
          }
        });
      });
  }

  function formatDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
    } catch (_) {
      return iso;
    }
  }

  function relativeTime(iso) {
    if (!iso) return "—";
    try {
      var sec = Math.floor((Date.now() - new Date(iso)) / 1000);
      if (sec < 60) return "just now";
      if (sec < 3600) return Math.floor(sec / 60) + "m ago";
      if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
      if (sec < 604800) return Math.floor(sec / 86400) + "d ago";
      return formatDate(iso);
    } catch (_) {
      return iso;
    }
  }

  function escapeHtml(s) {
    if (!s) return "";
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function showError(msg) {
    var banner = document.getElementById("error-banner");
    var text = document.getElementById("error-text");
    if (banner && text) {
      text.textContent = msg;
      banner.hidden = false;
    }
  }

  function hideError() {
    var banner = document.getElementById("error-banner");
    if (banner) banner.hidden = true;
  }

  function setLoading(loading) {
    var loadingEl = document.getElementById("loading");
    var skeleton = document.getElementById("skeleton");
    var tableWrap = document.getElementById("table-wrap");
    if (loadingEl) loadingEl.hidden = !loading;
    if (skeleton) skeleton.hidden = !loading;
    if (tableWrap) tableWrap.hidden = loading;
  }

  function renderStats(stats) {
    var totalEl = document.getElementById("stat-total");
    var twentyFourEl = document.getElementById("stat-24h");
    var lastRunEl = document.getElementById("stat-last-run");
    if (totalEl) totalEl.textContent = stats.total_items != null ? String(stats.total_items) : "—";
    if (twentyFourEl) twentyFourEl.textContent = stats.items_last_24h != null ? String(stats.items_last_24h) : "—";
    var lastRun = "—";
    if (stats.last_run != null && stats.last_run !== "") lastRun = formatDate(stats.last_run);
    if (lastRunEl) lastRunEl.textContent = lastRun;
  }

  function getFilters() {
    var tickerSel = document.getElementById("filter-ticker");
    var sourceSel = document.getElementById("filter-source");
    var tickerVal = tickerSel && tickerSel.value ? tickerSel.value.trim() : "";
    var sourceVal = sourceSel && sourceSel.value ? sourceSel.value.trim() : "";
    var sinceSel = document.getElementById("filter-since");
    var searchInput = document.getElementById("filter-search");
    return {
      tickers: tickerVal ? [tickerVal] : [],
      sources: sourceVal ? [sourceVal] : [],
      since: sinceSel ? sinceSel.value || "24h" : "24h",
      q: searchInput && searchInput.value ? searchInput.value.trim() || null : null,
    };
  }

  function loadItems(params) {
    var q = new URLSearchParams();
    if (params.tickers && params.tickers.length) params.tickers.forEach(function (t) { q.append("ticker", t); });
    if (params.sources && params.sources.length) params.sources.forEach(function (s) { q.append("source", s); });
    if (params.since) q.set("since", params.since);
    if (params.q) q.set("q", params.q);
    q.set("limit", String(params.limit != null ? params.limit : perPage));
    q.set("offset", String(params.offset != null ? params.offset : 0));
    q.set("sort", params.sort || "published_at_desc");
    return api("/api/items?" + q.toString()).then(function (data) {
      return { items: data.items || [], count: data.count != null ? data.count : 0 };
    });
  }

  function applyFiltersAndFetch(silent) {
    var filters = getFilters();
    if (!silent) { setLoading(true); hideError(); }
    var offset = (page - 1) * perPage;
    var sort = sortKey === "published_at" && sortOrder === "desc" ? "published_at_desc" : "published_at_asc";
    loadItems({
      tickers: filters.tickers.length ? filters.tickers : undefined,
      sources: filters.sources.length ? filters.sources : undefined,
      since: filters.since,
      q: filters.q,
      limit: perPage,
      offset: offset,
      sort: sort,
    })
      .then(function (data) {
        allItems = data.items || [];
        totalCount = data.count != null ? data.count : 0;
        if (!silent) setLoading(false);
        renderTablePage();
        updatePagination();
      })
      .catch(function (e) {
        if (!silent) setLoading(false);
        if (!silent) showError(e.message || "Failed to load. Is the backend running? Start: uvicorn web.backend.main:app --reload --port 8001");
        var tbody = document.getElementById("table-body");
        if (tbody) tbody.innerHTML = "";
        var empty = document.getElementById("empty-state");
        if (empty) empty.hidden = false;
        var pag = document.getElementById("pagination");
        if (pag) pag.innerHTML = "";
      });
  }

  function renderTablePage() {
    var tbody = document.getElementById("table-body");
    var emptyEl = document.getElementById("empty-state");
    if (!tbody) return;
    document.querySelectorAll(".sortable").forEach(function (th) {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === sortKey) th.classList.add("sort-" + sortOrder);
    });
    if (!allItems.length) {
      tbody.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    tbody.innerHTML = allItems
      .map(function (item, idx) {
        var headline = item.headline || item.title || "";
        var url = item.url || "#";
        var summary = item.summary || "";
        var ticker = item.ticker || "";
        var source = item.source || item.origin_source || "";
        return (
          '<tr data-index="' + idx + '">' +
          '<td><span class="badge">' + escapeHtml(ticker) + "</span></td>" +
          '<td><time title="' + escapeHtml(formatDate(item.published_at)) + '">' + relativeTime(item.published_at) + "</time></td>" +
          '<td><span class="badge">' + escapeHtml(source) + "</span></td>" +
          '<td class="col-headline"><a href="' + escapeHtml(url) + '" class="headline-link" target="_blank" rel="noopener">' + (escapeHtml(headline) || "—") + "</a></td>" +
          '<td class="summary-cell" title="' + escapeHtml(summary) + '">' + (escapeHtml(summary) || "—") + "</td>" +
          "</tr>"
        );
      })
      .join("");
    tbody.querySelectorAll("tr").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var idx = parseInt(tr.dataset.index, 10);
        var item = allItems[idx];
        if (item) openDetailModal(item);
      });
    });
  }

  function updatePagination() {
    var totalPages = perPage > 0 ? Math.ceil(totalCount / perPage) : 0;
    var infoEl = document.getElementById("pagination-info");
    if (infoEl) infoEl.textContent = totalCount > 0 ? (page + " of " + totalPages + " · " + totalCount + " items") : "—";
    var pagEl = document.getElementById("pagination");
    if (!pagEl) return;
    if (totalPages <= 1) {
      pagEl.innerHTML = "";
      return;
    }
    var html = "";
    if (page > 1) html += '<button type="button" class="btn btn-pag" data-page="' + (page - 1) + '">Previous</button>';
    html += ' <span class="pag-num">' + page + " / " + totalPages + "</span> ";
    if (page < totalPages) html += '<button type="button" class="btn btn-pag" data-page="' + (page + 1) + '">Next</button>';
    pagEl.innerHTML = html;
    pagEl.querySelectorAll(".btn-pag").forEach(function (btn) {
      btn.addEventListener("click", function () {
        page = parseInt(btn.dataset.page, 10);
        applyFiltersAndFetch();
      });
    });
  }

  function openDetailModal(item) {
    var modal = document.getElementById("detail-modal");
    if (!modal) return;
    document.getElementById("detail-ticker").textContent = item.ticker ? "Ticker: " + item.ticker : "";
    document.getElementById("detail-meta").textContent = (item.source || item.origin_source || "") + " · " + formatDate(item.published_at);
    document.getElementById("detail-headline").textContent = item.headline || item.title || "—";
    document.getElementById("detail-summary").textContent = item.summary || "—";
    var link = document.getElementById("detail-url");
    link.href = item.url || "#";
    link.textContent = item.url ? "Open article →" : "";
    modal.hidden = false;
  }

  function closeDetailModal() {
    var modal = document.getElementById("detail-modal");
    if (modal) modal.hidden = true;
  }

  function clearFilters() {
    var tickerSel = document.getElementById("filter-ticker");
    var sourceSel = document.getElementById("filter-source");
    var sinceSel = document.getElementById("filter-since");
    var searchInput = document.getElementById("filter-search");
    if (tickerSel) tickerSel.selectedIndex = 0;
    if (sourceSel) sourceSel.selectedIndex = 0;
    if (sinceSel) sinceSel.value = "24h";
    if (searchInput) searchInput.value = "";
    page = 1;
    applyFiltersAndFetch();
  }

  function init() {
    var dismissBtn = document.getElementById("error-dismiss");
    if (dismissBtn) dismissBtn.addEventListener("click", hideError);
    var backdrop = document.querySelector(".modal-backdrop");
    if (backdrop) backdrop.addEventListener("click", closeDetailModal);
    var closeBtn = document.querySelector(".modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeDetailModal);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDetailModal();
    });
    var btnApply = document.getElementById("btn-apply");
    if (btnApply) btnApply.addEventListener("click", function () { page = 1; applyFiltersAndFetch(); });
    var btnClear = document.getElementById("btn-clear");
    if (btnClear) btnClear.addEventListener("click", clearFilters);
    var btnRefresh = document.getElementById("btn-refresh");
    if (btnRefresh) btnRefresh.addEventListener("click", function () { applyFiltersAndFetch(); });
    var perPageSel = document.getElementById("per-page");
    if (perPageSel) perPageSel.addEventListener("change", function () {
      perPage = parseInt(perPageSel.value, 10);
      page = 1;
      applyFiltersAndFetch();
    });
    document.querySelectorAll(".data-table th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.dataset.sort;
        if (sortKey === key) sortOrder = sortOrder === "desc" ? "asc" : "desc";
        else { sortKey = key; sortOrder = key === "published_at" ? "desc" : "asc"; }
        page = 1;
        applyFiltersAndFetch();
      });
    });

    if (window.location.protocol === "file:") {
      showError("Open from http://localhost:8001/app/ (start backend: uvicorn web.backend.main:app --reload --port 8001)");
      setLoading(false);
      return;
    }

    Promise.all([api("/api/stats"), api("/api/tickers"), api("/api/sources")])
      .then(function (results) {
        var stats = results[0];
        var tickersData = results[1];
        var sourcesData = results[2];
        renderStats(stats);
        var tickerSel = document.getElementById("filter-ticker");
        if (tickerSel) {
          tickerSel.innerHTML = '<option value="">All</option>';
          (tickersData.tickers || []).forEach(function (t) {
            var opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            tickerSel.appendChild(opt);
          });
          tickerSel.selectedIndex = 0;
        }
        var sourceSel = document.getElementById("filter-source");
        if (sourceSel) {
          sourceSel.innerHTML = '<option value="">All</option>';
          (sourcesData.sources || []).forEach(function (s) {
            var opt = document.createElement("option");
            opt.value = s;
            opt.textContent = s;
            sourceSel.appendChild(opt);
          });
          sourceSel.selectedIndex = 0;
        }
        applyFiltersAndFetch();
        // Auto-refresh stats and table every 15 minutes (silent, no loading spinner)
        autoRefreshTimer = setInterval(function () {
          api("/api/stats").then(renderStats).catch(function () {});
          applyFiltersAndFetch(true);
        }, AUTO_REFRESH_MS);
      })
      .catch(function (e) {
        showError(e.message || "Failed to load. Start backend: uvicorn web.backend.main:app --reload --port 8001");
        setLoading(false);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
