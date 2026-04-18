"""
IMC Prosperity Round 2 — Iteration 3 Analysis
Custom mixture: user-defined type weights + sensitivity.
Run standalone: python3 iter3_analysis.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from pathlib import Path
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))

from manual_round2_utils import (
    research, scale, compute_rs_table,
    speed_multiplier, SPEED_HIGH, SPEED_LOW, SPEED_RANGE, TOTAL_BUDGET,
    verify_ranking_examples,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE   = Path(__file__).parent
OUT    = BASE / "results" / "iteration3"
PLOTS  = OUT / "plots"
CSVS   = OUT / "csv"
PLOTS.mkdir(parents=True, exist_ok=True)
CSVS.mkdir(parents=True, exist_ok=True)

# ─── Style ────────────────────────────────────────────────────────────────────
PALETTE = ["#2196F3","#4CAF50","#FF9800","#E91E63","#9C27B0","#00BCD4","#FF5722"]
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "#F8F9FA",
    "axes.grid": True, "grid.alpha": 0.3, "grid.color": "#CCCCCC",
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": "sans-serif", "font.size": 11,
    "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.labelsize": 11,
})

# ─── Constants ────────────────────────────────────────────────────────────────
SEED      = 42
N_PLAYERS = 50
N_SIMS    = 15_000
V_GRID    = list(range(0, 101, 1))   # every integer v

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER TYPE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

# User-specified mixture weights
TYPE_WEIGHTS = {
    "nash_like":    0.20,
    "focal_points": 0.10,
    "just_above":   0.20,
    "ai_similar":   0.30,
    "naive_ev":     0.10,
    "speed_race":   0.05,
    "random_pure":  0.05,
}
assert abs(sum(TYPE_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1"

# ── Type 2: Focal points ──
FOCAL_VALUES  = [0,  10,  20,  25,  30,  33,  34,  40,  50,  67, 100]
FOCAL_WEIGHTS_RAW = [3,  8,   10,  10,  10,  22,  10,   8,  12,   4,   3]
FOCAL_WEIGHTS_RAW = np.array(FOCAL_WEIGHTS_RAW, dtype=float)
FOCAL_WEIGHTS_RAW /= FOCAL_WEIGHTS_RAW.sum()

# ── Type 3: Just-above focal points ──
JUSTABOVE_VALUES  = [11, 21, 26, 31, 34, 35, 36, 41, 51]
JUSTABOVE_WEIGHTS_RAW = [8,  9,  8, 14, 12, 12, 12, 16,  9]
JUSTABOVE_WEIGHTS_RAW = np.array(JUSTABOVE_WEIGHTS_RAW, dtype=float)
JUSTABOVE_WEIGHTS_RAW /= JUSTABOVE_WEIGHTS_RAW.sum()

# ── Type 4: AI / similar — three versions ──
AI_VERSIONS = {
    "base":         {"kind": "normal", "mu": 37.0, "sigma": 6.0, "lo": 30, "hi": 46},
    "concentrated": {"kind": "discrete",
                     "values": [34, 35, 36, 40, 42],
                     "weights": [0.22, 0.18, 0.22, 0.22, 0.16]},
    "higher":       {"kind": "normal", "mu": 41.0, "sigma": 7.0, "lo": 33, "hi": 55},
}
DEFAULT_AI = "base"


def _sample_type(type_name: str, rng: np.random.Generator,
                 n: int, ai_version: str = DEFAULT_AI) -> np.ndarray:
    if type_name == "nash_like":
        raw = rng.normal(32.0, 10.0, size=n)
        return np.clip(raw, 0, 100).round().astype(int)

    elif type_name == "focal_points":
        return rng.choice(FOCAL_VALUES, size=n, p=FOCAL_WEIGHTS_RAW)

    elif type_name == "just_above":
        return rng.choice(JUSTABOVE_VALUES, size=n, p=JUSTABOVE_WEIGHTS_RAW)

    elif type_name == "ai_similar":
        cfg = AI_VERSIONS[ai_version]
        if cfg["kind"] == "normal":
            raw = rng.normal(cfg["mu"], cfg["sigma"], size=n)
            return np.clip(raw, cfg["lo"], cfg["hi"]).round().astype(int)
        else:
            w = np.array(cfg["weights"], dtype=float); w /= w.sum()
            return rng.choice(cfg["values"], size=n, p=w)

    elif type_name == "naive_ev":
        raw = rng.normal(50.0, 18.0, size=n)
        return np.clip(raw, 0, 100).round().astype(int)

    elif type_name == "speed_race":
        raw = rng.normal(70.0, 12.0, size=n)
        return np.clip(raw, 0, 100).round().astype(int)

    elif type_name == "random_pure":
        return rng.integers(0, 101, size=n)

    else:
        raise ValueError(f"Unknown type: {type_name}")


def sample_mixture(n_total: int, rng: np.random.Generator,
                   weights: dict = TYPE_WEIGHTS,
                   ai_version: str = DEFAULT_AI) -> np.ndarray:
    """Sample n_total speeds from the mixture."""
    names  = list(weights.keys())
    probs  = np.array(list(weights.values()), dtype=float)
    probs /= probs.sum()

    type_idx = rng.choice(len(names), size=n_total, p=probs)
    speeds = np.zeros(n_total, dtype=int)
    for i, name in enumerate(names):
        mask = type_idx == i
        if mask.any():
            speeds[mask] = _sample_type(name, rng, int(mask.sum()), ai_version)
    return speeds


def compute_mixture_pmf(n_samples: int = 500_000, seed: int = 0,
                        weights: dict = TYPE_WEIGHTS,
                        ai_version: str = DEFAULT_AI) -> pd.Series:
    rng = np.random.default_rng(seed)
    samples = sample_mixture(n_samples, rng, weights, ai_version)
    counts = np.bincount(samples, minlength=101)
    pmf = pd.Series(counts / counts.sum(), index=range(101))
    return pmf


# ─────────────────────────────────────────────────────────────────────────────
# VECTORISED MC ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def mc_custom_mixture(
    rs_table: pd.DataFrame,
    weights: dict = TYPE_WEIGHTS,
    ai_version: str = DEFAULT_AI,
    N: int = N_PLAYERS,
    n_sims: int = N_SIMS,
    seed: int = SEED,
    v_candidates: list[int] = None,
) -> pd.DataFrame:
    """Vectorised MC: sample (n_sims × N-1) others, compute PnL for each v."""
    if v_candidates is None:
        v_candidates = V_GRID

    rng   = np.random.default_rng(seed)
    # Sample ALL others at once → shape (n_sims, N-1)
    flat  = sample_mixture(n_sims * (N - 1), rng, weights, ai_version)
    others = flat.reshape(n_sims, N - 1)

    rs_idx = rs_table.set_index("v")
    rows   = []
    for v in v_candidates:
        gv        = float(rs_idx.loc[v, "gross_value"])
        n_higher  = (others > v).sum(axis=1)               # (n_sims,)
        rank      = n_higher + 1
        mult      = SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE
        pnl       = gv * mult - TOTAL_BUDGET
        rows.append(dict(
            v=v,
            mean_pnl=float(pnl.mean()),
            std_pnl=float(pnl.std()),
            p10=float(np.percentile(pnl, 10)),
            p25=float(np.percentile(pnl, 25)),
            p50=float(np.percentile(pnl, 50)),
            p75=float(np.percentile(pnl, 75)),
            p90=float(np.percentile(pnl, 90)),
            mean_mult=float(mult.mean()),
            std_mult=float(mult.std()),
            mean_rank=float(rank.mean()),
        ))
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# REGRET
# ─────────────────────────────────────────────────────────────────────────────

def add_regret(ev_df: pd.DataFrame) -> pd.DataFrame:
    df = ev_df.copy()
    best = df["mean_pnl"].max()
    df["regret"]    = best - df["mean_pnl"]
    df["regret_p10"] = df["p10"].max() - df["p10"]   # regret on downside
    return df


# ─────────────────────────────────────────────────────────────────────────────
# PLOT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def savefig(name: str, fig):
    p = PLOTS / name
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved {p.name}")


def fmt_k(x, _=None):  return f"{x/1e3:.0f}k"
def fmt_0(x, _=None):  return f"{x:,.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ITERATION 3 — Custom Mixture Analysis")
    print("=" * 60)

    rs_table = compute_rs_table()
    assert verify_ranking_examples(), "Ranking engine broken!"
    rs_table.to_csv(CSVS / "optimal_rs_by_speed_iter3.csv", index=False)
    print("RS table ok. Ranking verified.\n")

    # ── 1. Type PMFs ──────────────────────────────────────────────────────────
    print("Building type PMFs...")
    rng0 = np.random.default_rng(0)
    N_PMF = 200_000
    type_pmfs = {}
    for name in TYPE_WEIGHTS:
        samps = _sample_type(name, rng0, N_PMF, DEFAULT_AI)
        cnt = np.bincount(samps, minlength=101)
        type_pmfs[name] = cnt / cnt.sum()

    mixture_pmf = compute_mixture_pmf(500_000)
    mixture_pmf.to_csv(CSVS / "mixture_total_pmf.csv", header=["pmf"])
    print("  mixture PMF saved\n")

    # Save type PMF table
    pmf_df = pd.DataFrame(type_pmfs, index=range(101))
    pmf_df.index.name = "v"
    pmf_df["mixture"] = mixture_pmf.values
    pmf_df.to_csv(CSVS / "type_component_pmf.csv")
    print("  type PMF CSV saved\n")

    # ── 2. PMF Plots ──────────────────────────────────────────────────────────
    print("Plotting PMFs...")
    _plot_type_pmfs(type_pmfs, mixture_pmf)
    _plot_mixture_breakdown(type_pmfs, mixture_pmf)

    # ── 3. Main MC ────────────────────────────────────────────────────────────
    print(f"\nRunning main MC (N={N_PLAYERS}, n_sims={N_SIMS:,})...")
    ev_main = mc_custom_mixture(rs_table, ai_version=DEFAULT_AI)
    ev_main = add_regret(ev_main)
    ev_main.to_csv(CSVS / "ev_by_speed_iter3.csv", index=False)
    best_v = int(ev_main.loc[ev_main["mean_pnl"].idxmax(), "v"])
    print(f"  best v = {best_v}")
    regret_df = ev_main[["v","regret","regret_p10"]].copy()
    regret_df.to_csv(CSVS / "regret_by_speed_iter3.csv", index=False)

    # ── 4. EV & Regret Plots ──────────────────────────────────────────────────
    print("\nPlotting EV & regret...")
    _plot_ev_main(ev_main, rs_table, mixture_pmf, best_v)
    _plot_regret(ev_main, best_v)
    _plot_multiplier_dists(rs_table)
    _plot_combined_dashboard(ev_main, mixture_pmf, rs_table, best_v)

    # ── 5. Sensitivity ────────────────────────────────────────────────────────
    print("\nSensitivity analysis...")
    sens_rows = _run_sensitivity(rs_table)
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(CSVS / "sensitivity_summary_iter3.csv", index=False)
    _plot_sensitivity(sens_df)

    # ── 6. Final Recommendation ───────────────────────────────────────────────
    rec = _build_recommendation(ev_main, rs_table, sens_df)
    _print_recommendation(rec)
    rec["df"].to_csv(CSVS / "final_recommendation_iter3.csv", index=False)

    print("\nAll done. Files in:", OUT)


# ─────────────────────────────────────────────────────────────────────────────
# PLOT FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _plot_type_pmfs(type_pmfs, mixture_pmf):
    """Individual type PMFs + comparison overlay."""
    type_labels = {
        "nash_like":    "Nash-like (20%)",
        "focal_points": "Focal pts (10%)",
        "just_above":   "Just-above (20%)",
        "ai_similar":   "AI similar (30%)",
        "naive_ev":     "Naive EV (10%)",
        "speed_race":   "Speed-race (5%)",
        "random_pure":  "Random (5%)",
    }
    v = np.arange(101)

    # Panel 1: individual PMFs (2×4 grid, last for mixture)
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    axes_flat = axes.flatten()
    for ax, (name, pmf) in zip(axes_flat[:7], type_pmfs.items()):
        ax.bar(v, pmf, width=1.0, color=PALETTE[list(type_pmfs.keys()).index(name) % len(PALETTE)],
               alpha=0.8, edgecolor="none")
        ax.set_title(type_labels[name])
        ax.set_xlabel("Speed v"); ax.set_xlim(-2, 102)
        mu_val = (v * pmf).sum()
        ax.axvline(mu_val, color="black", lw=1.5, linestyle="--", label=f"μ={mu_val:.1f}")
        ax.legend(fontsize=8)
    # Last panel: mixture
    ax = axes_flat[7]
    ax.bar(v, mixture_pmf.values, width=1.0, color="#607D8B", alpha=0.8, edgecolor="none")
    mu_mix = (v * mixture_pmf.values).sum()
    ax.axvline(mu_mix, color="black", lw=2, linestyle="--", label=f"μ={mu_mix:.1f}")
    ax.set_title("TOTAL MIXTURE", fontweight="bold")
    ax.set_xlabel("Speed v"); ax.set_xlim(-2, 102)
    ax.legend(fontsize=8)
    plt.suptitle("Speed Distribution by Player Type + Total Mixture", fontsize=13, y=1.01)
    plt.tight_layout()
    savefig("01_type_pmfs_individual.png", fig)

    # Panel 2: overlay zoom [15, 55]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    ax = axes[0]
    for i, (name, pmf) in enumerate(type_pmfs.items()):
        w = TYPE_WEIGHTS[name]
        ax.plot(v, pmf * w, color=PALETTE[i % len(PALETTE)], lw=2,
                label=f"{type_labels[name]}", alpha=0.85)
    ax.bar(v, mixture_pmf.values, width=1.0, alpha=0.2, color="#607D8B", label="Mixture total")
    ax.set_xlim(-1, 101); ax.set_xlabel("Speed v"); ax.set_ylabel("Weight × PMF")
    ax.set_title("Weighted type contributions to mixture")
    ax.legend(fontsize=8, ncol=2)

    ax = axes[1]
    for i, (name, pmf) in enumerate(type_pmfs.items()):
        w = TYPE_WEIGHTS[name]
        mask = (v >= 15) & (v <= 55)
        ax.plot(v[mask], pmf[mask] * w, color=PALETTE[i % len(PALETTE)],
                lw=2, label=type_labels[name], alpha=0.85)
    ax.bar(v[(v>=15)&(v<=55)], mixture_pmf.values[(v>=15)&(v<=55)],
           width=1.0, alpha=0.25, color="#607D8B")
    for fp in [33, 34, 35, 36, 40, 41]:
        ax.axvline(fp, color="black", lw=0.7, linestyle=":", alpha=0.5)
    ax.set_xlim(14, 56); ax.set_xlabel("Speed v"); ax.set_ylabel("Weight × PMF")
    ax.set_title("Zoom v ∈ [15, 55] — focal + just-above + AI zone")
    ax.legend(fontsize=8)
    plt.tight_layout()
    savefig("02_type_pmfs_overlay.png", fig)


def _plot_mixture_breakdown(type_pmfs, mixture_pmf):
    """Mixture total PMF with CDF, annotated focal points."""
    v = np.arange(101)
    cdf = np.cumsum(mixture_pmf.values)
    mu_mix = (v * mixture_pmf.values).sum()

    # Key focal / just-above values to annotate
    focal_annot = {33: "33\n(equal-split)", 34: "34", 40: "40\n(AI)", 50: "50", 41: "41"}

    fig = plt.figure(figsize=(15, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35)

    # Top-left: full PMF
    ax = fig.add_subplot(gs[0, 0])
    ax.bar(v, mixture_pmf.values * 100, width=1.0, color="#607D8B", alpha=0.8, edgecolor="none")
    ax.axvline(mu_mix, color="red", lw=2, linestyle="--", label=f"μ={mu_mix:.1f}")
    for fp in [33, 40, 50]:
        ax.axvline(fp, color=PALETTE[3], lw=1.2, linestyle=":", alpha=0.7)
    ax.set_xlabel("Speed v"); ax.set_ylabel("PMF (%)")
    ax.set_title("Total Mixture PMF"); ax.legend(fontsize=9); ax.set_xlim(-1, 101)

    # Top-right: CDF
    ax = fig.add_subplot(gs[0, 1])
    ax.plot(v, cdf * 100, color="#2196F3", lw=2.5)
    ax.fill_between(v, 0, cdf * 100, alpha=0.1, color="#2196F3")
    for pct, col in [(25, "#4CAF50"), (50, "red"), (75, "#FF9800")]:
        v_pct = v[np.searchsorted(cdf, pct/100)]
        ax.axhline(pct, color=col, lw=1, linestyle="--", alpha=0.7)
        ax.axvline(v_pct, color=col, lw=1, linestyle="--", alpha=0.7, label=f"p{pct}={v_pct}")
    ax.set_xlabel("Speed v"); ax.set_ylabel("CDF (%)")
    ax.set_title("Total Mixture CDF"); ax.legend(fontsize=9); ax.set_xlim(-1, 101)

    # Bottom-left: zoom [20, 50]
    ax = fig.add_subplot(gs[1, 0])
    mask = (v >= 20) & (v <= 50)
    ax.bar(v[mask], mixture_pmf.values[mask] * 100, width=1.0,
           color="#607D8B", alpha=0.8, edgecolor="none")
    for fp, label in focal_annot.items():
        if 20 <= fp <= 50:
            ax.axvline(fp, color=PALETTE[3], lw=1.5, linestyle=":", alpha=0.7)
            ax.text(fp + 0.3, mixture_pmf.values[fp] * 100 + 0.05,
                    label, fontsize=8, color=PALETTE[3], ha="left")
    ax.set_xlabel("Speed v"); ax.set_ylabel("PMF (%)")
    ax.set_title("Zoom v ∈ [20, 50]"); ax.set_xlim(19, 51)

    # Bottom-right: stacked contribution by type
    ax = fig.add_subplot(gs[1, 1])
    bottom = np.zeros(101)
    for i, (name, pmf) in enumerate(type_pmfs.items()):
        w = TYPE_WEIGHTS[name]
        contrib = pmf * w
        mask = (v >= 20) & (v <= 50)
        ax.bar(v[mask], contrib[mask] * 100, width=1.0, bottom=bottom[mask],
               color=PALETTE[i % len(PALETTE)], alpha=0.85, edgecolor="none",
               label=f"{name} ({w:.0%})")
        bottom[mask] += contrib[mask] * 100
    ax.set_xlabel("Speed v"); ax.set_ylabel("Stacked PMF (%)")
    ax.set_title("Stacked Contribution by Type (zoom [20,50])")
    ax.legend(fontsize=8, ncol=2); ax.set_xlim(19, 51)

    plt.suptitle("Total Mixture Distribution Analysis", fontsize=14, y=1.02)
    savefig("03_mixture_pmf_full.png", fig)


def _plot_ev_main(ev_df, rs_table, mixture_pmf, best_v):
    """EV curves with uncertainty bands."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    v = ev_df["v"].values
    # Full range
    ax = axes[0]
    ax.fill_between(v, ev_df["p10"] / 1e3, ev_df["p90"] / 1e3,
                    alpha=0.12, color=PALETTE[0], label="p10–p90")
    ax.fill_between(v, ev_df["p25"] / 1e3, ev_df["p75"] / 1e3,
                    alpha=0.22, color=PALETTE[0], label="p25–p75")
    ax.plot(v, ev_df["mean_pnl"] / 1e3, color=PALETTE[0], lw=2.5, label="E[PnL]")
    ax.plot(v, ev_df["p50"] / 1e3, color=PALETTE[0], lw=1.2, linestyle="--",
            alpha=0.7, label="median")
    ax.axvline(best_v, color="black", lw=2, linestyle="-",
               label=f"best v={best_v}")
    ax.axhline(0, color="gray", lw=0.8, linestyle=":")
    ax.set_xlabel("Speed v"); ax.set_ylabel("PnL (k XIRECs)")
    ax.set_title("E[PnL(v)] — Custom Mixture (full range)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    # Zoom [20, 55]
    ax = axes[1]
    mask = (v >= 20) & (v <= 55)
    ax.fill_between(v[mask], ev_df["p10"].values[mask] / 1e3,
                    ev_df["p90"].values[mask] / 1e3,
                    alpha=0.12, color=PALETTE[0])
    ax.fill_between(v[mask], ev_df["p25"].values[mask] / 1e3,
                    ev_df["p75"].values[mask] / 1e3,
                    alpha=0.22, color=PALETTE[0])
    ax.plot(v[mask], ev_df["mean_pnl"].values[mask] / 1e3,
            color=PALETTE[0], lw=2.5, label="E[PnL]")
    ax.axvline(best_v, color="black", lw=2, label=f"best v={best_v}")
    for fp in [33, 34, 40, 41]:
        ax.axvline(fp, color="gray", lw=1, linestyle=":", alpha=0.6)
    ax.axhline(0, color="gray", lw=0.8, linestyle=":")
    ax.set_xlabel("Speed v"); ax.set_ylabel("PnL (k XIRECs)")
    ax.set_title("Zoom v ∈ [20, 55]")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9); ax.set_xlim(19, 56)

    plt.suptitle(f"Expected PnL(v) — Custom Mixture (N={N_PLAYERS}, {N_SIMS:,} sims)",
                 fontsize=13, y=1.02)
    plt.tight_layout()
    savefig("04_ev_main.png", fig)


def _plot_regret(ev_df, best_v):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    v = ev_df["v"].values

    ax = axes[0]
    ax.bar(v, ev_df["regret"] / 1e3, width=1.0, color=PALETTE[3], alpha=0.75, edgecolor="none")
    ax.fill_between(v, 0, ev_df["regret_p10"] / 1e3, alpha=0.2, color=PALETTE[3])
    ax.axvline(best_v, color="black", lw=2, linestyle="--", label=f"best v={best_v}")
    ax.set_xlabel("Speed v"); ax.set_ylabel("Regret (k XIRECs)")
    ax.set_title("Regret = E[PnL(v*)] - E[PnL(v)]")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    ax = axes[1]
    mask = (v >= 20) & (v <= 55)
    ax.bar(v[mask], ev_df["regret"].values[mask] / 1e3, width=1.0,
           color=PALETTE[3], alpha=0.75, edgecolor="none")
    ax.axvline(best_v, color="black", lw=2, linestyle="--", label=f"best v={best_v}")
    for fp in [33, 34, 40, 41]:
        ax.axvline(fp, color="gray", lw=1, linestyle=":", alpha=0.6)
    ax.set_xlabel("Speed v"); ax.set_ylabel("Regret (k)")
    ax.set_title("Regret Zoom v ∈ [20, 55]")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9); ax.set_xlim(19, 56)

    plt.tight_layout()
    savefig("05_regret.png", fig)


def _plot_multiplier_dists(rs_table):
    """Multiplier distribution at several v candidates."""
    v_show = [30, 34, 36, 40, 44, 50]
    rng = np.random.default_rng(SEED)
    n_diag = 20_000
    flat = sample_mixture(n_diag * (N_PLAYERS - 1), rng)
    others = flat.reshape(n_diag, N_PLAYERS - 1)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    rs_idx = rs_table.set_index("v")
    for ax, v in zip(axes.flatten(), v_show):
        gv   = float(rs_idx.loc[v, "gross_value"])
        n_hi = (others > v).sum(axis=1)
        rank = n_hi + 1
        mult = SPEED_HIGH - (rank - 1) / (N_PLAYERS - 1) * SPEED_RANGE
        pnl  = gv * mult - TOTAL_BUDGET

        c = PALETTE[v_show.index(v) % len(PALETTE)]
        unique_m, cnt = np.unique(mult.round(4), return_counts=True)
        ax.bar(unique_m, cnt / cnt.sum(), width=0.012, color=c, alpha=0.8, edgecolor="none")
        ax.axvline(mult.mean(), color="black", lw=1.5, linestyle="--",
                   label=f"E[mult]={mult.mean():.3f}")
        ax.axvline(0.5, color="gray", lw=1, linestyle=":", alpha=0.6)
        ax.set_title(f"v={v}  (E[PnL]={pnl.mean()/1e3:.0f}k)")
        ax.set_xlabel("Multiplier"); ax.set_xlim(0.05, 0.95)
        ax.legend(fontsize=8)

    plt.suptitle(f"Speed Multiplier Distribution by v — Custom Mixture (N={N_PLAYERS})",
                 fontsize=13, y=1.02)
    plt.tight_layout()
    savefig("06_multiplier_distributions.png", fig)


def _plot_combined_dashboard(ev_df, mixture_pmf, rs_table, best_v):
    """4-panel dashboard: speed dist, EV, rs-split, regret."""
    v_arr = np.arange(101)
    rs_v  = rs_table["v"].values

    fig = plt.figure(figsize=(17, 11))
    gs  = GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    # Panel 1: Speed distribution of others (mixture PMF)
    ax = fig.add_subplot(gs[0, 0])
    ax.bar(v_arr, mixture_pmf.values * 100, width=1.0, color="#78909C",
           alpha=0.8, edgecolor="none")
    for fp in [33, 34, 40, 41]:
        ax.axvline(fp, color=PALETTE[3], lw=1.5, linestyle=":", alpha=0.7)
    ax.axvline(best_v, color="black", lw=2, linestyle="-",
               label=f"Your v*={best_v}")
    mu_mix = (v_arr * mixture_pmf.values).sum()
    ax.axvline(mu_mix, color="red", lw=1.5, linestyle="--", label=f"field μ={mu_mix:.1f}")
    ax.set_xlabel("Speed v"); ax.set_ylabel("PMF (%)")
    ax.set_title("Field Speed Distribution (mixture)")
    ax.legend(fontsize=9); ax.set_xlim(-1, 101)

    # Panel 2: EV with uncertainty
    ax = fig.add_subplot(gs[0, 1])
    v = ev_df["v"].values
    ax.fill_between(v, ev_df["p10"] / 1e3, ev_df["p90"] / 1e3,
                    alpha=0.12, color=PALETTE[0])
    ax.fill_between(v, ev_df["p25"] / 1e3, ev_df["p75"] / 1e3,
                    alpha=0.22, color=PALETTE[0])
    ax.plot(v, ev_df["mean_pnl"] / 1e3, color=PALETTE[0], lw=2.5, label="E[PnL]")
    ax.axvline(best_v, color="black", lw=2, label=f"v*={best_v}")
    for fp in [33, 34, 40, 41]:
        ax.axvline(fp, color="gray", lw=1, linestyle=":", alpha=0.5)
    ax.axhline(0, color="gray", lw=0.8, linestyle=":")
    ax.set_xlabel("Speed v"); ax.set_ylabel("PnL (k)")
    ax.set_title("E[PnL(v)] — zoom [20, 55]")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9); ax.set_xlim(19, 56)

    # Panel 3: r*(v), s*(v)
    ax = fig.add_subplot(gs[1, 0])
    ax.stackplot(rs_v, rs_table["r_star"].values, rs_table["s_star"].values,
                 colors=[PALETTE[1], PALETTE[0]], alpha=0.8, labels=["r* Research", "s* Scale"])
    ax.axvline(best_v, color="black", lw=2, linestyle="--", label=f"v*={best_v}")
    ax.set_xlabel("Speed v"); ax.set_ylabel("Allocation (%)")
    ax.set_title("Optimal r*(v) / s*(v)")
    ax.legend(fontsize=9)

    # Panel 4: Regret (zoom)
    ax = fig.add_subplot(gs[1, 1])
    mask = (v >= 20) & (v <= 55)
    ax.fill_between(v[mask], 0, ev_df["regret"].values[mask] / 1e3,
                    alpha=0.25, color=PALETTE[3])
    ax.plot(v[mask], ev_df["regret"].values[mask] / 1e3,
            color=PALETTE[3], lw=2.5, label="Regret")
    ax.axvline(best_v, color="black", lw=2, label=f"v*={best_v}")
    for fp in [33, 34, 40, 41]:
        ax.axvline(fp, color="gray", lw=1, linestyle=":", alpha=0.5)
    ax.set_xlabel("Speed v"); ax.set_ylabel("Regret (k)")
    ax.set_title("Regret zoom [20, 55]")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9); ax.set_xlim(19, 56); ax.set_ylim(bottom=0)

    plt.suptitle(f"Strategy Dashboard — Custom Mixture (N={N_PLAYERS})",
                 fontsize=14, fontweight="bold", y=1.02)
    savefig("07_dashboard.png", fig)


# ─────────────────────────────────────────────────────────────────────────────
# SENSITIVITY
# ─────────────────────────────────────────────────────────────────────────────

def _run_sensitivity(rs_table) -> list[dict]:
    rows = []
    v_cands = list(range(20, 56, 1))   # fine grid in zone of interest

    def run_case(label, weights, ai_v=DEFAULT_AI, N=N_PLAYERS, seed=SEED):
        df = mc_custom_mixture(rs_table, weights, ai_v, N, N_SIMS//3, seed, v_cands)
        df = add_regret(df)
        best = df.loc[df["mean_pnl"].idxmax()]
        reg_at_40 = float(df[df["v"]==40]["regret"].values[0]) if 40 in df["v"].values else np.nan
        rows.append(dict(
            label=label, best_v=int(best["v"]),
            best_ev=float(best["mean_pnl"]),
            regret_at_40=reg_at_40,
            ai_version=ai_v, N=N,
        ))
        print(f"  {label:<45} best_v={int(best['v']):>3}  EV={best['mean_pnl']:>10,.0f}")

    print("Sensitivity: N...")
    for N_val in [20, 35, 50, 75, 100]:
        run_case(f"N={N_val}", TYPE_WEIGHTS, DEFAULT_AI, N_val)

    print("Sensitivity: AI version...")
    for ai_v in ["base", "concentrated", "higher"]:
        run_case(f"AI={ai_v}", TYPE_WEIGHTS, ai_v)

    print("Sensitivity: AI weight...")
    for ai_w in [0.15, 0.20, 0.30, 0.40, 0.50]:
        w = dict(TYPE_WEIGHTS)
        delta = ai_w - w["ai_similar"]
        w["ai_similar"] = ai_w
        # absorb delta from nash_like (keep others stable)
        w["nash_like"] = max(0.05, w["nash_like"] - delta)
        total = sum(w.values())
        w = {k: v/total for k, v in w.items()}
        run_case(f"ai_weight={ai_w:.0%}", w)

    print("Sensitivity: just-above weight...")
    for ja_w in [0.10, 0.15, 0.20, 0.25, 0.30]:
        w = dict(TYPE_WEIGHTS)
        delta = ja_w - w["just_above"]
        w["just_above"] = ja_w
        w["nash_like"] = max(0.05, w["nash_like"] - delta)
        total = sum(w.values())
        w = {k: v/total for k, v in w.items()}
        run_case(f"just_above_weight={ja_w:.0%}", w)

    print("Sensitivity: focal-point weight...")
    for fp_w in [0.05, 0.10, 0.15, 0.20]:
        w = dict(TYPE_WEIGHTS)
        delta = fp_w - w["focal_points"]
        w["focal_points"] = fp_w
        w["nash_like"] = max(0.05, w["nash_like"] - delta)
        total = sum(w.values())
        w = {k: v/total for k, v in w.items()}
        run_case(f"focal_weight={fp_w:.0%}", w)

    return rows


def _plot_sensitivity(sens_df):
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    def _bar(ax, mask, title, color=PALETTE[0]):
        sub = sens_df[mask].sort_values("best_v")
        colors_bar = [PALETTE[3] if bv <= 36 else PALETTE[1] if bv <= 44 else PALETTE[4]
                      for bv in sub["best_v"]]
        bars = ax.barh(sub["label"], sub["best_v"], color=colors_bar, alpha=0.85, edgecolor="none")
        ax.axvline(40, color="black", lw=1.5, linestyle="--", alpha=0.7, label="v=40")
        ax.set_xlabel("Optimal v*")
        ax.set_title(title)
        ax.legend(fontsize=9)
        for bar, val in zip(bars, sub["best_v"]):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                    str(int(val)), va="center", fontsize=9)

    _bar(axes[0, 0], sens_df["label"].str.startswith("N="),    "N sensitivity",       PALETTE[0])
    _bar(axes[0, 1], sens_df["label"].str.startswith("AI="),   "AI version",           PALETTE[1])
    _bar(axes[1, 0], sens_df["label"].str.startswith("ai_w"),  "AI weight",            PALETTE[2])
    _bar(axes[1, 1], sens_df["label"].str.startswith("just_"), "Just-above weight",    PALETTE[4])

    plt.suptitle("Sensitivity: Optimal v* across parameter variations", fontsize=13, y=1.02)
    plt.tight_layout()
    savefig("08_sensitivity.png", fig)


# ─────────────────────────────────────────────────────────────────────────────
# FINAL RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────

def _build_recommendation(ev_df, rs_table, sens_df):
    v_arr = ev_df["v"].values
    best_ev_v = int(ev_df.loc[ev_df["mean_pnl"].idxmax(), "v"])

    # Robustness: median optimal v across sensitivity runs
    all_best = sens_df["best_v"].values
    median_v  = int(np.median(all_best))
    mode_v    = int(pd.Series(all_best).mode().iloc[0])

    # Minimax regret within sensitivity set (find v that minimises max regret)
    v_cands_rec = list(range(30, 55))
    max_regret_by_v = {}
    for v_cand in v_cands_rec:
        if v_cand in ev_df["v"].values:
            row = ev_df[ev_df["v"] == v_cand].iloc[0]
            max_regret_by_v[v_cand] = row["regret"]
    minimax_v = min(max_regret_by_v, key=max_regret_by_v.get)

    rs_idx = rs_table.set_index("v")

    def make_row(v_val):
        r = int(rs_idx.loc[v_val, "r_star"])
        s = int(rs_idx.loc[v_val, "s_star"])
        ev_row = ev_df[ev_df["v"] == v_val].iloc[0]
        return dict(
            criterion="",
            v=v_val, r=r, s=s,
            ev=ev_row["mean_pnl"],
            p10=ev_row["p10"],
            p90=ev_row["p90"],
            regret=ev_row["regret"],
        )

    rows = [
        {**make_row(best_ev_v),  "criterion": "Max EV (base mixture)"},
        {**make_row(median_v),   "criterion": "Median v* across sensitivity"},
        {**make_row(mode_v),     "criterion": "Mode v* across sensitivity"},
        {**make_row(minimax_v),  "criterion": "Minimax regret"},
    ]
    rec_df = pd.DataFrame(rows)
    return {"df": rec_df, "best_ev_v": best_ev_v, "median_v": median_v,
            "mode_v": mode_v, "minimax_v": minimax_v}


def _print_recommendation(rec):
    df = rec["df"]
    print("\n" + "═" * 65)
    print("  FINAL RECOMMENDATION — ITERATION 3")
    print("═" * 65)
    for _, row in df.iterrows():
        print(f"\n  [{row['criterion']}]")
        print(f"    v={int(row['v']):>3}  r={int(row['r']):>3}  s={int(row['s']):>3}  "
              f"(total={int(row['v'])+int(row['r'])+int(row['s'])})")
        print(f"    E[PnL]={row['ev']:>10,.0f}  p10={row['p10']:>10,.0f}  p90={row['p90']:>10,.0f}")
        print(f"    Regret={row['regret']:>10,.0f}")
    print("\n" + "═" * 65)


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent)
    main()
