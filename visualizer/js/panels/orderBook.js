import { subscribe, getState, getReference } from "../store.js";
import { fmtPct, fmtPrice, fmtSigned } from "../format.js";

const HELP = {
  bid: "Bid = mejor precio visible al que el mercado está dispuesto a comprar. Si vos vendés pasivamente, competís en esta cola.",
  ask: "Ask = mejor precio visible al que el mercado está dispuesto a vender. Si vos comprás agresivamente, pagás acá.",
  spread: "Spread = ask - bid. Spreads amplios suelen dar más margen para market making, pero también señalan menor liquidez o más riesgo.",
  mid: "Mid = punto medio entre el mejor bid y el mejor ask. Es una referencia simple, no necesariamente el precio ejecutable.",
  micro: "Microprice = mid sesgado por el volumen visible en ambos lados. Si el ask está más fino, la micro suele quedar por encima del mid y viceversa.",
  wall: "Wall-mid = referencia que incorpora más información del libro visible por niveles. Ayuda a ver dónde está la masa de liquidez.",
  imbalance: "Imbalance = proporción del volumen visible del lado bid frente al total bid+ask. Cerca de 50% = balanceado; muy alto o muy bajo = libro inclinado.",
};

export function mountOrderBook({ bodyEl, titleEl, midSpreadEl }) {
  function render() {
    const state = getState();
    const ref = getReference(state);
    const product = state.selectedProduct ?? ref?.products?.[0] ?? null;
    titleEl.textContent = `Order Book Explorer${product ? ` · ${product}` : ""}`;
    if (!ref || !product) {
      bodyEl.innerHTML = `<div class="book-empty">Load a strategy and pick a product to inspect the book.</div>`;
      midSpreadEl.textContent = "";
      return;
    }

    const ps = ref.series?.[product];
    const tickIdx = state.tickIdx;
    const book = ps?.books?.[tickIdx] ?? { bids: [], asks: [] };
    const bestBid = book.bids?.[0]?.price ?? NaN;
    const bestAsk = book.asks?.[0]?.price ?? NaN;
    const mid = ps?.midPrice?.[tickIdx] ?? NaN;
    const micro = ps?.microPrice?.[tickIdx] ?? NaN;
    const wallMid = ps?.wallMid?.[tickIdx] ?? NaN;
    const imbalance = ps?.imbalance?.[tickIdx] ?? NaN;
    const spread = Number.isFinite(bestBid) && Number.isFinite(bestAsk) ? bestAsk - bestBid : NaN;
    const bidDepth = sum(book.bids?.map((level) => level.volume) ?? []);
    const askDepth = sum(book.asks?.map((level) => level.volume) ?? []);
    const stats = ref.analysis?.productStats?.[product] ?? {};

    midSpreadEl.textContent = [
      Number.isFinite(mid) ? `mid ${fmtPrice(mid)}` : null,
      Number.isFinite(spread) ? `spread ${fmtPrice(spread)}` : null,
      Number.isFinite(imbalance) ? `imb ${fmtPct(imbalance, 0)}` : null,
    ]
      .filter(Boolean)
      .join(" · ");

    const read = describeBook({ spread, micro, mid, wallMid, imbalance, stats, bidDepth, askDepth });
    const recentRows = buildRecentRows(ref, product, tickIdx);
    const ladderRows = buildLadder(book, mid);

    bodyEl.innerHTML = `
      <div class="book-explainer">
        <div class="book-badge ${read.tone}">${escapeHtml(read.badge)}</div>
        <div class="book-explainer-copy">
          <div class="book-explainer-title">Qué está diciendo el libro ahora</div>
          <div class="book-explainer-text">${escapeHtml(read.text)}</div>
        </div>
      </div>

      <div class="book-metrics-grid">
        ${metricCard("Bid", fmtPrice(bestBid), HELP.bid, "bid")}
        ${metricCard("Ask", fmtPrice(bestAsk), HELP.ask, "ask")}
        ${metricCard("Spread", fmtPrice(spread), HELP.spread, spreadTone(spread, stats))}
        ${metricCard("Mid", fmtPrice(mid), HELP.mid)}
        ${metricCard("Micro", fmtPrice(micro), HELP.micro)}
        ${metricCard("Wall mid", fmtPrice(wallMid), HELP.wall)}
        ${metricCard("Imbalance", fmtPct(imbalance, 0), HELP.imbalance, imbalanceTone(imbalance))}
        ${metricCard("Depth", `${fmtSigned(bidDepth, 0).replace("+", "")} / ${fmtSigned(askDepth, 0).replace("+", "")}`, "Volumen visible agregado bid / ask en los niveles disponibles. Es una proxy rápida de liquidez visible.")}
      </div>

      <div class="book-main-grid">
        <div class="book-ladder-card">
          <div class="book-subtitle">Snapshot actual</div>
          <div class="book-subhelp">Ladder por niveles visibles. Verde = bids, rojo = asks. Las barras muestran profundidad relativa en cada lado.</div>
          <div class="book-ladder">
            ${ladderRows}
          </div>
        </div>
        <div class="book-history-card">
          <div class="book-subtitle">Evolución reciente</div>
          <div class="book-subhelp">Últimos ticks con spread, microprice e inclinación del libro. Pensalo como un mini heatmap / tape del book visible.</div>
          <div class="book-history-table">
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">TS</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Spr</th>
                  <th>Micro-mid</th>
                  <th>Depth ribbon</th>
                </tr>
              </thead>
              <tbody>${recentRows}</tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  subscribe(render);
  render();
}

function buildLadder(book, mid) {
  const bids = Array.isArray(book?.bids) ? book.bids : [];
  const asks = Array.isArray(book?.asks) ? book.asks : [];
  const maxVol = Math.max(1, ...bids.map((row) => row.volume), ...asks.map((row) => row.volume));
  const askRows = [...asks]
    .reverse()
    .map((level, idx) => ladderRow({ level, idx: asks.length - idx, side: "ask", maxVol, mid }))
    .join("");
  const bidRows = bids
    .map((level, idx) => ladderRow({ level, idx: idx + 1, side: "bid", maxVol, mid }))
    .join("");
  return `
    ${askRows || `<div class="book-empty-row">No visible asks.</div>`}
    <div class="book-mid-divider strong">
      <span class="num">${fmtPrice(mid)}</span>
      <span>mid</span>
      <span class="right muted">best book snapshot</span>
    </div>
    ${bidRows || `<div class="book-empty-row">No visible bids.</div>`}
  `;
}

function ladderRow({ level, idx, side, maxVol, mid }) {
  const pct = maxVol > 0 ? Math.max(4, (level.volume / maxVol) * 100) : 0;
  const dist = Number.isFinite(mid) ? level.price - mid : NaN;
  return `
    <div class="book-row book-row-${side}">
      <div class="book-bar ${side}" style="width:${pct}%"></div>
      <span class="book-level">L${idx}</span>
      <span class="book-price-${side}">${fmtPrice(level.price)}</span>
      <span class="book-qty">${level.volume}</span>
      <span class="book-distance ${Number.isFinite(dist) ? (dist >= 0 ? "negative" : "positive") : "muted"}">${Number.isFinite(dist) ? fmtSigned(dist, 1) : "—"}</span>
    </div>
  `;
}

function buildRecentRows(ref, product, tickIdx) {
  const ps = ref.series?.[product] ?? {};
  const rows = [];
  const start = Math.max(0, tickIdx - 7);
  for (let i = start; i <= tickIdx; i++) {
    const book = ps.books?.[i] ?? { bids: [], asks: [] };
    const bestBid = book.bids?.[0]?.price ?? NaN;
    const bestAsk = book.asks?.[0]?.price ?? NaN;
    const spread = Number.isFinite(bestBid) && Number.isFinite(bestAsk) ? bestAsk - bestBid : NaN;
    const micro = ps.microPrice?.[i] ?? NaN;
    const mid = ps.midPrice?.[i] ?? NaN;
    const deltaMicro = Number.isFinite(micro) && Number.isFinite(mid) ? micro - mid : NaN;
    rows.push(`
      <tr class="${i === tickIdx ? "ref" : ""}">
        <td class="left num muted">${ref.rawTimestamps?.[i] ?? 0}</td>
        <td class="num positive">${fmtPrice(bestBid)}</td>
        <td class="num negative">${fmtPrice(bestAsk)}</td>
        <td class="num">${fmtPrice(spread)}</td>
        <td class="num ${Number.isFinite(deltaMicro) ? (deltaMicro >= 0 ? "positive" : "negative") : "muted"}">${Number.isFinite(deltaMicro) ? fmtSigned(deltaMicro, 2) : "—"}</td>
        <td class="left">${depthRibbon(book)}</td>
      </tr>
    `);
  }
  return rows.join("") || `<tr><td class="empty" colspan="6">No recent snapshots.</td></tr>`;
}

function depthRibbon(book) {
  const bids = Array.isArray(book?.bids) ? book.bids : [];
  const asks = Array.isArray(book?.asks) ? book.asks : [];
  const levels = [asks[2], asks[1], asks[0], bids[0], bids[1], bids[2]].filter(Boolean);
  const maxVol = Math.max(1, ...levels.map((level) => level.volume));
  const askCells = [asks[2], asks[1], asks[0]].map((level) => ribbonCell(level, maxVol, "ask"));
  const bidCells = [bids[0], bids[1], bids[2]].map((level) => ribbonCell(level, maxVol, "bid"));
  return `<span class="depth-ribbon">${askCells.join("")}<span class="depth-ribbon-mid"></span>${bidCells.join("")}</span>`;
}

function ribbonCell(level, maxVol, side) {
  if (!level) return `<span class="depth-cell empty"></span>`;
  const alpha = Math.max(0.18, Math.min(0.95, level.volume / maxVol));
  return `<span class="depth-cell ${side}" style="opacity:${alpha}" title="${side.toUpperCase()} ${fmtPrice(level.price)} · qty ${level.volume}"></span>`;
}

function describeBook({ spread, micro, mid, wallMid, imbalance, stats, bidDepth, askDepth }) {
  const spreadState = spreadTone(spread, stats);
  const imbalanceState = imbalanceTone(imbalance);
  const microShift = Number.isFinite(micro) && Number.isFinite(mid) ? micro - mid : NaN;
  const depthBias = bidDepth > askDepth ? "bid-heavy" : askDepth > bidDepth ? "ask-heavy" : "balanced";
  const parts = [];
  if (spreadState === "warn") parts.push("El spread está más ancho que lo habitual para este producto.");
  else if (spreadState === "good") parts.push("El spread está comprimido: menos edge bruto, pero más liquidez visible.");
  else parts.push("El spread está en una zona media, sin desbalance extremo.");

  if (Number.isFinite(microShift)) {
    if (microShift > 0) parts.push("La microprice está por encima del mid: el lado ask parece relativamente más fino / vulnerable.");
    else if (microShift < 0) parts.push("La microprice está por debajo del mid: el lado bid parece relativamente más fino / vulnerable.");
  }

  if (imbalanceState === "good") parts.push("Hay más volumen visible del lado bid; si estás comprando, ojo con pagar de más si eso es solo pared transitoria.");
  else if (imbalanceState === "risk") parts.push("El libro está cargado al lado ask; vender agresivo en este contexto puede ser caro si el book sigue cayendo.");
  else parts.push(`La liquidez visible está bastante balanceada (${depthBias}).`);

  const badge = spreadState === "warn" || imbalanceState === "risk" ? "riesgoso" : spreadState === "good" ? "liquidez alta" : "neutral";
  const tone = spreadState === "warn" || imbalanceState === "risk" ? "risk" : spreadState === "good" ? "good" : "neutral";
  return {
    badge,
    tone,
    text: parts.join(" "),
  };
}

function metricCard(label, value, help, tone = "") {
  return `
    <div class="metric-card ${tone}">
      <div class="metric-card-label">${escapeHtml(label)} <span class="term-help" title="${escapeHtml(help)}">?</span></div>
      <div class="metric-card-value num">${escapeHtml(String(value))}</div>
    </div>
  `;
}

function spreadTone(spread, stats) {
  if (!Number.isFinite(spread)) return "";
  if (Number.isFinite(stats?.spreadQ75) && spread >= stats.spreadQ75) return "warn";
  if (Number.isFinite(stats?.spreadQ25) && spread <= stats.spreadQ25) return "good";
  return "";
}

function imbalanceTone(imbalance) {
  if (!Number.isFinite(imbalance)) return "";
  if (imbalance >= 0.58) return "good";
  if (imbalance <= 0.42) return "risk";
  return "";
}

function sum(values) {
  return (values ?? []).reduce((acc, value) => acc + (Number.isFinite(value) ? value : 0), 0);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
