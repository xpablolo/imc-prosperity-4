import { subscribe, getState, getReference } from "../store.js";
import { fmtInt, fmtPct, fmtPrice, fmtSigned } from "../format.js";

export function mountWhatHappened({ bodyEl, titleEl, valueEl }) {
  function render() {
    const state = getState();
    const ref = getReference(state);
    const product = state.selectedProduct ?? ref?.products?.[0] ?? null;
    titleEl.textContent = `What happened here?${product ? ` · ${product}` : ""}`;
    if (!ref || !product) {
      bodyEl.innerHTML = `<div class="logs-empty">Load a strategy to get an automatic narrative for the selected tick.</div>`;
      valueEl.textContent = "";
      return;
    }

    const ps = ref.series?.[product] ?? {};
    const tickIdx = state.tickIdx;
    const currentTs = ref.rawTimestamps?.[tickIdx] ?? 0;
    const spread = ps.spread?.[tickIdx] ?? NaN;
    const mid = ps.midPrice?.[tickIdx] ?? NaN;
    const micro = ps.microPrice?.[tickIdx] ?? NaN;
    const imbalance = ps.imbalance?.[tickIdx] ?? NaN;
    const position = ps.position?.[tickIdx] ?? 0;
    const limit = ref.positionLimits?.[product] ?? 0;
    const riskRatio = limit > 0 ? Math.abs(position) / limit : NaN;
    const recentFills = (ref.analysis?.fills ?? []).filter(
      (fill) => fill.product === product && Math.abs(fill.tickIdx - tickIdx) <= 5
    );
    const lastOrder = [...(ref.analysis?.lifecycle?.orders ?? [])]
      .filter((order) => order.product === product && order.startTickIdx <= tickIdx)
      .sort((a, b) => (b.startTickIdx ?? 0) - (a.startTickIdx ?? 0))[0];
    const recentPnl = windowDelta(ref.totalPnl ?? [], tickIdx, 15);

    const bullets = [];
    bullets.push(describeBook(spread, mid, micro, imbalance));
    bullets.push(describeInventory(position, limit, riskRatio));
    if (recentFills.length > 0) bullets.push(describeRecentFills(recentFills));
    else bullets.push("No hubo fills propios muy cerca del tick actual; lo que estás viendo es más contexto de mercado que ejecución directa.");
    bullets.push(describeRecentPnl(recentPnl));
    if (lastOrder) bullets.push(describeOrder(lastOrder));

    const tone = riskRatio > 0.7 ? "risk" : recentPnl > 0 ? "good" : "neutral";
    valueEl.textContent = tone === "risk" ? "inventory stressed" : tone === "good" ? "favorable local tape" : "mixed";

    bodyEl.innerHTML = `
      <div class="explain-panel ${tone}">
        <div class="explain-panel-head">
          <div>
            <div class="explain-title">Resumen automático del tick ${fmtInt(tickIdx)}</div>
            <div class="muted tiny">D${ref.days?.[tickIdx] ?? 0} · TS ${fmtInt(currentTs)}</div>
          </div>
          <div class="explain-badge ${tone}">${tone === "risk" ? "riesgoso" : tone === "good" ? "bueno" : "neutral"}</div>
        </div>
        <ul class="explain-list">
          ${bullets.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </div>
    `;
  }

  subscribe(render);
  render();
}

function describeBook(spread, mid, micro, imbalance) {
  const deltaMicro = Number.isFinite(micro) && Number.isFinite(mid) ? micro - mid : NaN;
  const bias = Number.isFinite(imbalance)
    ? imbalance >= 0.58
      ? "bid-heavy"
      : imbalance <= 0.42
        ? "ask-heavy"
        : "balanced"
    : "unknown";
  return `Libro actual: spread ${fmtPrice(spread)}, mid ${fmtPrice(mid)}, micro-mid ${Number.isFinite(deltaMicro) ? fmtSigned(deltaMicro, 2) : "—"}. El imbalance luce ${bias}.`;
}

function describeInventory(position, limit, riskRatio) {
  if (!Number.isFinite(position)) return "No hay posición visible para este producto en el tick actual.";
  if (!Number.isFinite(riskRatio)) return `Posición actual ${fmtSigned(position, 0)}.`;
  if (riskRatio > 0.7) {
    return `Inventario alto: ${fmtSigned(position, 0)} sobre un límite ±${fmtInt(limit)}. Si el book gira, el PnL puede depender más del inventory beta que del edge de ejecución.`;
  }
  if (riskRatio > 0.35) {
    return `Inventario intermedio: ${fmtSigned(position, 0)} / ±${fmtInt(limit)}. No está al límite, pero ya condiciona decisiones de quoting/agresión.`;
  }
  return `Inventario controlado: ${fmtSigned(position, 0)} / ±${fmtInt(limit)}.`;
}

function describeRecentFills(fills) {
  const passive = fills.filter((fill) => fill.context?.mode === "passive").length;
  const aggressive = fills.filter((fill) => fill.context?.mode === "aggressive").length;
  const avgMarkout5 = mean(
    fills.map((fill) => fill.horizons?.[5]?.markout).filter(Number.isFinite)
  );
  return `Hubo ${fills.length} fills recientes (${passive} pasivos, ${aggressive} agresivos). El markout medio a 5 ticks es ${Number.isFinite(avgMarkout5) ? fmtSigned(avgMarkout5, 2) : "—"}, útil para juzgar adverse selection.`;
}

function describeRecentPnl(delta) {
  if (!Number.isFinite(delta)) return "No pude calcular el cambio reciente de PnL.";
  if (delta > 0) return `En la ventana reciente (~15 ticks), el PnL viene ${fmtSigned(delta, 0)}. Ojo: mirá si eso viene de edge o solo de mark-to-market con inventario.`;
  if (delta < 0) return `En la ventana reciente (~15 ticks), el PnL cae ${fmtSigned(delta, 0)}. Si además hubo fills con markout negativo, eso huele a adverse selection.`;
  return "El PnL reciente está prácticamente plano; el foco está más en el posicionamiento y en la calidad del quote que en resultado inmediato.";
}

function describeOrder(order) {
  const markout5 = order.averageMarkout?.[5] ?? NaN;
  const relation = order.bookRelation ?? "unknown";
  return `Último episodio de órdenes: ${order.side.toUpperCase()} ${order.product} ${order.statusLabel} · ${order.type} · relación con el book: ${relation} · markout 5t ${Number.isFinite(markout5) ? fmtSigned(markout5, 2) : "—"}.`;
}

function windowDelta(values, endIdx, width) {
  if (!Array.isArray(values) || !values.length) return NaN;
  const lo = Math.max(0, endIdx - width);
  const start = values[lo - 1] ?? 0;
  const end = values[endIdx] ?? values[values.length - 1] ?? 0;
  return end - start;
}

function mean(values) {
  if (!values.length) return NaN;
  return values.reduce((acc, value) => acc + value, 0) / values.length;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
