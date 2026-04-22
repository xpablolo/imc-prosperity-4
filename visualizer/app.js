import {
  subscribe,
  getState,
  replaceStrategies,
} from "./js/store.js";
import { mountRail } from "./js/panels/rail.js";
import { mountTopBar } from "./js/panels/topBar.js";
import { mountKpi } from "./js/panels/kpi.js";
import { mountPnlChart } from "./js/panels/pnlChart.js";
import { mountDrawdownChart } from "./js/panels/drawdownChart.js";
import { mountPriceChart } from "./js/panels/priceChart.js";
import { mountPositionChart } from "./js/panels/positionChart.js";
import { mountSummary } from "./js/panels/summary.js";
import { mountOrderBook } from "./js/panels/orderBook.js";
import { mountWhatHappened } from "./js/panels/whatHappened.js";
import { mountOrderLifecycle } from "./js/panels/orderLifecycle.js";
import { mountExecutionPanel } from "./js/panels/executionPanel.js";
import { mountComparePanel } from "./js/panels/comparePanel.js";
import { mountDiagnostics } from "./js/panels/diagnostics.js";
import { mountLogs } from "./js/panels/logs.js";
import { showAboutModal } from "./js/panels/about.js";
import { loadStrategies } from "./js/persistence.js";
import { prepareStrategy } from "./js/strategyPrep.js";

function $(id) {
  return document.getElementById(id);
}

function openAbout() {
  showAboutModal($("modal-root"));
}

function applyTheme(theme) {
  document.body.classList.toggle("theme-dark", theme === "dark");
  document.body.classList.toggle("theme-light", theme === "light");
}

async function hydrate() {
  if (!getState().prefs.persistEnabled) return;
  try {
    const list = await loadStrategies();
    if (list.length > 0) replaceStrategies(list.map(prepareStrategy));
  } catch {
    /* ignore */
  }
}

async function main() {
  applyTheme(getState().prefs.theme);
  subscribe((state, prev) => {
    if (state.prefs.theme !== prev.prefs?.theme) applyTheme(state.prefs.theme);
  });

  mountRail({
    railEl: $("rail"),
    railExpandEl: $("rail-expand"),
    dropzoneEl: $("dropzone"),
    fileInputEl: $("file-input"),
    listEl: $("rail-list"),
    workspaceListEl: $("workspace-list"),
    workspaceSearchEl: $("workspace-search"),
    workspaceRefreshEl: $("workspace-refresh"),
    workspaceStatusEl: $("workspace-status"),
    progressEl: $("parse-progress"),
    progressMessage: $("parse-progress-message"),
    progressPct: $("parse-progress-pct"),
    progressFill: $("parse-progress-fill"),
    persistToggle: $("persist-toggle"),
    collapseBtn: $("rail-collapse"),
    onShowAbout: openAbout,
  });
  $("open-about").addEventListener("click", openAbout);

  mountTopBar({
    scrubberEl: $("scrubber"),
    tickCurEl: $("tick-cur"),
    tickMaxEl: $("tick-max"),
    tickTsEl: $("tick-ts"),
    tickDayPrefixEl: $("tick-day-prefix"),
    playBtn: $("play"),
    stepBackBtn: $("step-back"),
    stepFwdBtn: $("step-fwd"),
    speedGroupEl: $("speed-group"),
    productSelect: $("product-select"),
    themeBtn: $("theme-toggle"),
    aboutBtn: $("open-about-top"),
    onShowAbout: openAbout,
  });

  mountKpi($("kpi-grid"));

  mountPnlChart({
    canvasEl: $("chart-pnl"),
    emptyEl: $("chart-pnl-empty"),
    legendEl: $("pnl-legend"),
    normCheck: $("pnl-norm"),
    diffCheck: $("pnl-diff"),
    sampledCheck: $("pnl-sampled"),
    exportBtn: $("pnl-export"),
    resetZoomBtn: $("pnl-reset-zoom"),
  });

  mountSummary({
    bodyEl: $("summary-body"),
    exportBtn: $("summary-export"),
  });

  mountPriceChart({
    canvasEl: $("chart-price"),
    emptyEl: $("chart-price-empty"),
    titleEl: $("price-title"),
    legendEl: $("price-legend"),
    levelsCheck: $("price-levels"),
    midCheck: $("price-mid"),
    microCheck: $("price-micro"),
    wallMidCheck: $("price-wallmid"),
    buysCheck: $("price-buys"),
    sellsCheck: $("price-sells"),
    botsCheck: $("price-bots"),
    overlayCheck: $("price-overlay"),
    joinGapsCheck: $("price-join-gaps"),
    resetZoomBtn: $("price-reset-zoom"),
  });

  mountOrderBook({
    bodyEl: $("book-body"),
    titleEl: $("book-title"),
    midSpreadEl: $("book-mid-spread"),
  });

  mountWhatHappened({
    bodyEl: $("pressure-body"),
    titleEl: $("pressure-title"),
    valueEl: $("pressure-value"),
  });

  mountPositionChart({
    canvasEl: $("chart-position"),
    emptyEl: $("chart-position-empty"),
    titleEl: $("position-title"),
    legendEl: $("position-legend"),
    limitInput: $("position-limit"),
    resetZoomBtn: $("position-reset-zoom"),
  });

  mountDrawdownChart({
    canvasEl: $("chart-drawdown"),
    emptyEl: $("chart-drawdown-empty"),
    legendEl: $("drawdown-legend"),
    resetZoomBtn: $("drawdown-reset-zoom"),
  });

  mountComparePanel({
    bodyEl: $("compare-body"),
  });

  mountExecutionPanel({
    bodyEl: $("execution-body"),
  });

  mountOrderLifecycle({
    bodyEl: $("fills-body"),
    titleEl: $("fills-title"),
    showAllInput: $("fills-all"),
    currentOnlyInput: $("fills-current"),
  });

  mountLogs({
    bodyEl: $("logs-body"),
    tsEl: $("logs-ts"),
    tabsEl: $("panel-logs").querySelector(".tabs"),
  });

  mountDiagnostics({
    bodyEl: $("diagnostics-body"),
  });

  await hydrate();
}

main().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<pre style="color:#f87171;padding:12px;font-family:monospace">Boot error: ${String(err)}</pre>`
  );
});
