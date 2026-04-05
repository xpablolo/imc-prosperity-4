#!/usr/bin/env python3
"""
Generate matplotlib plots from a Monte Carlo run output directory.

Called automatically by montecarlo.py, but can also be run standalone:
    python round_0/tools/mc_plots.py round_0/results/montecarlo/model_v2/<timestamp>/

Generates:
    plots/pnl_distribution.png   — total PnL histogram + normal fit + percentiles
    plots/pnl_by_product.png     — EMERALDS vs TOMATOES distribution side by side
    plots/pnl_paths.png          — PnL path bands across sampled sessions
    plots/metrics_table.png      — summary statistics table
"""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd


# ── Style ──────────────────────────────────────────────────────────────────
DARK_BG   = "#0f1117"
PANEL_BG  = "#1a1d27"
BORDER    = "#2c2f3e"
TEXT_MAIN = "#e8eaf0"
TEXT_DIM  = "#6b7280"
BLUE      = "#3b82f6"
BLUE_LITE = "#93c5fd"
AMBER     = "#f59e0b"
GREEN     = "#10b981"
RED       = "#ef4444"
PURPLE    = "#8b5cf6"

def apply_dark_style(fig, axes=None):
    fig.patch.set_facecolor(DARK_BG)
    if axes:
        for ax in (axes if hasattr(axes, "__iter__") else [axes]):
            ax.set_facecolor(PANEL_BG)
            ax.spines[:].set_color(BORDER)
            ax.tick_params(colors=TEXT_DIM, labelsize=9)
            ax.xaxis.label.set_color(TEXT_DIM)
            ax.yaxis.label.set_color(TEXT_DIM)


# ── Plot 1: PnL distribution ───────────────────────────────────────────────

def plot_pnl_distribution(ax, total_pnl: list[float], stats: dict) -> None:
    arr = np.array(total_pnl)
    bins = min(50, max(20, len(arr) // 10))
    n, edges, patches = ax.hist(arr, bins=bins, color=BLUE, alpha=0.6, edgecolor=BORDER, linewidth=0.4)

    # Normal fit overlay
    mu, sigma = stats["mean"], stats["std"]
    x = np.linspace(arr.min(), arr.max(), 300)
    bin_width = edges[1] - edges[0]
    normal_y = (np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))) * len(arr) * bin_width
    ax.plot(x, normal_y, color=AMBER, linewidth=2, label=f"Normal fit  μ={mu:,.0f}  σ={sigma:,.0f}")

    # Percentile lines
    for label, pct, color in [
        ("P05", stats["p05"], RED),
        ("P50", stats["p50"], TEXT_MAIN),
        ("P95", stats["p95"], GREEN),
    ]:
        ax.axvline(pct, color=color, linestyle="--", linewidth=1.4, alpha=0.9)
        ax.text(pct, ax.get_ylim()[1] * 0.92, f" {label}\n {pct:,.0f}", color=color, fontsize=8.5)

    ax.set_title("Total PnL Distribution", color=TEXT_MAIN, fontsize=13, pad=10)
    ax.set_xlabel("Total PnL (SeaShells)", color=TEXT_DIM)
    ax.set_ylabel("Sessions", color=TEXT_DIM)
    ax.legend(fontsize=9, facecolor=PANEL_BG, edgecolor=BORDER, labelcolor=TEXT_MAIN)

    win_rate = stats["positiveRate"] * 100
    ax.text(0.98, 0.97, f"Win rate: {win_rate:.1f}%", transform=ax.transAxes,
            ha="right", va="top", color=GREEN if win_rate >= 50 else RED, fontsize=10)


# ── Plot 2: PnL by product ─────────────────────────────────────────────────

def plot_by_product(ax_em, ax_to, emerald_pnl: list[float], tomato_pnl: list[float]) -> None:
    for ax, arr, color, label in [
        (ax_em, np.array(emerald_pnl), BLUE, "EMERALDS"),
        (ax_to, np.array(tomato_pnl), GREEN, "TOMATOES"),
    ]:
        bins = min(40, max(15, len(arr) // 10))
        ax.hist(arr, bins=bins, color=color, alpha=0.65, edgecolor=BORDER, linewidth=0.4)
        mu = arr.mean()
        ax.axvline(mu, color=AMBER, linestyle="--", linewidth=1.5)
        ax.text(mu, ax.get_ylim()[1] * 0.88, f"  μ={mu:,.0f}", color=AMBER, fontsize=9)
        ax.set_title(label, color=TEXT_MAIN, fontsize=12, pad=8)
        ax.set_xlabel("PnL (SeaShells)", color=TEXT_DIM)
        ax.set_ylabel("Sessions", color=TEXT_DIM)


# ── Plot 3: PnL path bands ─────────────────────────────────────────────────

def plot_path_bands(ax, band_series: dict, sample_paths: list[dict]) -> None:
    if not band_series:
        ax.text(0.5, 0.5, "No path data\n(increase --sample-sessions)",
                transform=ax.transAxes, ha="center", va="center", color=TEXT_DIM, fontsize=11)
        ax.set_title("PnL Path Bands", color=TEXT_MAIN, fontsize=13, pad=10)
        return

    ts = np.array(band_series["timestamps"])
    mean = np.array(band_series["mean"])
    s1_lo = np.array(band_series["std1Low"])
    s1_hi = np.array(band_series["std1High"])
    s3_lo = np.array(band_series["std3Low"])
    s3_hi = np.array(band_series["std3High"])

    ax.fill_between(ts, s3_lo, s3_hi, alpha=0.12, color=BLUE, label="±3σ")
    ax.fill_between(ts, s1_lo, s1_hi, alpha=0.28, color=BLUE, label="±1σ")
    ax.plot(ts, mean, color=AMBER, linewidth=2, label="Mean")

    # Overlay individual traces
    for path in sample_paths[:8]:
        path_ts = path["total"]["timestamps"]
        path_pnl = path["total"]["mtmPnl"]
        ax.plot(path_ts, path_pnl, color=GREEN, linewidth=0.8, alpha=0.25)

    ax.axhline(0, color=BORDER, linewidth=1)
    ax.set_title("Total PnL Path Bands", color=TEXT_MAIN, fontsize=13, pad=10)
    ax.set_xlabel("Timestamp", color=TEXT_DIM)
    ax.set_ylabel("MTM PnL", color=TEXT_DIM)
    ax.legend(fontsize=9, facecolor=PANEL_BG, edgecolor=BORDER, labelcolor=TEXT_MAIN)


# ── Plot 4: Metrics table ──────────────────────────────────────────────────

def plot_metrics_table(ax, dashboard: dict) -> None:
    ax.axis("off")
    total = dashboard["overall"]["totalPnl"]
    em    = dashboard["overall"]["emeraldPnl"]
    to    = dashboard["overall"]["tomatoPnl"]
    n     = int(total["count"])

    rows = [
        ["Metric", "TOTAL", "EMERALDS", "TOMATOES"],
        ["Sessions", f"{n:,}", "—", "—"],
        ["Mean PnL", f"{total['mean']:,.0f}", f"{em['mean']:,.0f}", f"{to['mean']:,.0f}"],
        ["Median (P50)", f"{total['p50']:,.0f}", f"{em['p50']:,.0f}", f"{to['p50']:,.0f}"],
        ["Std Dev", f"{total['std']:,.0f}", f"{em['std']:,.0f}", f"{to['std']:,.0f}"],
        ["Sharpe-like", f"{total['sharpeLike']:.3f}", f"{em['sharpeLike']:.3f}", f"{to['sharpeLike']:.3f}"],
        ["P05 (VaR)", f"{total['p05']:,.0f}", f"{em['p05']:,.0f}", f"{to['p05']:,.0f}"],
        ["P95", f"{total['p95']:,.0f}", f"{em['p95']:,.0f}", f"{to['p95']:,.0f}"],
        ["Win rate", f"{total['positiveRate']*100:.1f}%", f"{em['positiveRate']*100:.1f}%", f"{to['positiveRate']*100:.1f}%"],
        ["Min", f"{total['min']:,.0f}", f"{em['min']:,.0f}", f"{to['min']:,.0f}"],
        ["Max", f"{total['max']:,.0f}", f"{em['max']:,.0f}", f"{to['max']:,.0f}"],
    ]

    table = ax.table(
        cellText=[r[1:] for r in rows[1:]],
        rowLabels=[r[0] for r in rows[1:]],
        colLabels=rows[0][1:],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.6)

    # Style cells
    for (row, col), cell in table.get_celld().items():
        cell.set_facecolor(PANEL_BG if row % 2 == 0 else DARK_BG)
        cell.set_edgecolor(BORDER)
        cell.set_text_props(color=TEXT_MAIN if row > 0 else AMBER)

    ax.set_title("Summary Statistics", color=TEXT_MAIN, fontsize=13, pad=14)


# ── Main ───────────────────────────────────────────────────────────────────

def main(run_dir: Path) -> None:
    session_csv = run_dir / "session_summary.csv"
    dashboard_json = run_dir / "dashboard.json"

    if not session_csv.exists() or not dashboard_json.exists():
        print(f"Error: missing output files in {run_dir}")
        sys.exit(1)

    df = pd.read_csv(session_csv)
    with dashboard_json.open() as f:
        dashboard = json.load(f)

    total_pnl   = df["total_pnl"].tolist()
    emerald_pnl = df["emerald_pnl"].tolist()
    tomato_pnl  = df["tomato_pnl"].tolist()
    total_stats = dashboard["overall"]["totalPnl"]

    # Load sample paths for band chart
    band_series = {}
    sample_paths = []
    if "bandSeries" in dashboard and dashboard["bandSeries"]:
        total_bands = dashboard["bandSeries"].get("EMERALDS", {}).get("mtmPnl")
        # Use total mtmPnl band if available, else skip
        # Actually build total band from per-product bands
        em_bands = dashboard["bandSeries"].get("EMERALDS", {}).get("mtmPnl", {})
        to_bands = dashboard["bandSeries"].get("TOMATOES", {}).get("mtmPnl", {})
        if em_bands and to_bands and "timestamps" in em_bands:
            ts = em_bands["timestamps"]
            band_series = {
                "timestamps": ts,
                "mean":     [a + b for a, b in zip(em_bands["mean"], to_bands["mean"])],
                "std1Low":  [a + b for a, b in zip(em_bands["std1Low"], to_bands["std1Low"])],
                "std1High": [a + b for a, b in zip(em_bands["std1High"], to_bands["std1High"])],
                "std3Low":  [a + b for a, b in zip(em_bands["std3Low"], to_bands["std3Low"])],
                "std3High": [a + b for a, b in zip(em_bands["std3High"], to_bands["std3High"])],
            }

    # Load sample path traces from sidecar JSON files
    sample_paths_dir = run_dir / "sample_paths"
    if sample_paths_dir.exists():
        for path_file in sorted(sample_paths_dir.glob("*.json"))[:10]:
            with path_file.open() as f:
                sample_paths.append(json.load(f))

    plots_dir = run_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    model_name = run_dir.parent.name
    n_sessions = int(total_stats["count"])
    suptitle = f"{model_name}  •  Monte Carlo  •  {n_sessions:,} sessions"

    # ── Figure 1: PnL distribution ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=DARK_BG)
    apply_dark_style(fig, ax)
    plot_pnl_distribution(ax, total_pnl, total_stats)
    fig.suptitle(suptitle, color=TEXT_MAIN, fontsize=11, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = plots_dir / "pnl_distribution.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.relative_to(run_dir.parent.parent.parent.parent)}")

    # ── Figure 2: by product ──────────────────────────────────────────────
    fig, (ax_em, ax_to) = plt.subplots(1, 2, figsize=(13, 5), facecolor=DARK_BG)
    apply_dark_style(fig, [ax_em, ax_to])
    plot_by_product(ax_em, ax_to, emerald_pnl, tomato_pnl)
    fig.suptitle(suptitle, color=TEXT_MAIN, fontsize=11, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = plots_dir / "pnl_by_product.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.relative_to(run_dir.parent.parent.parent.parent)}")

    # ── Figure 3: path bands ──────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(13, 5.5), facecolor=DARK_BG)
    apply_dark_style(fig, ax)
    plot_path_bands(ax, band_series, sample_paths)
    fig.suptitle(suptitle, color=TEXT_MAIN, fontsize=11, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = plots_dir / "pnl_paths.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.relative_to(run_dir.parent.parent.parent.parent)}")

    # ── Figure 4: metrics table ───────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
    apply_dark_style(fig, ax)
    plot_metrics_table(ax, dashboard)
    fig.suptitle(suptitle, color=TEXT_MAIN, fontsize=11, y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = plots_dir / "metrics_table.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out.relative_to(run_dir.parent.parent.parent.parent)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mc_plots.py <run_dir>")
        sys.exit(1)
    main(Path(sys.argv[1]))
