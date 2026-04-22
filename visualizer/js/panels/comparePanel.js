import { subscribe, getState, getReference } from "../store.js";
import { compareStrategies } from "../analysis.js";
import { fmtInt, fmtPct, fmtSigned } from "../format.js";

export function mountComparePanel({ bodyEl }) {
  const local = {
    compareId: null,
    startIdx: 0,
    endIdx: null,
    initialized: false,
  };

  bodyEl.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches("[data-compare-id]")) {
      local.compareId = target.value || null;
      render();
    }
    if (target.matches("[data-window-start]")) {
      local.startIdx = Number(target.value);
      render();
    }
    if (target.matches("[data-window-end]")) {
      local.endIdx = Number(target.value);
      render();
    }
  });

  bodyEl.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.matches("[data-window-current]")) {
      const state = getState();
      const ref = getReference(state);
      const center = state.tickIdx;
      local.startIdx = Math.max(0, center - 250);
      local.endIdx = Math.min((ref?.timestamps?.length ?? 1) - 1, center + 250);
      render();
    }
    if (target.matches("[data-window-full]")) {
      const ref = getReference(getState());
      local.startIdx = 0;
      local.endIdx = Math.max(0, (ref?.timestamps?.length ?? 1) - 1);
      render();
    }
  });

  function render() {
    const state = getState();
    const ref = getReference(state);
    const others = state.strategies.filter((strategy) => strategy.id !== ref?.id);
    if (!ref) {
      bodyEl.innerHTML = `<div class="logs-empty">Load at least two strategies to compare them properly.</div>`;
      return;
    }
    if (!local.initialized) {
      local.startIdx = Math.max(0, state.tickIdx - 250);
      local.endIdx = Math.min((ref.timestamps?.length ?? 1) - 1, state.tickIdx + 250);
      local.compareId = others[0]?.id ?? null;
      local.initialized = true;
    }
    if (!others.length) {
      bodyEl.innerHTML = `<div class="logs-empty">Load a second strategy to unlock side-by-side diagnostics and “why different?”.</div>`;
      return;
    }
    if (!others.some((strategy) => strategy.id === local.compareId)) {
      local.compareId = others[0]?.id ?? null;
    }
    const other = others.find((strategy) => strategy.id === local.compareId) ?? others[0];
    const startIdx = clamp(local.startIdx, 0, (ref.timestamps?.length ?? 1) - 1);
    const endIdx = clamp(local.endIdx ?? (ref.timestamps?.length ?? 1) - 1, 0, (ref.timestamps?.length ?? 1) - 1);
    const comparison = compareStrategies(ref, other, { startIdx, endIdx });

    bodyEl.innerHTML = `
      <div class="section-stack">
        <div class="compare-toolbar">
          <label class="control-inline">vs
            <select class="input" data-compare-id>
              ${others
                .map(
                  (strategy) => `<option value="${strategy.id}" ${strategy.id === other.id ? "selected" : ""}>${escapeHtml(strategy.name)}</option>`
                )
                .join("")}
            </select>
          </label>
          <label class="control-inline">start tick <input class="input tiny-num" type="number" data-window-start value="${startIdx}" min="0" max="${Math.max(0, (ref.timestamps?.length ?? 1) - 1)}" /></label>
          <label class="control-inline">end tick <input class="input tiny-num" type="number" data-window-end value="${endIdx}" min="0" max="${Math.max(0, (ref.timestamps?.length ?? 1) - 1)}" /></label>
          <button class="btn icon" data-window-current title="Center on current tick">◎</button>
          <button class="btn icon" data-window-full title="Use full run">↔</button>
        </div>

        <div class="info-banner neutral">
          <strong>Episode compare.</strong>
          Ventana actual: tick ${fmtInt(comparison.window.startIdx)}-${fmtInt(comparison.window.endIdx)} · TS ${fmtInt(comparison.window.startRawTs)}-${fmtInt(comparison.window.endRawTs)}.
        </div>

        <div class="compare-cards-grid">
          ${comparison.metrics
            .slice(0, 8)
            .map(
              (metric) => `
                <article class="compare-card ${metric.referenceBetter ? "good" : "warn"}">
                  <div class="compare-card-label">${escapeHtml(metric.label)}</div>
                  <div class="compare-card-values">
                    <span>${escapeHtml(ref.name)}: <strong class="num">${fmt(metric.ref)}</strong></span>
                    <span>${escapeHtml(other.name)}: <strong class="num">${fmt(metric.other)}</strong></span>
                  </div>
                  <div class="compare-card-delta num ${metric.delta >= 0 ? "positive" : "negative"}">${fmtSigned(metric.delta, 2)}</div>
                </article>
              `
            )
            .join("")}
        </div>

        <div class="split-section two">
          <section>
            <div class="section-title">Why different?</div>
            <ul class="compare-bullets">
              ${comparison.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}
            </ul>
          </section>
          <section>
            <div class="section-title">By product</div>
            <table class="data compact static-table">
              <thead>
                <tr>
                  <th class="left">Product</th>
                  <th>${escapeHtml(ref.name)}</th>
                  <th>${escapeHtml(other.name)}</th>
                  <th>Gap</th>
                </tr>
              </thead>
              <tbody>
                ${comparison.byProduct
                  .map(
                    (row) => `
                      <tr>
                        <td class="left">${escapeHtml(row.product)}</td>
                        <td class="num ${tone(row.ref.pnlDelta)}">${fmtSigned(row.ref.pnlDelta, 0)}</td>
                        <td class="num ${tone(row.other.pnlDelta)}">${fmtSigned(row.other.pnlDelta, 0)}</td>
                        <td class="num ${tone(row.pnlGap)}">${fmtSigned(row.pnlGap, 0)}</td>
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

  subscribe((state, prev) => {
    if (state.referenceId !== prev.referenceId || state.strategies.length !== prev.strategies.length) {
      local.initialized = false;
    }
    render();
  });
  render();
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, Number.isFinite(value) ? value : min));
}

function fmt(value) {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return fmtSigned(value, 0);
  if (Math.abs(value) <= 1 && value !== 0) return fmtSigned(value, 3);
  return fmtSigned(value, 2);
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
