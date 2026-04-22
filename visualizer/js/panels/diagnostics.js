import { subscribe, getState, getReference } from "../store.js";
import { fmtInt, fmtPct, fmtSigned } from "../format.js";

export function mountDiagnostics({ bodyEl }) {
  function render() {
    const state = getState();
    const ref = getReference(state);
    if (!ref) {
      bodyEl.innerHTML = `<div class="logs-empty">Load a strategy to inspect diagnostics and PnL decomposition.</div>`;
      return;
    }

    const analysis = ref.analysis ?? {};
    const diagnostics = analysis.diagnostics ?? {};
    const overall = analysis.pnlBreakdown?.overall ?? {};
    const concentration = diagnostics.concentration?.byProduct ?? [];
    const slices = diagnostics.sliceStats ?? [];
    const regimeBlocks = diagnostics.regimeStats ?? {};
    const insights = analysis.insights ?? [];

    bodyEl.innerHTML = `
      <div class="section-stack">
        <div class="metric-grid four">
          ${scoreCard("consistency", diagnostics.scores?.consistency, "más alto = más parejo")}
          ${scoreCard("fragility", diagnostics.scores?.fragility, "más alto = más frágil")}
          ${scoreCard("stability", diagnostics.scores?.stability, "combina consistencia y fragilidad")}
          ${metricCard("Sharpe-like", fmtSigned(diagnostics.sharpeLike, 2), "heurístico")}
          ${metricCard("expectancy", fmtSigned(diagnostics.expectancy, 2), "por trade cerrado")}
          ${metricCard("hit rate", fmtPct(diagnostics.hitRate), "trade-level")}
          ${metricCard("time under water", fmtPct(diagnostics.timeUnderWater?.pct), `max ${fmtInt(diagnostics.timeUnderWater?.longestTicks)} ticks`) }
          ${metricCard("inventory", `${fmtInt(diagnostics.inventory?.maxAbs)} max · ${fmtInt(diagnostics.inventory?.averageAbs)} avg`, "abs pos")}
        </div>

        <section>
          <div class="section-title">Interpretación automática</div>
          <div class="insight-grid">
            ${insights.map((card) => insightCard(card)).join("")}
          </div>
        </section>

        <section>
          <div class="section-title">PnL decomposition (exacto vs aproximado)</div>
          <div class="metric-grid four">
            ${metricCard("mark-to-market", fmtSigned(overall.markToMarketPnl, 0), "exacto si la serie PnL es confiable")}
            ${metricCard("realized PnL", fmtSigned(overall.realizedPnl, 0), "FIFO exact on fills")}
            ${metricCard("unrealized PnL", fmtSigned(overall.unrealizedPnl, 0), "open lots vs última fair")}
            ${metricCard("inventory PnL", fmtSigned(overall.inventoryPnlApprox, 0), "aprox: pos_{t-1} × Δfair")}
            ${metricCard("spread capture", fmtSigned(overall.spreadCaptureApprox, 0), "aprox: fair - fill")}
            ${metricCard("execution cost", fmtSigned(overall.executionCostApprox, 0), "aprox: -shortfall")}
            ${metricCard("adverse selection", fmtSigned(overall.adverseSelectionApprox, 0), "aprox: min(markout5, 0)")}
            ${metricCard("PnL / trade", fmtSigned(diagnostics.pnlPerTrade, 2), "headline")}
          </div>
        </section>

        <div class="split-section two">
          <section>
            <div class="section-title">Best / worst episodes</div>
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">Slice</th>
                  <th>PnL</th>
                  <th>Fills</th>
                  <th>Aggressive %</th>
                </tr>
              </thead>
              <tbody>
                ${[...slices]
                  .sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0))
                  .slice(0, 3)
                  .map((row) => episodeRow(row, "best"))
                  .join("")}
                ${[...slices]
                  .sort((a, b) => (a.pnl ?? 0) - (b.pnl ?? 0))
                  .slice(0, 3)
                  .map((row) => episodeRow(row, "worst"))
                  .join("")}
              </tbody>
            </table>
          </section>

          <section>
            <div class="section-title">Concentration by product</div>
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">Product</th>
                  <th>PnL share</th>
                  <th>Volume share</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                ${concentration
                  .map(
                    (row) => `
                      <tr>
                        <td class="left">${escapeHtml(row.product)}</td>
                        <td class="num">${fmtPct(row.pnlShare)}</td>
                        <td class="num">${fmtPct(row.volumeShare)}</td>
                        <td class="num ${tone(row.pnl)}">${fmtSigned(row.pnl, 0)}</td>
                      </tr>
                    `
                  )
                  .join("")}
              </tbody>
            </table>
          </section>
        </div>

        <section>
          <div class="section-title">Performance by regime</div>
          <div class="regime-grid">
            ${Object.entries(regimeBlocks)
              .map(([name, rows]) => regimeTable(name, rows))
              .join("")}
          </div>
        </section>
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

function scoreCard(label, score, meta) {
  const cls = !Number.isFinite(score) ? "" : score >= 70 ? "good" : score <= 45 ? "warn" : "";
  return `
    <div class="metric-card ${cls}">
      <div class="metric-card-label">${escapeHtml(label)}</div>
      <div class="metric-card-value num">${Number.isFinite(score) ? score.toFixed(0) : "—"}</div>
      <div class="metric-card-meta">${escapeHtml(meta)}</div>
    </div>
  `;
}

function insightCard(card) {
  return `
    <article class="insight-card ${card.tone}">
      <div class="insight-card-title">${escapeHtml(card.title)}</div>
      <div class="insight-card-body">${escapeHtml(card.body)}</div>
    </article>
  `;
}

function episodeRow(row, kind) {
  return `
    <tr>
      <td class="left">${kind === "best" ? "▲" : "▼"} ${fmtInt(row.startRawTs)}-${fmtInt(row.endRawTs)}</td>
      <td class="num ${tone(row.pnl)}">${fmtSigned(row.pnl, 0)}</td>
      <td class="num">${fmtInt(row.fillCount)}</td>
      <td class="num">${fmtPct(row.aggressiveFillPct)}</td>
    </tr>
  `;
}

function regimeTable(name, rows) {
  return `
    <section class="regime-card">
      <div class="section-title inline">${escapeHtml(name)}</div>
      <table class="data compact static-table">
        <thead>
          <tr>
            <th class="left">Bucket</th>
            <th>PnL</th>
            <th>Ticks</th>
            <th>Avg/tick</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <td class="left">${escapeHtml(row.key)}</td>
                  <td class="num ${tone(row.pnl)}">${fmtSigned(row.pnl, 0)}</td>
                  <td class="num">${fmtInt(row.ticks)}</td>
                  <td class="num ${tone(row.avgPnlPerTick)}">${fmtSigned(row.avgPnlPerTick, 3)}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;
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
