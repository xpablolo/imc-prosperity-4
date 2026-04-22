import {
  subscribe,
  getState,
  getReference,
  setFillsShowAll,
  setFillsCurrentOnly,
} from "../store.js";
import { fmtInt, fmtPrice, fmtSigned } from "../format.js";

export function mountOrderLifecycle({ bodyEl, titleEl, showAllInput, currentOnlyInput }) {
  showAllInput.addEventListener("change", (event) => setFillsShowAll(event.target.checked));
  currentOnlyInput.addEventListener("change", (event) => setFillsCurrentOnly(event.target.checked));

  function render() {
    const state = getState();
    const ref = getReference(state);
    showAllInput.checked = state.fillsShowAll;
    currentOnlyInput.checked = state.fillsCurrentOnly;
    const scopeLabel = state.fillsCurrentOnly ? "current" : state.fillsShowAll ? "all" : "±2.5k ts";
    titleEl.textContent = `Order Lifecycle · ${scopeLabel}`;

    if (!ref) {
      bodyEl.innerHTML = `<div class="logs-empty">Load a strategy to inspect inferred / observed order lifecycle.</div>`;
      return;
    }

    const currentTs = ref.rawTimestamps?.[state.tickIdx] ?? 0;
    let orders = ref.analysis?.lifecycle?.orders ?? [];
    if (state.selectedProduct) orders = orders.filter((order) => order.product === state.selectedProduct);
    if (state.fillsCurrentOnly) {
      orders = orders.filter((order) => order.startTimestamp <= currentTs && order.endTimestamp >= currentTs);
    } else if (!state.fillsShowAll) {
      orders = orders.filter((order) => order.endTimestamp >= currentTs - 2500 && order.startTimestamp <= currentTs + 2500);
    }

    const coverage = ref.analysis?.lifecycle?.coverage ?? { observedOrders: 0, inferredOrders: 0 };

    bodyEl.innerHTML = `
      <div class="section-stack tight">
        <div class="info-banner ${coverage.observedOrders ? "good" : "warn"}">
          <strong>Lifecycle coverage.</strong>
          ${coverage.observedOrders
            ? `${fmtInt(coverage.observedOrders)} órdenes observadas y ${fmtInt(coverage.inferredOrders)} episodios inferidos.`
            : `No hay submissions observadas en los logs actuales. Esta vista reconstruye episodios de orden a partir de fills + contexto del book.`}
        </div>

        <table class="data compact static-table lifecycle-table">
          <thead>
            <tr>
              <th class="left">Obs</th>
              <th class="left">TS</th>
              <th class="left">Product</th>
              <th class="left">Side</th>
              <th class="left">Type</th>
              <th class="left">Status</th>
              <th>Qty</th>
              <th>Filled</th>
              <th>VWAP</th>
              <th>Life</th>
              <th>Queue</th>
              <th>Markout 5</th>
              <th class="left">Context</th>
            </tr>
          </thead>
          <tbody>
            ${orders.length
              ? orders
                  .sort((a, b) => (b.startTickKey ?? 0) - (a.startTickKey ?? 0))
                  .map(
                    (order) => `
                      <tr>
                        <td class="left"><span class="timeline-badge ${order.observed ? "accent" : "dim"}">${order.observed ? "obs" : "inf"}</span></td>
                        <td class="left num muted">${fmtInt(order.startTimestamp)}${order.endTimestamp !== order.startTimestamp ? ` → ${fmtInt(order.endTimestamp)}` : ""}</td>
                        <td class="left">${escapeHtml(order.product)}</td>
                        <td class="left ${order.side === "buy" ? "positive" : "negative"}">${escapeHtml(order.side.toUpperCase())}</td>
                        <td class="left">${escapeHtml(typeLabel(order))}</td>
                        <td class="left">${escapeHtml(order.statusLabel ?? order.status)}</td>
                        <td class="num">${fmtInt(order.quantity)}</td>
                        <td class="num">${fmtInt(order.executedQty)}</td>
                        <td class="num">${fmtPrice(order.vwap)}</td>
                        <td class="num">${fmtInt(order.lifetime)}</td>
                        <td class="num">${order.queueAheadEstimate != null ? fmtInt(order.queueAheadEstimate) : "—"}</td>
                        <td class="num ${tone(order.averageMarkout?.[5])}">${fmtSigned(order.averageMarkout?.[5], 2)}</td>
                        <td class="left lifecycle-context">${escapeHtml(order.summary ?? "—")}</td>
                      </tr>
                    `
                  )
                  .join("")
              : `<tr><td class="empty" colspan="13">No lifecycle episodes match the current filters.</td></tr>`}
          </tbody>
        </table>
      </div>
    `;
  }

  subscribe(render);
  render();
}

function typeLabel(order) {
  if (order.type === "aggressive") return "marketable / aggressive";
  if (order.bookRelation === "inside-spread") return "passive improving";
  return order.type ?? "unknown";
}

function tone(value) {
  if (!Number.isFinite(value)) return "muted";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "muted";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
