import {
  subscribe,
  getState,
  addStrategy,
  removeStrategy,
  renameStrategy,
  recolorStrategy,
  setReference,
  toggleComparing,
  setParseProgress,
  setPrefs,
  setRailCollapsed,
} from "../store.js";
import { pickColor } from "../colors.js";
import { uid } from "../uid.js";
import { parseLogText } from "../parserClient.js";
import { loadDemoLog } from "../demoLog.js";
import { saveStrategy, clearAll } from "../persistence.js";
import { fmtInt } from "../format.js";
import { prepareStrategy } from "../strategyPrep.js";
import {
  listWorkspaceRuns,
  fetchRunSourceText,
  fetchNormalizedRun,
} from "../api.js";

let editingId = null;
let workspaceRuns = [];
let workspaceLoading = false;
let workspaceError = null;
let workspaceAvailable = false;
let workspaceQuery = "";

export function mountRail({
  railEl,
  railExpandEl,
  dropzoneEl,
  fileInputEl,
  listEl,
  workspaceListEl,
  workspaceSearchEl,
  workspaceRefreshEl,
  workspaceStatusEl,
  progressEl,
  progressMessage,
  progressPct,
  progressFill,
  persistToggle,
  collapseBtn,
  onShowAbout,
}) {
  async function addPreparedStrategy(strat) {
    const prepared = prepareStrategy(strat);
    addStrategy(prepared);
    if (getState().prefs.persistEnabled) {
      saveStrategy(prepared).catch(() => {});
    }
  }

  async function handleFiles(files) {
    const arr = Array.from(files);
    const batchColors = getState().strategies.map((s) => s.color);
    for (const file of arr) {
      const id = uid();
      try {
        setParseProgress({ id, pct: 0, message: `Reading ${file.name}…` });
        const text = await file.text();
        setParseProgress({ id, pct: 5, message: `Parsing ${file.name}…` });
        const color = pickColor(batchColors);
        batchColors.push(color);
        const strat = await parseLogText(
          text,
          {
            id,
            name: file.name.replace(/\.(log|json)$/i, ""),
            color,
            filename: file.name,
          },
          {
            onProgress: (pct, message) => setParseProgress({ id, pct, message }),
          }
        );
        await addPreparedStrategy(strat);
      } catch (e) {
        alert(`Failed to parse ${file.name}: ${e.message}`);
      } finally {
        setParseProgress(null);
      }
    }
  }

  async function doLoadDemo() {
    const id = uid("demo");
    try {
      setParseProgress({ id, pct: 0, message: "Loading demo…" });
      const text = await loadDemoLog();
      const strat = await parseLogText(
        text,
        {
          id,
          name: "Demo — IMC Day 0 Sample",
          color: pickColor(getState().strategies.map((s) => s.color)),
          filename: "demo.log",
        },
        {
          onProgress: (pct, message) => setParseProgress({ id, pct, message }),
        }
      );
      await addPreparedStrategy(strat);
    } catch (e) {
      alert(`Demo load failed: ${e.message}`);
    } finally {
      setParseProgress(null);
    }
  }

  async function refreshWorkspace(force = false) {
    workspaceLoading = true;
    workspaceError = null;
    renderWorkspace();
    try {
      workspaceRuns = await listWorkspaceRuns({ refresh: force });
      workspaceAvailable = true;
    } catch (e) {
      workspaceAvailable = false;
      workspaceError =
        "No encontré la API local. Arrancá el dashboard con `python3 visualizer/server.py`.";
      console.warn(e);
    } finally {
      workspaceLoading = false;
      renderWorkspace();
    }
  }

  async function loadWorkspaceRun(runId) {
    const existing = getState().strategies.find((item) => item.id === runId);
    if (existing) {
      setReference(existing.id);
      return;
    }

    const run = workspaceRuns.find((item) => item.id === runId);
    if (!run) return;

    try {
      setParseProgress({ id: run.id, pct: 0, message: `Loading ${run.name}…` });
      const color = pickColor(getState().strategies.map((s) => s.color));

      if (run.loadMode === "source-text") {
        const text = await fetchRunSourceText(run.id);
        const strat = await parseLogText(
          text,
          {
            id: run.id,
            name: run.name,
            color,
            filename: run.path,
          },
          {
            onProgress: (pct, message) =>
              setParseProgress({ id: run.id, pct, message }),
          }
        );
        await addPreparedStrategy({ ...strat, id: run.id, color, filename: run.path });
      } else {
        setParseProgress({ id: run.id, pct: 35, message: `Normalizing ${run.name}…` });
        const normalized = await fetchNormalizedRun(run.id);
        await addPreparedStrategy({
          ...normalized,
          id: run.id,
          name: run.name,
          color,
          filename: run.path,
        });
      }
    } catch (e) {
      alert(`Failed to load ${run.name}: ${e.message}`);
    } finally {
      setParseProgress(null);
      renderWorkspace();
    }
  }

  dropzoneEl.addEventListener("click", () => fileInputEl.click());
  dropzoneEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzoneEl.classList.add("active");
  });
  dropzoneEl.addEventListener("dragleave", () =>
    dropzoneEl.classList.remove("active")
  );
  dropzoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzoneEl.classList.remove("active");
    if (e.dataTransfer?.files?.length) handleFiles(e.dataTransfer.files);
  });
  fileInputEl.addEventListener("change", () => {
    if (fileInputEl.files?.length) handleFiles(fileInputEl.files);
    fileInputEl.value = "";
  });

  persistToggle.addEventListener("change", (e) => {
    const on = e.target.checked;
    setPrefs({ persistEnabled: on });
    if (on) {
      for (const s of getState().strategies) saveStrategy(s).catch(() => {});
    } else {
      clearAll().catch(() => {});
    }
  });

  collapseBtn.addEventListener("click", () => setRailCollapsed(true));
  railExpandEl.addEventListener("click", () => setRailCollapsed(false));
  workspaceRefreshEl.addEventListener("click", () => refreshWorkspace(true));
  workspaceSearchEl.addEventListener("input", (e) => {
    workspaceQuery = e.target.value.trim().toLowerCase();
    renderWorkspace();
  });

  workspaceListEl.addEventListener("click", (e) => {
    const target = e.target.closest("[data-run-id]");
    if (!target) return;
    const runId = target.dataset.runId;
    loadWorkspaceRun(runId);
  });

  listEl.addEventListener("click", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    const item = target.closest("[data-strat-id]");
    if (!item) return;
    const id = item.getAttribute("data-strat-id");
    const action = target.getAttribute("data-action");
    if (action === "remove") {
      const s = getState().strategies.find((x) => x.id === id);
      if (s && confirm(`Remove ${s.name}?`)) removeStrategy(id);
    } else if (action === "name") {
      editingId = id;
      renderLoaded();
      const input = listEl.querySelector(`[data-strat-id="${id}"] .strat-rename`);
      input?.focus();
      input?.select();
    } else if (action === "ref-radio" || action === "name-click") {
      setReference(id);
    } else if (action === "cmp") {
      toggleComparing(id);
    }
  });

  listEl.addEventListener("change", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLInputElement)) return;
    const item = target.closest("[data-strat-id]");
    if (!item) return;
    const id = item.getAttribute("data-strat-id");
    if (target.getAttribute("data-action") === "ref-radio") {
      setReference(id);
    } else if (target.getAttribute("data-action") === "cmp") {
      toggleComparing(id);
    } else if (target.getAttribute("data-action") === "color") {
      recolorStrategy(id, target.value);
    }
  });

  listEl.addEventListener("keydown", (e) => {
    if (!(e.target instanceof HTMLInputElement)) return;
    if (!e.target.classList.contains("strat-rename")) return;
    if (e.key === "Enter") e.target.blur();
    else if (e.key === "Escape") {
      editingId = null;
      renderLoaded();
    }
  });

  listEl.addEventListener("focusout", (e) => {
    if (!(e.target instanceof HTMLInputElement)) return;
    if (!e.target.classList.contains("strat-rename")) return;
    const item = e.target.closest("[data-strat-id]");
    if (!item) return;
    const id = item.getAttribute("data-strat-id");
    const newName = e.target.value.trim();
    if (newName) renameStrategy(id, newName);
    editingId = null;
    renderLoaded();
  });

  function renderWorkspace() {
    const loadedIds = new Set(getState().strategies.map((s) => s.id));
    if (workspaceLoading) {
      workspaceStatusEl.innerHTML = `<span class="muted tiny">Scanning workspace runs…</span>`;
      workspaceListEl.innerHTML = "";
      return;
    }
    if (!workspaceAvailable) {
      workspaceStatusEl.innerHTML = `<div class="rail-empty">${escapeHtml(
        workspaceError ??
          "Workspace scan unavailable. You can still drag files manually."
      )}</div>`;
      workspaceListEl.innerHTML = "";
      return;
    }

    const filtered = workspaceRuns.filter((run) => {
      if (!workspaceQuery) return true;
      const hay = `${run.name} ${run.path} ${run.kind} ${run.round ?? ""}`.toLowerCase();
      return hay.includes(workspaceQuery);
    });

    workspaceStatusEl.innerHTML = `<span class="muted tiny">${filtered.length} local runs detected</span>`;
    if (filtered.length === 0) {
      workspaceListEl.innerHTML = `<div class="rail-empty">No local runs match your search.</div>`;
      return;
    }

    workspaceListEl.innerHTML = filtered
      .slice(0, 80)
      .map((run) => {
        const loaded = loadedIds.has(run.id);
        const badge = run.kind === "backtest" ? "CSV" : run.kind === "replay-log" ? "REPLAY" : "IMC";
        return `
          <button class="workspace-item ${loaded ? "loaded" : ""}" data-run-id="${run.id}">
            <div class="workspace-item-top">
              <span class="workspace-name">${escapeHtml(run.name)}</span>
              <span class="badge-pill">${badge}</span>
            </div>
            <div class="workspace-meta">${escapeHtml(run.path)}</div>
            <div class="workspace-meta workspace-meta-row">
              ${run.round ? `<span>${escapeHtml(run.round)}</span>` : "<span>workspace</span>"}
              <span>·</span>
              <span>${loaded ? "loaded" : run.loadMode === "normalized" ? "normalized" : "parse on load"}</span>
            </div>
          </button>
        `;
      })
      .join("");
  }

  function renderLoaded() {
    const { strategies, referenceId, comparingIds } = getState();
    if (strategies.length === 0) {
      listEl.innerHTML = `
        <div class="rail-empty">No runs loaded yet.</div>
        <button class="btn full" id="rail-load-demo-inline">Load demo log</button>
      `;
      listEl.querySelector("#rail-load-demo-inline")?.addEventListener(
        "click",
        doLoadDemo
      );
      return;
    }
    const items = strategies
      .map((s) => {
        const isRef = s.id === referenceId;
        const isCmp = comparingIds.has(s.id);
        const pnl = s.summary.totalPnl;
        const pnlStr = (pnl >= 0 ? "+" : "") + Math.round(pnl).toLocaleString();
        const pnlClass = pnl >= 0 ? "positive" : "negative";
        const isEditing = editingId === s.id;
        const sourceKind = s.source?.kind ?? "log";
        const warningCount = s.warnings?.length ?? 0;
        return `
          <div class="strat-item ${isRef ? "ref" : ""}" data-strat-id="${s.id}">
            <label class="strat-swatch" style="background:${s.color}" title="Recolor">
              <input type="color" value="${s.color}" data-action="color" />
            </label>
            <div class="strat-body">
              ${
                isEditing
                  ? `<input class="strat-rename" value="${escapeAttr(s.name)}" autofocus />`
                  : `<button class="strat-name" data-action="name-click" title="${escapeAttr(s.name)}&#10;${escapeAttr(s.filename ?? "")}">${escapeHtml(s.name)}</button>`
              }
              <div class="strat-meta">
                <span class="num">${fmtInt(s.timestamps.length)} ticks</span>
                <span>·</span>
                <span>${s.products.length} sym</span>
                <span>·</span>
                <span>${escapeHtml(sourceKind)}</span>
                <span>·</span>
                <span class="num ${pnlClass}">${pnlStr}</span>
                ${warningCount ? `<span>·</span><span class="negative">${warningCount} warn</span>` : ""}
              </div>
              <div class="strat-controls">
                <label><input type="radio" name="reference" data-action="ref-radio" ${isRef ? "checked" : ""}/> ref</label>
                <label><input type="checkbox" data-action="cmp" ${isCmp ? "checked" : ""}/> compare</label>
                <button data-action="name" class="strat-remove" title="Rename">✎</button>
                <button data-action="remove" class="strat-remove" title="Remove">×</button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");
    listEl.innerHTML =
      items +
      `<button class="btn full" id="rail-add-demo" style="margin-top:8px">+ Add demo</button>`;
    listEl.querySelector("#rail-add-demo")?.addEventListener("click", doLoadDemo);
  }

  function renderProgress() {
    const { parseProgress } = getState();
    if (!parseProgress) {
      progressEl.classList.add("hidden");
      return;
    }
    progressEl.classList.remove("hidden");
    progressMessage.textContent = parseProgress.message;
    progressPct.textContent = `${parseProgress.pct.toFixed(0)}%`;
    progressFill.style.width = `${parseProgress.pct}%`;
  }

  function renderToggleState() {
    const { prefs, railCollapsed } = getState();
    persistToggle.checked = prefs.persistEnabled;
    const app = document.querySelector(".app");
    app.classList.toggle("rail-collapsed", railCollapsed);
    railExpandEl.classList.toggle("hidden", !railCollapsed);
  }

  let lastSnap = {};
  subscribe((state) => {
    const snap = {
      strategies: state.strategies,
      referenceId: state.referenceId,
      comparingIds: state.comparingIds,
      parseProgress: state.parseProgress,
      persistEnabled: state.prefs.persistEnabled,
      railCollapsed: state.railCollapsed,
      editingId,
    };
    if (
      snap.strategies !== lastSnap.strategies ||
      snap.referenceId !== lastSnap.referenceId ||
      snap.comparingIds !== lastSnap.comparingIds ||
      snap.editingId !== lastSnap.editingId
    ) {
      renderLoaded();
      renderWorkspace();
    }
    if (snap.parseProgress !== lastSnap.parseProgress) renderProgress();
    if (
      snap.persistEnabled !== lastSnap.persistEnabled ||
      snap.railCollapsed !== lastSnap.railCollapsed
    ) {
      renderToggleState();
    }
    lastSnap = snap;
  });

  renderLoaded();
  renderWorkspace();
  renderProgress();
  renderToggleState();
  refreshWorkspace(false);

  void railEl;
  void onShowAbout;
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
