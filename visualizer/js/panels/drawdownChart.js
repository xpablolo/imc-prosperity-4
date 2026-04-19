import { subscribe, getState, getReference, setTickIdx } from "../store.js";
import { lttb } from "../downsample.js";
import { createChart } from "../chart.js";
import { computeDrawdown } from "../strategyPrep.js";

const TARGET_POINTS = 1200;

export function mountDrawdownChart({
  canvasEl,
  emptyEl,
  legendEl,
  resetZoomBtn,
}) {
  let chart = null;
  let lastKey = null;
  let currentLegend = [];

  resetZoomBtn.addEventListener("click", () => chart?.resetXView());

  function ensureChart() {
    if (chart) return;
    chart = createChart(canvasEl, {
      onSeek: (xValue) => {
        const state = getState();
        const ref = getReference(state);
        if (!ref) return;
        const ts = ref.timestamps;
        let lo = 0;
        let hi = ts.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >>> 1;
          if (ts[mid] < xValue) lo = mid + 1;
          else hi = mid;
        }
        setTickIdx(lo);
      },
      onHover: renderLegend,
    });
  }

  function drawdownSeriesFor(strat, product) {
    if (product && strat.drawdownByProduct?.[product]) {
      return strat.drawdownByProduct[product];
    }
    if (Array.isArray(strat.drawdown)) return strat.drawdown;
    return computeDrawdown(strat.totalPnl ?? []);
  }

  function computeModel(state, ref) {
    const product = state.selectedProduct ?? null;
    const series = [];
    const add = (strat, width) => {
      const xs = strat.timestamps;
      const ys = drawdownSeriesFor(strat, product);
      const sampled = state.prefs.showSampled ? lttb(xs, ys, TARGET_POINTS) : { xs, ys };
      series.push({
        name: strat.id === ref.id ? `${strat.name} (ref)` : strat.name,
        color: strat.color,
        width,
        xs: sampled.xs,
        ys: sampled.ys,
      });
    };
    add(ref, 2.1);
    for (const strat of state.strategies) {
      if (strat.id === ref.id || !state.comparingIds.has(strat.id)) continue;
      add(strat, 1.2);
    }
    currentLegend = series.map((item) => ({ name: item.name, color: item.color }));
    return {
      xFormat: (v) => Math.round(v).toLocaleString(),
      yFormat: (v) => v.toFixed(0),
      series,
    };
  }

  function renderLegend(values) {
    if (!currentLegend.length) {
      legendEl.innerHTML = "";
      return;
    }
    legendEl.innerHTML = currentLegend
      .map((entry, idx) => {
        const value = values ? values[idx] : null;
        const text =
          value == null
            ? "—"
            : value === 0
              ? "0"
              : `−${Math.abs(value).toFixed(0)}`;
        return `<span class="legend-row">
          <span class="legend-swatch" style="background:${entry.color}"></span>
          <span class="legend-name">${escapeHtml(entry.name)}</span>
          <span class="legend-value ${value == null ? "muted" : value < 0 ? "negative" : ""}">${text}</span>
        </span>`;
      })
      .join("");
  }

  function render() {
    const state = getState();
    const ref = getReference(state);
    if (!ref) {
      if (chart) {
        chart.destroy();
        chart = null;
      }
      currentLegend = [];
      legendEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      canvasEl.classList.add("hidden");
      return;
    }

    emptyEl.classList.add("hidden");
    canvasEl.classList.remove("hidden");
    ensureChart();

    const key = [
      ref.id,
      state.strategies.length,
      Array.from(state.comparingIds).join(","),
      state.selectedProduct ?? "",
      state.prefs.showSampled,
    ].join("|");

    if (key !== lastKey) {
      chart.setData(computeModel(state, ref));
      lastKey = key;
      renderLegend(null);
    }
    chart.setCursorX(ref.timestamps[state.tickIdx] ?? 0);
  }

  subscribe(render);
  render();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
