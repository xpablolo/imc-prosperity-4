import {
  subscribe,
  getState,
  getReference,
  setPrefs,
  setTickIdx,
} from "../store.js";
import { lttb } from "../downsample.js";
import { createChart } from "../chart.js";
import { downloadCanvasPng } from "../exporters.js";

const TARGET_POINTS = 1500;

export function mountPnlChart({
  canvasEl,
  emptyEl,
  legendEl,
  normCheck,
  diffCheck,
  sampledCheck,
  exportBtn,
  resetZoomBtn,
}) {
  let chart = null;
  let lastKey = null;
  let currentSeriesForLegend = [];

  normCheck.addEventListener("change", () =>
    setPrefs({ normalizedX: normCheck.checked })
  );
  diffCheck.addEventListener("change", () =>
    setPrefs({ diffMode: diffCheck.checked })
  );
  sampledCheck.addEventListener("change", () =>
    setPrefs({ showSampled: sampledCheck.checked })
  );
  exportBtn.addEventListener("click", () => {
    downloadCanvasPng(canvasEl, "pnl-performance.png");
  });
  resetZoomBtn.addEventListener("click", () => chart?.resetXView());

  function ensureChart() {
    if (chart) return;
    chart = createChart(canvasEl, {
      onSeek: (xValue) => {
        const state = getState();
        const ref = getReference(state);
        if (!ref) return;
        const len = ref.timestamps.length;
        if (len < 2) return;
        if (state.prefs.normalizedX) {
          setTickIdx(Math.round(xValue * (len - 1)));
        } else {
          // nearest tickKey
          let lo = 0;
          let hi = len - 1;
          while (lo < hi) {
            const mid = (lo + hi) >>> 1;
            if (ref.timestamps[mid] < xValue) lo = mid + 1;
            else hi = mid;
          }
          setTickIdx(lo);
        }
      },
      onHover: (values, cursor) => {
        renderLegend(values, cursor);
      },
    });
  }

  function renderLegend(values, cursor) {
    if (!currentSeriesForLegend.length) {
      legendEl.innerHTML = "";
      return;
    }
    legendEl.innerHTML = currentSeriesForLegend
      .map((s, i) => {
        const v = values ? values[i] : null;
        const cls =
          v === null ? "muted" : v >= 0 ? "positive" : "negative";
        const text =
          v === null
            ? "—"
            : (v >= 0 ? "+" : "") +
              (Math.abs(v) >= 1000
                ? (v / 1000).toFixed(1) + "k"
                : v.toFixed(0));
        return `<span class="legend-row">
          <span class="legend-swatch" style="background:${s.color}"></span>
          <span class="legend-name">${escapeHtml(s.name)}</span>
          <span class="legend-value ${cls}">${text}</span>
        </span>`;
      })
      .join("");
    void cursor;
  }

  function pnlSeriesFor(strat, selectedProduct) {
    if (!selectedProduct || !strat.series[selectedProduct]) {
      return strat.totalPnl;
    }
    const src = strat.series[selectedProduct].pnl;
    const out = new Array(src.length);
    let last = 0;
    for (let i = 0; i < src.length; i++) {
      if (Number.isFinite(src[i])) last = src[i];
      out[i] = last;
    }
    return out;
  }

  function computeModel(state) {
    const ref = getReference(state);
    if (!ref) return null;
    const { prefs, strategies, comparingIds, selectedProduct } = state;
    const compareList = strategies.filter(
      (s) => comparingIds.has(s.id) && s.id !== ref.id
    );
    const refXs = ref.timestamps;
    const refYs = pnlSeriesFor(ref, selectedProduct);

    function project(strat) {
      const xsBase = prefs.normalizedX
        ? strat.timestamps.map((_, i) =>
            strat.timestamps.length > 1 ? i / (strat.timestamps.length - 1) : 0
          )
        : strat.timestamps;
      let ys = pnlSeriesFor(strat, selectedProduct);
      if (prefs.diffMode && strat.id !== ref.id) {
        const out = new Array(xsBase.length);
        if (prefs.normalizedX) {
          for (let i = 0; i < xsBase.length; i++) {
            const refIdx = Math.min(
              refXs.length - 1,
              Math.round(xsBase[i] * (refXs.length - 1))
            );
            out[i] = ys[i] - refYs[refIdx];
          }
        } else {
          let j = 0;
          for (let i = 0; i < xsBase.length; i++) {
            while (j + 1 < refXs.length && refXs[j + 1] <= xsBase[i]) j++;
            out[i] = ys[i] - refYs[j];
          }
        }
        ys = out;
      }
      return prefs.showSampled ? lttb(xsBase, ys, TARGET_POINTS) : { xs: xsBase, ys };
    }

    const series = [
      { name: ref.name + " (ref)", color: ref.color, width: 2.2, ...project(ref) },
    ];
    for (const s of compareList) {
      series.push({ name: s.name, color: s.color, width: 1.2, ...project(s) });
    }
    currentSeriesForLegend = series.map((s) => ({ name: s.name, color: s.color }));

    return {
      xFormat: (v) =>
        prefs.normalizedX
          ? (v * 100).toFixed(1) + "%"
          : Math.round(v).toLocaleString(),
      yFormat: (v) =>
        Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + "k" : v.toFixed(0),
      series,
    };
  }

  function render() {
    const state = getState();
    const ref = getReference(state);

    normCheck.checked = state.prefs.normalizedX;
    diffCheck.checked = state.prefs.diffMode;
    sampledCheck.checked = state.prefs.showSampled;

    if (!ref) {
      if (chart) {
        chart.destroy();
        chart = null;
      }
      currentSeriesForLegend = [];
      legendEl.innerHTML = "";
      emptyEl.classList.remove("hidden");
      canvasEl.classList.add("hidden");
      return;
    }
    emptyEl.classList.add("hidden");
    canvasEl.classList.remove("hidden");
    ensureChart();

    const key =
      state.strategies.length +
      "|" +
      state.referenceId +
      "|" +
      Array.from(state.comparingIds).join(",") +
      "|" +
      state.prefs.diffMode +
      "|" +
      state.prefs.normalizedX +
      "|" +
      state.prefs.showSampled +
      "|" +
      (state.selectedProduct ?? "");
    if (key !== lastKey) {
      chart.setData(computeModel(state));
      lastKey = key;
      renderLegend(null, null);
    }

    const cursorX = state.prefs.normalizedX
      ? ref.timestamps.length > 1
        ? state.tickIdx / (ref.timestamps.length - 1)
        : 0
      : ref.timestamps[state.tickIdx] ?? 0;
    chart.setCursorX(cursorX);
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
