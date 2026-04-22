import { subscribe, getState, getReference } from "../store.js";
import { fmtInt, fmtPct, fmtPrice, fmtSigned } from "../format.js";

export function mountExecutionPanel({ bodyEl }) {
  function render() {
    const state = getState();
    const ref = getReference(state);
    const product = state.selectedProduct ?? null;
    if (!ref) {
      bodyEl.innerHTML = `<div class="logs-empty">Load a strategy to inspect execution quality.</div>`;
      return;
    }

    const overall = ref.analysis?.execution?.overall ?? {};
    const byProduct = ref.analysis?.execution?.byProduct ?? [];
    const bySide = ref.analysis?.execution?.bySide ?? [];
    const activeProducts = product ? byProduct.filter((row) => row.key === product) : byProduct;

    bodyEl.innerHTML = `
      <div class="section-stack">
        <div class="info-banner ${overall.coverage?.observedOrders ? "good" : "warn"}">
          <strong>Exacto vs inferido.</strong>
          ${overall.coverage?.observedOrders
            ? `Hay ${fmtInt(overall.coverage.observedOrders)} órdenes observadas; fill ratio y cancel ratio usan esa cobertura.`
            : `No hay order intents observados en los logs actuales. Passive/aggressive, queue ahead y lifecycle usan inferencia sobre fills + book visible.`}
        </div>

        <div class="metric-grid four">
          ${metricCard("fills", fmtInt(overall.totalFills), "observed")}
          ${metricCard("passive fill %", fmtPct(overall.passiveFillPct), "book-based")}
          ${metricCard("aggressive fill %", fmtPct(overall.aggressiveFillPct), "book-based")}
          ${metricCard("avg queue ahead", fmtInt(overall.averageQueueAheadEstimate), overall.coverage?.observedOrders ? "observed/inferred" : "inferred")}
          ${metricCard("IS / shortfall", fmtSigned(overall.averageShortfall, 2), "per-unit")}
          ${metricCard("slippage", fmtSigned(overall.averageSlippage, 2), "per-unit")}
          ${metricCard("markout 1/5/10", `${fmtSigned(overall.averageMarkout?.[1], 2)} · ${fmtSigned(overall.averageMarkout?.[5], 2)} · ${fmtSigned(overall.averageMarkout?.[10], 2)}`, "per-unit")}
          ${metricCard("adverse selection", scoreBadge(overall.adverseSelectionScore), "0-100")}
        </div>

        <div class="split-section two">
          <section>
            <div class="section-title">By product</div>
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">Product</th>
                  <th>Fills</th>
                  <th>Passive %</th>
                  <th>Aggressive %</th>
                  <th>Shortfall</th>
                  <th>Mk5</th>
                  <th>AdvSel</th>
                </tr>
              </thead>
              <tbody>
                ${activeProducts.length
                  ? activeProducts
                      .map(
                        (row) => `
                          <tr>
                            <td class="left">${escapeHtml(row.key)}</td>
                            <td class="num">${fmtInt(row.totalFills)}</td>
                            <td class="num">${fmtPct(row.passiveFillPct)}</td>
                            <td class="num">${fmtPct(row.aggressiveFillPct)}</td>
                            <td class="num ${toneClass(-row.averageShortfall)}">${fmtSigned(row.averageShortfall, 2)}</td>
                            <td class="num ${toneClass(row.averageMarkout?.[5])}">${fmtSigned(row.averageMarkout?.[5], 2)}</td>
                            <td class="num">${scoreBadge(row.adverseSelectionScore)}</td>
                          </tr>
                        `
                      )
                      .join("")
                  : `<tr><td class="empty" colspan="7">No product metrics available.</td></tr>`}
              </tbody>
            </table>
          </section>

          <section>
            <div class="section-title">By side</div>
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">Side</th>
                  <th>Fills</th>
                  <th>Passive %</th>
                  <th>Shortfall</th>
                  <th>Markout 5</th>
                  <th>Realized spr 5</th>
                </tr>
              </thead>
              <tbody>
                ${bySide
                  .map(
                    (row) => `
                      <tr>
                        <td class="left">${escapeHtml(row.key.toUpperCase())}</td>
                        <td class="num">${fmtInt(row.totalFills)}</td>
                        <td class="num">${fmtPct(row.passiveFillPct)}</td>
                        <td class="num ${toneClass(-row.averageShortfall)}">${fmtSigned(row.averageShortfall, 2)}</td>
                        <td class="num ${toneClass(row.averageMarkout?.[5])}">${fmtSigned(row.averageMarkout?.[5], 2)}</td>
                        <td class="num ${toneClass(row.averageRealizedSpread?.[5])}">${fmtSigned(row.averageRealizedSpread?.[5], 2)}</td>
                      </tr>
                    `
                  )
                  .join("")}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    `;
  }

  subscribe(render);
  render();
}

function metricCard(label, value, meta) {
  return `
    <div class="metric-card subtle">
      <div class="metric-card-label">${escapeHtml(label)}</div>
      <div class="metric-card-value num">${escapeHtml(String(value))}</div>
      <div class="metric-card-meta">${escapeHtml(meta)}</div>
    </div>
  `;
}

function scoreBadge(value) {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(0)} / 100`;
}

function toneClass(value) {
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
