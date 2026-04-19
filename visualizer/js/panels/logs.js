import {
  subscribe,
  getState,
  getReference,
  setLogTab,
  setTickIdx,
} from "../store.js";
import { decodeLambdaLog } from "../parser.js";

export function mountLogs({ bodyEl, tsEl, tabsEl }) {
  const timelineState = {
    type: "all",
    query: "",
    nearOnly: true,
    focusQuery: false,
  };

  tabsEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    setLogTab(btn.dataset.logTab);
  });

  bodyEl.addEventListener("change", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches("[data-timeline-type]")) {
      timelineState.type = target.value;
      render();
    }
    if (target.matches("[data-timeline-near]")) {
      timelineState.nearOnly = target.checked;
      render();
    }
  });

  bodyEl.addEventListener("input", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches("[data-timeline-query]")) {
      timelineState.query = target.value.toLowerCase();
      timelineState.focusQuery = true;
      render();
    }
  });

  bodyEl.addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-tick-idx]");
    if (!row) return;
    setTickIdx(Number(row.dataset.tickIdx));
  });

  function render() {
    const state = getState();
    const ref = getReference(state);
    for (const t of tabsEl.querySelectorAll(".tab")) {
      t.classList.toggle("active", t.dataset.logTab === state.logTab);
    }

    if (!ref) {
      bodyEl.innerHTML = `<div class="logs-empty">No strategy loaded.</div>`;
      tsEl.textContent = "";
      return;
    }

    const tickIdx = state.tickIdx;
    const tickKey = ref.timestamps[tickIdx];
    const rawTs = ref.rawTimestamps[tickIdx] ?? 0;
    const day = ref.days[tickIdx] ?? 0;
    tsEl.textContent = `D${day} · TS ${rawTs.toLocaleString()}`;

    if (state.logTab === "timeline") {
      bodyEl.innerHTML = renderTimeline(ref, state, timelineState);
      const queryInput = bodyEl.querySelector("[data-timeline-query]");
      if (queryInput && queryInput.value !== timelineState.query) {
        queryInput.value = timelineState.query;
      }
      if (queryInput && timelineState.focusQuery) {
        queryInput.focus();
        queryInput.setSelectionRange(queryInput.value.length, queryInput.value.length);
        timelineState.focusQuery = false;
      }
      const typeSelect = bodyEl.querySelector("[data-timeline-type]");
      if (typeSelect) typeSelect.value = timelineState.type;
      const nearCheck = bodyEl.querySelector("[data-timeline-near]");
      if (nearCheck) nearCheck.checked = timelineState.nearOnly;
      return;
    }

    const info = ref.logIndexByTick[tickKey];
    let sandbox = "";
    let lambda = "";
    let decoded = null;
    if (info) {
      const entry = ref.rawLogs[info.start];
      sandbox = entry?.sandboxLog ?? "";
      lambda = entry?.lambdaLog ?? "";
      decoded = decodeLambdaLog(lambda);
    }
    const tab = state.logTab;
    const showRaw = tab === "sandbox" ? sandbox : lambda;
    if (tab === "trader") {
      if (decoded?.ok) {
        bodyEl.textContent = decoded.pretty;
      } else {
        bodyEl.innerHTML = `<div class="logs-empty">
          No structured trader data at this tick.
          <div class="hint">Si esperabas state dumps acá, tu logger necesita emitir el payload estructurado.</div>
        </div>`;
      }
      return;
    }

    const isEmpty = !showRaw || showRaw.trim().length === 0;
    if (isEmpty) {
      const label = tab === "sandbox" ? "sandbox" : "algorithm";
      const hint =
        tab === "lambda"
          ? "No algorithm logs at this tick. If you expect them, your run needs print() or structured lambda logging."
          : "Sandbox logs are usually empty unless something failed upstream.";
      bodyEl.innerHTML = `<div class="logs-empty">No ${label} logs at this tick.<div class="hint">${hint}</div></div>`;
      return;
    }
    bodyEl.textContent = showRaw;
  }

  subscribe(render);
  render();
}

function renderTimeline(ref, state, filters) {
  const tickIdx = state.tickIdx;
  const currentTs = ref.rawTimestamps[tickIdx] ?? 0;
  const currentDay = ref.days[tickIdx] ?? 0;
  const selectedProduct = state.selectedProduct ?? null;
  const query = filters.query.trim();

  const rows = (ref.events ?? []).filter((event) => {
    if (selectedProduct && event.product && event.product !== selectedProduct) {
      return false;
    }
    if (filters.type === "log" && !["algorithm", "sandbox"].includes(event.type)) {
      return false;
    }
    if (filters.type !== "all" && filters.type !== "log" && event.type !== filters.type) {
      return false;
    }
    if (filters.nearOnly) {
      if ((event.day ?? 0) !== currentDay) return false;
      if (Math.abs((event.timestamp ?? 0) - currentTs) > 5000) return false;
    }
    if (!query) return true;
    const hay = `${event.type} ${event.product ?? ""} ${event.side ?? ""} ${event.detail ?? ""} ${event.raw ?? ""}`.toLowerCase();
    return hay.includes(query);
  });

  const tableRows = rows.length
    ? rows
        .slice(0, 400)
        .map((event) => {
          const idx = nearestTickIndex(ref, event.tickKey ?? 0);
          return `
            <tr data-tick-idx="${idx}" class="timeline-row type-${event.type}">
              <td class="left num">${event.day ?? 0}</td>
              <td class="left num">${event.timestamp ?? "—"}</td>
              <td class="left"><span class="timeline-badge ${badgeClass(event.type)}">${escapeHtml(event.type)}</span></td>
              <td class="left">${escapeHtml(event.product ?? "—")}</td>
              <td class="left">${escapeHtml(event.side ? event.side.toUpperCase() : "—")}</td>
              <td class="num">${Number.isFinite(event.price) ? event.price.toFixed(1) : "—"}</td>
              <td class="num">${Number.isFinite(event.quantity) ? event.quantity : "—"}</td>
              <td class="left timeline-detail" title="${escapeAttr(event.raw || event.detail || "")}">${escapeHtml(event.detail ?? "")}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td class="empty" colspan="8">No timeline events match the current filters.</td></tr>`;

  return `
    <div class="timeline-toolbar">
      <select class="input" data-timeline-type>
        <option value="all">All events</option>
        <option value="fill">Own fills</option>
        <option value="trade">Market trades</option>
        <option value="log">Logs</option>
        <option value="order">Orders</option>
        <option value="warning">Warnings</option>
      </select>
      <label class="check small"><input type="checkbox" data-timeline-near checked /> near tick</label>
      <input class="input timeline-search" data-timeline-query placeholder="search events, logs, products" />
    </div>
    <div class="table-body timeline-body">
      <table class="data timeline-table">
        <thead>
          <tr>
            <th class="left">Day</th>
            <th class="left">TS</th>
            <th class="left">Type</th>
            <th class="left">Product</th>
            <th class="left">Side</th>
            <th>Price</th>
            <th>Qty</th>
            <th class="left">Detail</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
  `;
}

function nearestTickIndex(ref, target) {
  const ts = ref.timestamps ?? [];
  let lo = 0;
  let hi = ts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (ts[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function badgeClass(type) {
  if (type === "fill") return "ok";
  if (type === "trade") return "muted";
  if (type === "warning") return "warn";
  if (type === "order") return "accent";
  return "dim";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}
