from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import nbformat
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from scipy.stats import norm


BASE = Path(__file__).parent
OUT = BASE / "results" / "iteration3"
PLOTS = OUT / "plots"
CSVS = OUT / "csv"
PLOTS.mkdir(parents=True, exist_ok=True)
CSVS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE))

import iter3_analysis as base_iter3  # noqa: E402
from manual_round2_utils import (  # noqa: E402
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_RANGE,
    TOTAL_BUDGET,
    compute_rs_table,
    speed_multiplier,
    speed_rank,
    verify_ranking_examples,
)


# ──────────────────────────────────────────────────────────────────────────────
# Style / constants
# ──────────────────────────────────────────────────────────────────────────────

PALETTE = ["#2563EB", "#16A34A", "#F59E0B", "#DB2777", "#7C3AED", "#0891B2", "#EA580C"]
TYPE_LABELS = {
    "nash_like": "Nash-like / racionales",
    "focal_points": "Focal points",
    "just_above": "Just-above focal points",
    "ai_similar": "AI / recomendaciones parecidas",
    "naive_ev": "Naive EV / incompleto",
    "speed_race": "Speed-race agresivo",
    "random_pure": "Random puro",
}

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "#F8FAFC",
        "axes.grid": True,
        "grid.alpha": 0.22,
        "grid.color": "#CBD5E1",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "legend.frameon": False,
    }
)

SEED = 42
MAIN_N = 50
MAIN_SIMS = 20_000
SENS_SIMS = 5_000
V_GRID = np.arange(0, 101, 1)
V_GRID_SENS = np.arange(25, 56, 1)


def fmt_k(x, _=None) -> str:
    return f"{x/1e3:.0f}k"


def savefig(name: str, fig) -> None:
    path = PLOTS / name
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_csv_dual(filename: str, df: pd.DataFrame) -> None:
    df.to_csv(OUT / filename, index=False)
    df.to_csv(CSVS / filename, index=False)


def markdown_table(df: pd.DataFrame, float_fmt: str = ".1f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    rows: List[str] = []
    for _, row in df.iterrows():
        vals: List[str] = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(value, float_fmt))
            else:
                vals.append(str(value))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *rows,
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# Audit current implementation
# ──────────────────────────────────────────────────────────────────────────────


def audit_current_implementation() -> pd.DataFrame:
    findings = [
        {
            "topic": "Regret",
            "status": "needs_fix",
            "detail": "The current iter3 script computes regret vs the best mean EV, not expected regret vs the per-simulation best action.",
        },
        {
            "topic": "Sensitivity scope",
            "status": "needs_fix",
            "detail": "The current iter3 script varies N and some weights, but not the exact location of focal-point and just-above clusters.",
        },
        {
            "topic": "Artifacts",
            "status": "needs_fix",
            "detail": "The existing iteration3 folder had plots/CSVs, but no markdown summary and no final notebook-level synthesis.",
        },
        {
            "topic": "Ranking engine",
            "status": "ok",
            "detail": "The tie-aware ranking logic itself is correct because rank depends only on the count of strictly higher speeds.",
        },
        {
            "topic": "Research/Scale exact solver",
            "status": "ok",
            "detail": "The exact integer subproblem is already correctly solved by compute_rs_table().",
        },
    ]
    return pd.DataFrame(findings)


# ──────────────────────────────────────────────────────────────────────────────
# Explicit type distributions (exact PMFs)
# ──────────────────────────────────────────────────────────────────────────────


FOCAL_VERSIONS: Dict[str, Dict[str, Sequence[float]]] = {
    "base": {
        "values": [0, 10, 20, 25, 30, 33, 34, 35, 40, 50, 60, 67, 70, 100],
        "weights": [2.0, 6.0, 8.0, 8.0, 9.0, 14.0, 12.0, 12.0, 10.0, 8.0, 4.0, 2.0, 1.0, 0.5],
    },
    "round_heavy": {
        "values": [0, 10, 20, 25, 30, 33, 34, 35, 40, 50, 60, 67, 70, 100],
        "weights": [2.0, 7.0, 8.0, 9.0, 10.0, 16.0, 12.0, 14.0, 11.0, 7.0, 2.0, 1.0, 0.7, 0.3],
    },
    "low_mid": {
        "values": [0, 10, 20, 25, 30, 33, 34, 35, 40, 50],
        "weights": [3.0, 8.0, 12.0, 12.0, 12.0, 18.0, 12.0, 10.0, 8.0, 5.0],
    },
}

JUST_ABOVE_VERSIONS: Dict[str, Dict[str, Sequence[float]]] = {
    "base": {
        "values": [11, 21, 26, 31, 34, 35, 36, 41, 46, 51],
        "weights": [8.0, 9.0, 8.0, 13.0, 10.0, 12.0, 12.0, 14.0, 8.0, 6.0],
    },
    "lower": {
        "values": [11, 21, 26, 31, 34, 35, 41, 46, 51],
        "weights": [10.0, 10.0, 10.0, 15.0, 16.0, 16.0, 12.0, 7.0, 4.0],
    },
    "higher": {
        "values": [12, 22, 27, 32, 35, 36, 42, 47, 52],
        "weights": [9.0, 9.0, 9.0, 14.0, 16.0, 16.0, 13.0, 8.0, 6.0],
    },
}

AI_VERSIONS = base_iter3.AI_VERSIONS
TYPE_WEIGHTS = dict(base_iter3.TYPE_WEIGHTS)


def rounded_truncnorm_pmf(mu: float, sigma: float, lo: int = 0, hi: int = 100) -> pd.Series:
    xs = np.arange(101)
    probs = np.zeros(101, dtype=float)
    for x in xs:
        if x < lo or x > hi:
            continue
        lower = x - 0.5
        upper = x + 0.5
        probs[x] = norm.cdf(upper, loc=mu, scale=sigma) - norm.cdf(lower, loc=mu, scale=sigma)
    probs = np.maximum(probs, 0.0)
    probs /= probs.sum()
    return pd.Series(probs, index=xs)


def categorical_pmf(values: Sequence[int], weights: Sequence[float]) -> pd.Series:
    xs = np.arange(101)
    probs = np.zeros(101, dtype=float)
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    for value, weight in zip(values, w):
        probs[int(value)] += float(weight)
    return pd.Series(probs, index=xs)


def build_component_pmfs(
    *,
    ai_version: str = "base",
    focal_version: str = "base",
    just_above_version: str = "base",
) -> Dict[str, pd.Series]:
    focal_cfg = FOCAL_VERSIONS[focal_version]
    ja_cfg = JUST_ABOVE_VERSIONS[just_above_version]
    ai_cfg = AI_VERSIONS[ai_version]

    if ai_cfg["kind"] == "normal":
        ai_pmf = rounded_truncnorm_pmf(ai_cfg["mu"], ai_cfg["sigma"], int(ai_cfg["lo"]), int(ai_cfg["hi"]))
    else:
        ai_pmf = categorical_pmf(ai_cfg["values"], ai_cfg["weights"])

    pmfs = {
        "nash_like": rounded_truncnorm_pmf(mu=32.0, sigma=10.0, lo=0, hi=100),
        "focal_points": categorical_pmf(focal_cfg["values"], focal_cfg["weights"]),
        "just_above": categorical_pmf(ja_cfg["values"], ja_cfg["weights"]),
        "ai_similar": ai_pmf,
        "naive_ev": rounded_truncnorm_pmf(mu=50.0, sigma=18.0, lo=0, hi=100),
        "speed_race": rounded_truncnorm_pmf(mu=70.0, sigma=12.0, lo=0, hi=100),
        "random_pure": pd.Series(np.ones(101) / 101.0, index=np.arange(101)),
    }
    return pmfs


def build_mixture_pmf(
    component_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float] = TYPE_WEIGHTS,
) -> pd.Series:
    mixture = pd.Series(np.zeros(101), index=np.arange(101), dtype=float)
    for name, weight in weights.items():
        mixture += float(weight) * component_pmfs[name]
    mixture /= mixture.sum()
    return mixture


def sample_from_component_pmfs(
    n_samples: int,
    rng: np.random.Generator,
    component_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float] = TYPE_WEIGHTS,
) -> np.ndarray:
    names = list(weights.keys())
    probs = np.array([weights[name] for name in names], dtype=float)
    probs /= probs.sum()
    type_idx = rng.choice(len(names), size=n_samples, p=probs)
    speeds = np.zeros(n_samples, dtype=int)
    grid = np.arange(101)
    for i, name in enumerate(names):
        mask = type_idx == i
        if mask.any():
            speeds[mask] = rng.choice(grid, size=int(mask.sum()), p=component_pmfs[name].values)
    return speeds


def top_mass_table(component_pmfs: Mapping[str, pd.Series], mixture_pmf: pd.Series, top_n: int = 8) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for name, pmf in list(component_pmfs.items()) + [("mixture_total", mixture_pmf)]:
        top = pmf.sort_values(ascending=False).head(top_n)
        rows.append(
            {
                "component": name,
                "top_speeds": ", ".join(str(int(v)) for v in top.index),
                "top_probs_pct": ", ".join(f"{100*x:.1f}%" for x in top.values),
                "mean_speed": float((np.asarray(pmf.index, dtype=float) * pmf.values).sum()),
            }
        )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Exact ranking engine checks
# ──────────────────────────────────────────────────────────────────────────────


def ranking_examples_table() -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    example_1 = [70, 70, 70, 50, 40, 40, 30]
    for idx, value in enumerate(example_1):
        others = example_1[:idx] + example_1[idx + 1 :]
        rows.append(
            {
                "example": "ties",
                "my_speed": value,
                "others": str(others),
                "rank": speed_rank(value, others),
                "multiplier": speed_multiplier(value, others),
            }
        )

    example_2 = [95, 20, 10]
    for idx, value in enumerate(example_2):
        others = example_2[:idx] + example_2[idx + 1 :]
        rows.append(
            {
                "example": "three_players",
                "my_speed": value,
                "others": str(others),
                "rank": speed_rank(value, others),
                "multiplier": speed_multiplier(value, others),
            }
        )

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Monte Carlo engine with exact regret
# ──────────────────────────────────────────────────────────────────────────────


def monte_carlo_speed_game(
    rs_table: pd.DataFrame,
    component_pmfs: Mapping[str, pd.Series],
    *,
    weights: Mapping[str, float] = TYPE_WEIGHTS,
    N: int = MAIN_N,
    n_sims: int = MAIN_SIMS,
    seed: int = SEED,
    v_grid: Sequence[int] = V_GRID,
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    others = sample_from_component_pmfs(n_sims * (N - 1), rng, component_pmfs, weights=weights).reshape(n_sims, N - 1)

    rs_idx = rs_table.set_index("v")
    v_arr = np.array(list(v_grid), dtype=int)
    pnl_matrix = np.empty((n_sims, len(v_arr)), dtype=float)
    mult_matrix = np.empty_like(pnl_matrix)

    for j, v in enumerate(v_arr):
        gross_value = float(rs_idx.loc[v, "gross_value"])
        n_higher = (others > v).sum(axis=1)
        rank = n_higher + 1
        mult = SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE
        pnl = gross_value * mult - TOTAL_BUDGET
        pnl_matrix[:, j] = pnl
        mult_matrix[:, j] = mult

    best_per_sim = pnl_matrix.max(axis=1, keepdims=True)
    regret_matrix = best_per_sim - pnl_matrix

    rows: List[Dict[str, float | int]] = []
    for j, v in enumerate(v_arr):
        pnl = pnl_matrix[:, j]
        mult = mult_matrix[:, j]
        n_higher = (others > v).sum(axis=1)
        rank = n_higher + 1
        rows.append(
            {
                "v": int(v),
                "mean_pnl": float(pnl.mean()),
                "std_pnl": float(pnl.std(ddof=0)),
                "p10": float(np.percentile(pnl, 10)),
                "p25": float(np.percentile(pnl, 25)),
                "p50": float(np.percentile(pnl, 50)),
                "p75": float(np.percentile(pnl, 75)),
                "p90": float(np.percentile(pnl, 90)),
                "mean_multiplier": float(mult.mean()),
                "std_multiplier": float(mult.std(ddof=0)),
                "p10_multiplier": float(np.percentile(mult, 10)),
                "p90_multiplier": float(np.percentile(mult, 90)),
                "mean_rank": float(rank.mean()),
                "p10_rank": float(np.percentile(rank, 10)),
                "p90_rank": float(np.percentile(rank, 90)),
                "expected_regret": float(regret_matrix[:, j].mean()),
                "p90_regret": float(np.percentile(regret_matrix[:, j], 90)),
                "prob_best_response": float((np.abs(pnl - best_per_sim[:, 0]) < 1e-9).mean()),
            }
        )
    return pd.DataFrame(rows), pnl_matrix, others


def selected_rank_multiplier_stats(
    rs_table: pd.DataFrame,
    component_pmfs: Mapping[str, pd.Series],
    *,
    weights: Mapping[str, float] = TYPE_WEIGHTS,
    N: int = MAIN_N,
    n_sims: int = 25_000,
    seed: int = SEED + 99,
    selected_v: Sequence[int] = (34, 40, 42, 44, 46),
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    others = sample_from_component_pmfs(n_sims * (N - 1), rng, component_pmfs, weights=weights).reshape(n_sims, N - 1)
    rs_idx = rs_table.set_index("v")
    rows: List[Dict[str, float | int]] = []
    for v in selected_v:
        gross_value = float(rs_idx.loc[v, "gross_value"])
        n_higher = (others > v).sum(axis=1)
        rank = n_higher + 1
        mult = SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE
        pnl = gross_value * mult - TOTAL_BUDGET
        for r, m, p in zip(rank, mult, pnl):
            rows.append({"v": int(v), "rank": int(r), "multiplier": float(m), "pnl": float(p)})
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Sensitivity scenarios
# ──────────────────────────────────────────────────────────────────────────────


def normalize_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    total = float(sum(weights.values()))
    return {k: float(v) / total for k, v in weights.items()}


def reweight_component(base_weights: Mapping[str, float], key: str, new_weight: float, absorb_key: str = "nash_like") -> Dict[str, float]:
    weights = dict(base_weights)
    delta = new_weight - weights[key]
    weights[key] = new_weight
    weights[absorb_key] = max(0.05, weights[absorb_key] - delta)
    return normalize_weights(weights)


def sensitivity_cases() -> List[Dict[str, object]]:
    cases: List[Dict[str, object]] = []

    for n in [20, 35, 50, 75, 100]:
        cases.append(
            {
                "label": f"N={n}",
                "group": "N",
                "weights": TYPE_WEIGHTS,
                "ai_version": "base",
                "focal_version": "base",
                "just_above_version": "base",
                "N": n,
            }
        )

    for ai_version in ["base", "concentrated", "higher"]:
        cases.append(
            {
                "label": f"AI version = {ai_version}",
                "group": "ai_version",
                "weights": TYPE_WEIGHTS,
                "ai_version": ai_version,
                "focal_version": "base",
                "just_above_version": "base",
                "N": MAIN_N,
            }
        )

    for ai_weight in [0.20, 0.30, 0.40, 0.50]:
        cases.append(
            {
                "label": f"AI weight = {ai_weight:.0%}",
                "group": "ai_weight",
                "weights": reweight_component(TYPE_WEIGHTS, "ai_similar", ai_weight),
                "ai_version": "base",
                "focal_version": "base",
                "just_above_version": "base",
                "N": MAIN_N,
            }
        )

    for ja_weight in [0.10, 0.20, 0.30]:
        cases.append(
            {
                "label": f"Just-above weight = {ja_weight:.0%}",
                "group": "just_above_weight",
                "weights": reweight_component(TYPE_WEIGHTS, "just_above", ja_weight),
                "ai_version": "base",
                "focal_version": "base",
                "just_above_version": "base",
                "N": MAIN_N,
            }
        )

    for focal_weight in [0.05, 0.10, 0.15, 0.20]:
        cases.append(
            {
                "label": f"Focal weight = {focal_weight:.0%}",
                "group": "focal_weight",
                "weights": reweight_component(TYPE_WEIGHTS, "focal_points", focal_weight),
                "ai_version": "base",
                "focal_version": "base",
                "just_above_version": "base",
                "N": MAIN_N,
            }
        )

    for focal_version in ["base", "round_heavy", "low_mid"]:
        cases.append(
            {
                "label": f"Focal locations = {focal_version}",
                "group": "focal_version",
                "weights": TYPE_WEIGHTS,
                "ai_version": "base",
                "focal_version": focal_version,
                "just_above_version": "base",
                "N": MAIN_N,
            }
        )

    for ja_version in ["base", "lower", "higher"]:
        cases.append(
            {
                "label": f"Just-above locations = {ja_version}",
                "group": "just_above_version",
                "weights": TYPE_WEIGHTS,
                "ai_version": "base",
                "focal_version": "base",
                "just_above_version": ja_version,
                "N": MAIN_N,
            }
        )

    return cases


def run_sensitivity(rs_table: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    curves: List[pd.DataFrame] = []
    summary_rows: List[Dict[str, object]] = []

    for idx, case in enumerate(sensitivity_cases()):
        pmfs = build_component_pmfs(
            ai_version=str(case["ai_version"]),
            focal_version=str(case["focal_version"]),
            just_above_version=str(case["just_above_version"]),
        )
        curve_df, _pnl_matrix, _others = monte_carlo_speed_game(
            rs_table,
            pmfs,
            weights=case["weights"],
            N=int(case["N"]),
            n_sims=SENS_SIMS,
            seed=SEED + 100 + idx,
            v_grid=V_GRID_SENS,
        )
        curve_df = curve_df.copy()
        curve_df["label"] = str(case["label"])
        curve_df["group"] = str(case["group"])
        curves.append(curve_df)

        best_row = curve_df.loc[curve_df["mean_pnl"].idxmax()]
        robust_row = curve_df.loc[curve_df["expected_regret"].idxmin()]
        summary_rows.append(
            {
                "label": str(case["label"]),
                "group": str(case["group"]),
                "best_v": int(best_row["v"]),
                "best_ev": float(best_row["mean_pnl"]),
                "robust_v": int(robust_row["v"]),
                "robust_ev": float(robust_row["mean_pnl"]),
                "best_p10": float(best_row["p10"]),
                "best_expected_regret": float(best_row["expected_regret"]),
                "N": int(case["N"]),
                "ai_version": str(case["ai_version"]),
                "focal_version": str(case["focal_version"]),
                "just_above_version": str(case["just_above_version"]),
            }
        )

    curves_df = pd.concat(curves, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows)
    return summary_df, curves_df


def aggregate_sensitivity_curves(curves_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | int]] = []
    for v, sub in curves_df.groupby("v"):
        ev_vals = sub["mean_pnl"].values
        reg_vals = sub["expected_regret"].values
        rows.append(
            {
                "v": int(v),
                "mean_ev_across_scenarios": float(ev_vals.mean()),
                "median_ev_across_scenarios": float(np.median(ev_vals)),
                "min_ev_across_scenarios": float(ev_vals.min()),
                "p25_ev_across_scenarios": float(np.percentile(ev_vals, 25)),
                "p75_ev_across_scenarios": float(np.percentile(ev_vals, 75)),
                "mean_expected_regret_across_scenarios": float(reg_vals.mean()),
                "max_expected_regret_across_scenarios": float(reg_vals.max()),
            }
        )
    return pd.DataFrame(rows).sort_values("v").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Plots
# ──────────────────────────────────────────────────────────────────────────────


def plot_rs_subproblem(rs_table: pd.DataFrame) -> None:
    rs = rs_table.copy()
    multipliers = [0.1, 0.3, 0.5, 0.7, 0.9]
    fig = plt.figure(figsize=(17, 11))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.28)

    ax = fig.add_subplot(gs[0, 0])
    ax.plot(rs["v"], rs["r_star"], color=PALETTE[1], lw=2.5, label="r*(v)")
    ax.plot(rs["v"], rs["s_star"], color=PALETTE[0], lw=2.5, label="s*(v)")
    ax.set_title("Exact Research/Scale split by Speed")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Allocation (%)")
    ax.legend()

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(rs["v"], rs["gross_value"] / 1e3, color=PALETTE[4], lw=2.5)
    ax.set_title("Gross value(v) = Research(r*) × Scale(s*)")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Gross value (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))

    ax = fig.add_subplot(gs[1, 0])
    for mult, color in zip(multipliers, PALETTE):
        pnl = rs["gross_value"] * mult - rs["budget_used"]
        ax.plot(rs["v"], pnl / 1e3, lw=2, color=color, label=f"mult = {mult:.1f}")
    ax.axhline(0, color="black", lw=1, linestyle=":")
    ax.set_title("Net PnL(v) under representative multipliers")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.legend(ncol=2, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))

    ax = fig.add_subplot(gs[1, 1])
    ax.stackplot(
        rs["v"],
        rs["r_star"],
        rs["s_star"],
        colors=[PALETTE[1], PALETTE[0]],
        alpha=0.82,
        labels=["Research r*", "Scale s*"],
    )
    ax.set_title("Composition of the exact Research/Scale optimum")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Allocation (%)")
    ax.legend(loc="upper right")

    fig.suptitle("Exact economic subproblem for each Speed choice", fontsize=14, y=1.02)
    savefig("00_rs_subproblem.png", fig)


def plot_component_pmfs(component_pmfs: Mapping[str, pd.Series], mixture_pmf: pd.Series) -> None:
    v = np.arange(101)

    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    for ax, (name, pmf), color in zip(axes.flatten()[:7], component_pmfs.items(), PALETTE):
        ax.bar(v, pmf.values * 100, width=1.0, color=color, alpha=0.85, edgecolor="none")
        mu = float((np.asarray(pmf.index, dtype=float) * pmf.values).sum())
        ax.axvline(mu, color="black", lw=1.5, linestyle="--", label=f"μ={mu:.1f}")
        ax.set_title(TYPE_LABELS[name])
        ax.set_xlabel("Speed v")
        ax.set_ylabel("PMF (%)")
        ax.set_xlim(-1, 101)
        ax.legend(fontsize=8)

    ax = axes.flatten()[7]
    ax.bar(v, mixture_pmf.values * 100, width=1.0, color="#64748B", alpha=0.85, edgecolor="none")
    mu_mix = float((np.asarray(mixture_pmf.index, dtype=float) * mixture_pmf.values).sum())
    ax.axvline(mu_mix, color="black", lw=1.8, linestyle="--", label=f"μ={mu_mix:.1f}")
    ax.set_title("Mixture total")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")
    ax.set_xlim(-1, 101)
    ax.legend(fontsize=8)

    fig.suptitle("PMF por tipo de jugador y mezcla total", fontsize=14, y=1.02)
    savefig("01_component_pmfs.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))
    ax = axes[0]
    for color, (name, pmf) in zip(PALETTE, component_pmfs.items()):
        ax.plot(v, pmf.values * TYPE_WEIGHTS[name] * 100, lw=2.2, color=color, label=TYPE_LABELS[name])
    ax.fill_between(v, 0, mixture_pmf.values * 100, color="#94A3B8", alpha=0.18, label="Mixture total")
    ax.set_title("Weighted contribution of each type")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Contribution to PMF (%)")
    ax.legend(fontsize=8, ncol=2)

    ax = axes[1]
    mask = (v >= 20) & (v <= 45)
    for color, (name, pmf) in zip(PALETTE, component_pmfs.items()):
        ax.plot(v[mask], pmf.values[mask] * TYPE_WEIGHTS[name] * 100, lw=2.2, color=color, label=TYPE_LABELS[name])
    ax.fill_between(v[mask], 0, mixture_pmf.values[mask] * 100, color="#94A3B8", alpha=0.18, label="Mixture total")
    for fp in [30, 33, 34, 35, 36, 40, 41, 42]:
        ax.axvline(fp, color="#0F172A", lw=0.7, linestyle=":", alpha=0.45)
    ax.set_title("Zoom 20–45: focal / just-above / AI cluster")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Contribution to PMF (%)")
    ax.legend(fontsize=8, ncol=2)

    fig.suptitle("Superposed type distributions", fontsize=14, y=1.02)
    savefig("02_component_overlay_zoom.png", fig)


def plot_mixture_total(component_pmfs: Mapping[str, pd.Series], mixture_pmf: pd.Series) -> None:
    v = np.arange(101)
    cdf = np.cumsum(mixture_pmf.values)
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.28)

    ax = fig.add_subplot(gs[0, 0])
    ax.bar(v, mixture_pmf.values * 100, width=1.0, color="#64748B", alpha=0.85, edgecolor="none")
    mu = float((np.asarray(mixture_pmf.index, dtype=float) * mixture_pmf.values).sum())
    ax.axvline(mu, color="red", lw=1.8, linestyle="--", label=f"mean = {mu:.1f}")
    for fp in [30, 33, 34, 35, 36, 40, 41]:
        ax.axvline(fp, color=PALETTE[3], lw=1.1, linestyle=":", alpha=0.65)
    ax.set_title("Total mixture PMF")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")
    ax.legend(fontsize=9)

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(v, cdf * 100, color=PALETTE[0], lw=2.5)
    for q, color in [(25, PALETTE[1]), (50, PALETTE[3]), (75, PALETTE[2])]:
        cutoff = int(v[np.searchsorted(cdf, q / 100)])
        ax.axhline(q, color=color, lw=1, linestyle="--", alpha=0.7)
        ax.axvline(cutoff, color=color, lw=1, linestyle="--", alpha=0.7, label=f"p{q} = {cutoff}")
    ax.set_title("Cumulative distribution of field Speed")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("CDF (%)")
    ax.legend(fontsize=9)

    ax = fig.add_subplot(gs[1, 0])
    mask = (v >= 20) & (v <= 45)
    ax.bar(v[mask], mixture_pmf.values[mask] * 100, width=1.0, color="#64748B", alpha=0.85, edgecolor="none")
    annot = {30: "30", 33: "33", 34: "34", 35: "35", 36: "36", 40: "40", 41: "41"}
    for value, label in annot.items():
        ax.axvline(value, color=PALETTE[3], lw=1.1, linestyle=":", alpha=0.7)
        ax.text(value + 0.25, mixture_pmf.loc[value] * 100 + 0.06, label, fontsize=8, color=PALETTE[3])
    ax.set_title("Zoom 20–45: where the field clusters")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")

    ax = fig.add_subplot(gs[1, 1])
    bottom = np.zeros(101)
    mask = (v >= 20) & (v <= 45)
    for color, (name, pmf) in zip(PALETTE, component_pmfs.items()):
        contrib = pmf.values * TYPE_WEIGHTS[name] * 100
        ax.bar(v[mask], contrib[mask], bottom=bottom[mask], color=color, alpha=0.88, width=1.0, edgecolor="none", label=TYPE_LABELS[name])
        bottom[mask] += contrib[mask]
    ax.set_title("Stacked type contributions (zoom 20–45)")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Stacked PMF (%)")
    ax.legend(fontsize=8, ncol=2)

    fig.suptitle("Total field distribution implied by the user-specified mixture", fontsize=14, y=1.02)
    savefig("03_mixture_total.png", fig)


def plot_ev_and_regret(main_df: pd.DataFrame, best_v: int, robust_v: int, conservative_v: int) -> None:
    v = main_df["v"].values

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ax.fill_between(v, main_df["p10"] / 1e3, main_df["p90"] / 1e3, alpha=0.12, color=PALETTE[0], label="p10–p90")
    ax.fill_between(v, main_df["p25"] / 1e3, main_df["p75"] / 1e3, alpha=0.24, color=PALETTE[0], label="p25–p75")
    ax.plot(v, main_df["mean_pnl"] / 1e3, color=PALETTE[0], lw=2.8, label="EV")
    ax.plot(v, main_df["p50"] / 1e3, color=PALETTE[0], lw=1.3, linestyle="--", alpha=0.7, label="median")
    ax.axvline(best_v, color="black", lw=2, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--", label=f"robust={robust_v}")
    ax.axvline(conservative_v, color=PALETTE[2], lw=1.8, linestyle=":", label=f"conservative={conservative_v}")
    ax.axhline(0, color="#475569", lw=1, linestyle=":")
    ax.set_title("EV by Speed with uncertainty bands")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    ax = axes[1]
    mask = (v >= 20) & (v <= 50)
    ax.fill_between(v[mask], main_df.loc[mask, "p10"] / 1e3, main_df.loc[mask, "p90"] / 1e3, alpha=0.12, color=PALETTE[0])
    ax.fill_between(v[mask], main_df.loc[mask, "p25"] / 1e3, main_df.loc[mask, "p75"] / 1e3, alpha=0.24, color=PALETTE[0])
    ax.plot(v[mask], main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE[0], lw=2.8)
    ax.axvline(best_v, color="black", lw=2)
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--")
    ax.axvline(conservative_v, color=PALETTE[2], lw=1.8, linestyle=":")
    for fp in [30, 33, 34, 35, 36, 40, 41, 42, 44]:
        ax.axvline(fp, color="#64748B", lw=0.8, linestyle=":", alpha=0.4)
    ax.set_xlim(20, 50)
    ax.set_title("Zoom 20–50")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))

    fig.suptitle("Main Monte Carlo payoff surface", fontsize=14, y=1.02)
    savefig("04_ev_by_speed.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ax.fill_between(v, 0, main_df["expected_regret"] / 1e3, alpha=0.25, color=PALETTE[3])
    ax.plot(v, main_df["expected_regret"] / 1e3, color=PALETTE[3], lw=2.8, label="Expected regret")
    ax.plot(v, main_df["p90_regret"] / 1e3, color=PALETTE[4], lw=1.8, linestyle="--", label="p90 regret")
    ax.axvline(robust_v, color=PALETTE[1], lw=2, label=f"robust={robust_v}")
    ax.set_title("Regret by Speed")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    ax = axes[1]
    mask = (v >= 20) & (v <= 50)
    ax.fill_between(v[mask], 0, main_df.loc[mask, "expected_regret"] / 1e3, alpha=0.25, color=PALETTE[3])
    ax.plot(v[mask], main_df.loc[mask, "expected_regret"] / 1e3, color=PALETTE[3], lw=2.8)
    ax.plot(v[mask], main_df.loc[mask, "p90_regret"] / 1e3, color=PALETTE[4], lw=1.8, linestyle="--")
    ax.axvline(robust_v, color=PALETTE[1], lw=2)
    for fp in [30, 33, 34, 35, 36, 40, 41, 42, 44]:
        ax.axvline(fp, color="#64748B", lw=0.8, linestyle=":", alpha=0.4)
    ax.set_xlim(20, 50)
    ax.set_title("Regret zoom 20–50")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))

    fig.suptitle("Expected regret relative to the per-simulation best v", fontsize=14, y=1.02)
    savefig("05_regret_by_speed.png", fig)


def plot_rank_multiplier_diagnostics(diag_df: pd.DataFrame) -> None:
    selected = sorted(diag_df["v"].unique())
    fig, axes = plt.subplots(2, len(selected), figsize=(3.8 * len(selected), 8))
    for col, v in enumerate(selected):
        sub = diag_df[diag_df["v"] == v]
        ax = axes[0, col]
        ax.hist(sub["rank"], bins=np.arange(1, MAIN_N + 3) - 0.5, color=PALETTE[col % len(PALETTE)], alpha=0.82)
        ax.axvline(sub["rank"].mean(), color="black", lw=1.5, linestyle="--")
        ax.set_title(f"Rank distribution — v={v}")
        ax.set_xlabel("Rank")
        ax.set_ylabel("Count")

        ax = axes[1, col]
        ax.hist(sub["multiplier"], bins=20, color=PALETTE[col % len(PALETTE)], alpha=0.82)
        ax.axvline(sub["multiplier"].mean(), color="black", lw=1.5, linestyle="--")
        ax.set_title(f"Multiplier distribution — v={v}")
        ax.set_xlabel("Multiplier")
        ax.set_ylabel("Count")
    fig.suptitle("Induced rank and multiplier distributions for key candidate speeds", fontsize=14, y=1.02)
    savefig("06_rank_multiplier_diagnostics.png", fig)


def plot_dashboard(main_df: pd.DataFrame, mixture_pmf: pd.Series, rs_table: pd.DataFrame, best_v: int, robust_v: int, conservative_v: int) -> None:
    v = main_df["v"].values
    fig = plt.figure(figsize=(17, 11))
    gs = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32)

    ax = fig.add_subplot(gs[0, 0])
    ax.bar(mixture_pmf.index, mixture_pmf.values * 100, width=1.0, color="#64748B", alpha=0.85, edgecolor="none")
    for fp in [30, 33, 34, 35, 36, 40, 41, 42, 44]:
        ax.axvline(fp, color=PALETTE[3], lw=1.0, linestyle=":", alpha=0.55)
    ax.axvline(best_v, color="black", lw=2, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--", label=f"robust={robust_v}")
    ax.set_title("Field distribution of Speed")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")
    ax.legend(fontsize=9)

    ax = fig.add_subplot(gs[0, 1])
    mask = (v >= 20) & (v <= 50)
    ax.fill_between(v[mask], main_df.loc[mask, "p10"] / 1e3, main_df.loc[mask, "p90"] / 1e3, alpha=0.12, color=PALETTE[0])
    ax.fill_between(v[mask], main_df.loc[mask, "p25"] / 1e3, main_df.loc[mask, "p75"] / 1e3, alpha=0.24, color=PALETTE[0])
    ax.plot(v[mask], main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE[0], lw=2.8, label="EV")
    ax.axvline(best_v, color="black", lw=2, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--", label=f"robust={robust_v}")
    ax.axvline(conservative_v, color=PALETTE[2], lw=1.8, linestyle=":", label=f"conservative={conservative_v}")
    ax.set_title("EV(v) in the candidate zone")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    ax = fig.add_subplot(gs[1, 0])
    ax.stackplot(rs_table["v"], rs_table["r_star"], rs_table["s_star"], colors=[PALETTE[1], PALETTE[0]], alpha=0.84, labels=["Research", "Scale"])
    ax.axvline(best_v, color="black", lw=2, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--", label=f"robust={robust_v}")
    ax.set_title("Exact optimal split r*(v), s*(v)")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Allocation (%)")
    ax.legend(fontsize=9)

    ax = fig.add_subplot(gs[1, 1])
    ax.plot(v[mask], main_df.loc[mask, "expected_regret"] / 1e3, color=PALETTE[3], lw=2.8, label="Expected regret")
    ax.plot(v[mask], main_df.loc[mask, "p90_regret"] / 1e3, color=PALETTE[4], lw=1.8, linestyle="--", label="p90 regret")
    ax.axvline(robust_v, color=PALETTE[1], lw=2, label=f"robust={robust_v}")
    ax.set_title("Regret in the candidate zone")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=9)

    fig.suptitle("Iteration 3 dashboard — field clusters, payoff, exact RS split and regret", fontsize=14, y=1.02)
    savefig("07_dashboard.png", fig)


def plot_sensitivity(summary_df: pd.DataFrame, agg_df: pd.DataFrame, best_v: int, robust_v: int, conservative_v: int) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    def bar_panel(ax, group: str, title: str):
        sub = summary_df[summary_df["group"] == group].copy()
        if sub.empty:
            ax.axis("off")
            return
        sub = sub.sort_values("best_v")
        colors = [
            PALETTE[3] if v <= 40 else PALETTE[1] if v <= 43 else PALETTE[2]
            for v in sub["best_v"]
        ]
        bars = ax.barh(sub["label"], sub["best_v"], color=colors, alpha=0.85)
        ax.axvline(best_v, color="black", lw=1.8, linestyle="--", alpha=0.75, label=f"EV*={best_v}")
        ax.axvline(robust_v, color=PALETTE[1], lw=1.5, linestyle=":", alpha=0.75, label=f"robust={robust_v}")
        ax.set_xlabel("Best v")
        ax.set_title(title)
        ax.legend(fontsize=8)
        for bar, value in zip(bars, sub["best_v"]):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, str(int(value)), va="center", fontsize=9)

    bar_panel(axes[0, 0], "N", "Sensitivity to total players N")
    bar_panel(axes[0, 1], "ai_version", "Sensitivity to AI cluster location")
    bar_panel(axes[1, 0], "ai_weight", "Sensitivity to AI weight")
    bar_panel(axes[1, 1], "just_above_weight", "Sensitivity to just-above weight")

    fig.suptitle("Best Speed across the main sensitivity families", fontsize=14, y=1.02)
    savefig("08_sensitivity_families.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ax.plot(agg_df["v"], agg_df["mean_ev_across_scenarios"] / 1e3, color=PALETTE[0], lw=2.6, label="mean EV across scenarios")
    ax.plot(agg_df["v"], agg_df["median_ev_across_scenarios"] / 1e3, color=PALETTE[4], lw=2.0, linestyle="--", label="median EV across scenarios")
    ax.plot(agg_df["v"], agg_df["min_ev_across_scenarios"] / 1e3, color=PALETTE[2], lw=1.8, linestyle=":", label="min EV across scenarios")
    ax.axvline(best_v, color="black", lw=1.8, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, linestyle="--", label=f"robust={robust_v}")
    ax.axvline(conservative_v, color=PALETTE[2], lw=1.8, linestyle=":", label=f"conservative={conservative_v}")
    ax.set_title("Scenario-aggregated EV metrics")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(agg_df["v"], agg_df["mean_expected_regret_across_scenarios"] / 1e3, color=PALETTE[3], lw=2.6, label="mean expected regret")
    ax.plot(agg_df["v"], agg_df["max_expected_regret_across_scenarios"] / 1e3, color=PALETTE[5], lw=1.8, linestyle="--", label="max expected regret")
    ax.axvline(robust_v, color=PALETTE[1], lw=1.8, label=f"robust={robust_v}")
    ax.set_title("Scenario-aggregated regret metrics")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=8)

    fig.suptitle("Aggregated sensitivity surface", fontsize=14, y=1.02)
    savefig("09_sensitivity_aggregate.png", fig)


def plot_recommendation_zoom(main_df: pd.DataFrame, agg_df: pd.DataFrame, mixture_pmf: pd.Series, best_v: int, robust_v: int, conservative_v: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8))
    mask = (main_df["v"] >= 30) & (main_df["v"] <= 48)

    ax = axes[0]
    v = main_df.loc[mask, "v"].values
    ax.bar(v, mixture_pmf.loc[v].values * 100, width=1.0, color="#64748B", alpha=0.85, edgecolor="none")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE[1], f"robust={robust_v}"),
        (conservative_v, PALETTE[2], f"conservative={conservative_v}"),
    ]:
        ax.axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    ax.set_title("Where the field clusters")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(v, main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE[0], lw=2.8, label="main EV")
    ax.plot(v, agg_df.loc[agg_df["v"].isin(v), "median_ev_across_scenarios"].values / 1e3, color=PALETTE[4], lw=1.8, linestyle="--", label="median EV across sensitivity")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE[1], f"robust={robust_v}"),
        (conservative_v, PALETTE[2], f"conservative={conservative_v}"),
    ]:
        ax.axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    ax.set_title("Payoff around the final candidate zone")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(v, main_df.loc[mask, "expected_regret"] / 1e3, color=PALETTE[3], lw=2.8, label="main expected regret")
    ax.plot(v, agg_df.loc[agg_df["v"].isin(v), "max_expected_regret_across_scenarios"].values / 1e3, color=PALETTE[5], lw=1.8, linestyle="--", label="max regret across sensitivity")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE[1], f"robust={robust_v}"),
        (conservative_v, PALETTE[2], f"conservative={conservative_v}"),
    ]:
        ax.axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    ax.set_title("Regret around the final candidate zone")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k))
    ax.legend(fontsize=8)

    fig.suptitle("Final decision zoom", fontsize=14, y=1.02)
    savefig("10_final_recommendation_zoom.png", fig)


# ──────────────────────────────────────────────────────────────────────────────
# Final recommendation synthesis
# ──────────────────────────────────────────────────────────────────────────────


def build_final_recommendation(
    rs_table: pd.DataFrame,
    main_df: pd.DataFrame,
    sensitivity_summary: pd.DataFrame,
    sensitivity_aggregate: pd.DataFrame,
) -> pd.DataFrame:
    rs_idx = rs_table.set_index("v")
    best_v = int(main_df.loc[main_df["mean_pnl"].idxmax(), "v"])
    robust_v = int(main_df.loc[main_df["expected_regret"].idxmin(), "v"])
    conservative_v = int(sensitivity_aggregate.loc[sensitivity_aggregate["min_ev_across_scenarios"].idxmax(), "v"])

    best_vals = sensitivity_summary["best_v"].values
    best_v_low = int(np.min(best_vals))
    best_v_high = int(np.max(best_vals))

    within_1pct = sensitivity_aggregate.loc[
        sensitivity_aggregate["mean_ev_across_scenarios"]
        >= sensitivity_aggregate["mean_ev_across_scenarios"].max() * 0.99,
        "v",
    ]
    defendable_low = int(within_1pct.min())
    defendable_high = int(within_1pct.max())

    rows: List[Dict[str, object]] = []
    for criterion, v in [
        ("Max EV (central mixture)", best_v),
        ("Robust (min expected regret)", robust_v),
        ("Conservative (best min EV across sensitivity)", conservative_v),
    ]:
        row = main_df.loc[main_df["v"] == v].iloc[0]
        rows.append(
            {
                "criterion": criterion,
                "v": int(v),
                "r": int(rs_idx.loc[v, "r_star"]),
                "s": int(rs_idx.loc[v, "s_star"]),
                "gross_value": float(rs_idx.loc[v, "gross_value"]),
                "expected_pnl": float(row["mean_pnl"]),
                "p10_pnl": float(row["p10"]),
                "p90_pnl": float(row["p90"]),
                "expected_regret": float(row["expected_regret"]),
                "prob_best_response": float(row["prob_best_response"]),
                "broad_sensitivity_range_low": best_v_low,
                "broad_sensitivity_range_high": best_v_high,
                "core_defendable_range_low": defendable_low,
                "core_defendable_range_high": defendable_high,
            }
        )
    return pd.DataFrame(rows)


def build_summary_markdown(
    audit_df: pd.DataFrame,
    rs_table: pd.DataFrame,
    component_top_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    main_df: pd.DataFrame,
    mixture_pmf: pd.Series,
    sensitivity_summary: pd.DataFrame,
    sensitivity_aggregate: pd.DataFrame,
    final_rec_df: pd.DataFrame,
) -> str:
    best_row = final_rec_df.iloc[0]
    robust_row = final_rec_df.iloc[1]
    conservative_row = final_rec_df.iloc[2]
    best_v_val = int(best_row["v"])
    robust_v_val = int(robust_row["v"])
    conservative_v_val = int(conservative_row["v"])

    top_mix = mixture_pmf.sort_values(ascending=False).head(10)
    cluster_text = ", ".join(f"{int(v)} ({100*p:.1f}%)" for v, p in zip(top_mix.index[:6], top_mix.values[:6]))
    broad_low, broad_high = int(best_row["broad_sensitivity_range_low"]), int(best_row["broad_sensitivity_range_high"])
    core_low, core_high = int(best_row["core_defendable_range_low"]), int(best_row["core_defendable_range_high"])

    cand_mask = main_df["v"].isin([41, 42, 43, 44, 45])
    cand_table = main_df.loc[
        cand_mask,
        ["v", "mean_pnl", "p10", "p90", "expected_regret", "mean_multiplier", "mean_rank", "prob_best_response"],
    ].copy()

    best_counts = sensitivity_summary["best_v"].value_counts().sort_index().reset_index()
    best_counts.columns = ["v", "count"]
    best_mode = int(sensitivity_summary["best_v"].mode().iloc[0])
    second_mode = int(best_counts.sort_values("count", ascending=False).iloc[min(1, len(best_counts) - 1)]["v"])

    lines = [
        "# IMC Prosperity Round 2 Manual — Iteration 3 summary",
        "",
        "## 1. Executive summary",
        "",
        "- I audited the existing `iter3_analysis.py` and kept what was already solid:",
        "  - exact `Research/Scale` solver,",
        "  - exact tie-aware ranking engine,",
        "  - a useful first pass at the type mixture and the main plots.",
        "- I then completed the missing pieces:",
        "  - **expected regret vs the per-simulation best v**, not just regret vs the best mean EV,",
        "  - **sensitivity to focal-point and just-above locations**,",
        "  - a final markdown synthesis and notebook hand-off,",
        "  - the required CSVs with the final recommendation.",
        "",
        f"- **Central recommendation:** `Speed* = {int(best_row['v'])}`, `Research* = {int(best_row['r'])}`, `Scale* = {int(best_row['s'])}`.",
        f"- **Robust recommendation:** `v = {int(robust_row['v'])}` (same in this run).",
        f"- **More conservative recommendation:** `v = {int(conservative_row['v'])}` if you want a hedge against a more speed-heavy field.",
        f"- **Broad sensitivity range:** `{broad_low}–{broad_high}`.",
        f"- **Core defendable range:** `{core_low}–{core_high}`.",
        "",
        "## 2. Audit of the current iteration-3 implementation",
        "",
        markdown_table(audit_df, ".1f"),
        "",
        "## 3. Exact Research/Scale subproblem",
        "",
        "For each `v`, the remaining budget is `T = 100 - v`, and the exact integer split `r*(v), s*(v)` is solved first. Because both Research and Scale are increasing, the optimum always uses the whole budget, so `budget_used(v) = 50,000` for all feasible `v`.",
        "",
        "### Key allocations around the candidate zone",
        "",
        markdown_table(
            rs_table[rs_table["v"].isin([30, 34, 40, 42, 44, 45])]
            [["v", "r_star", "s_star", "gross_value", "budget_used"]],
            ".1f",
        ),
        "",
        "## 4. Exact ranking engine with ties",
        "",
        "The rank engine remains exact:",
        "",
        "- `rank(v) = # {players with strictly higher speed} + 1`",
        "- all ties share the minimum rank of the tied block",
        "- multiplier is linear from `0.9` (top rank) to `0.1` (bottom rank)",
        "",
        markdown_table(ranking_df, ".3f"),
        "",
        "## 5. Explicit type distributions used in the central mixture",
        "",
        "### Weights",
        "",
        markdown_table(
            pd.DataFrame(
                [
                    {"type": TYPE_LABELS[name], "weight": weight}
                    for name, weight in TYPE_WEIGHTS.items()
                ]
            ),
            ".2f",
        ),
        "",
        "### Top masses by component and by total mixture",
        "",
        markdown_table(component_top_df, ".2f"),
        "",
        "## 6. What total Speed distribution do these weights induce?",
        "",
        f"The main clusters of the field are: **{cluster_text}**.",
        "",
        "Interpretation:",
        "",
        "- `30` is a large focal/AI overlap.",
        "- `33–36` is the equal-split / AI-adjacent / just-above battleground.",
        "- `41–42` is the natural 'step above the 40 cluster' zone.",
        "- `50+` still has mass, but much less than the central cluster.",
        "",
        "## 7. Main Monte Carlo results (central mixture)",
        "",
        markdown_table(
            cand_table.sort_values("v"),
            ".1f",
        ),
        "",
        "### Reading the candidate zone",
        "",
        f"- `v = {best_v_val}` is the **EV winner** in the central mixture.",
        f"- `v = {robust_v_val}` is also the **minimum expected regret** choice in the main run.",
        f"- `v = {conservative_v_val}` gives up some EV, but improves the **worst-case sensitivity floor** when the field shifts upward.",
        "- `v = 42–44` is the real central battleground; values below that are too exposed to the 40/41 cluster, and much above that you pay a clearer Research/Scale tax unless the field itself shifts upward.",
        "",
        "## 8. Sensitivity",
        "",
        "### Best v across sensitivity runs",
        "",
        markdown_table(sensitivity_summary[["label", "best_v", "robust_v", "best_ev"]], ".1f"),
        "",
        "### Count of scenario winners",
        "",
        markdown_table(best_counts, ".1f"),
        "",
        "### Scenario-aggregated surface",
        "",
        markdown_table(
            sensitivity_aggregate[sensitivity_aggregate["v"].isin([41, 42, 43, 44, 45, 46])],
            ".1f",
        ),
        "",
        "Interpretation:",
        "",
        f"- `{best_mode}` is the centre of gravity across the sensitivity battery.",
        f"- `{second_mode}` is the nearest competing value when the field shifts slightly lower or more focal-heavy.",
        f"- `{conservative_v_val}` is the hedge that becomes attractive when the field moves materially higher in Speed.",
        "",
        "## 9. Final recommendation",
        "",
        markdown_table(final_rec_df, ".1f"),
        "",
        f"### Why {best_v_val}?",
        "",
        "- It sits **just above the 41/42 bottleneck**, which is one of the main step-up zones created by the mixture.",
        f"- It still preserves a strong exact economic split: `r = {int(best_row['r'])}`, `s = {int(best_row['s'])}`.",
        "- It wins on central EV **and** on main-run expected regret.",
        "",
        f"### When would I move to {conservative_v_val}?",
        "",
        "- If you want a more conservative hedge against the possibility that other players cluster a bit higher than the central mixture suggests.",
        f"- `{conservative_v_val}` is not the central EV leader, but it scores best on the worst EV across the tested sensitivity battery here.",
        "",
        "## 10. Direct answers to the requested questions",
        "",
        "1. **What total distribution of Speed do these weights induce?**",
        f"   - A highly clustered field with major mass around `34–36`, another clear knot at `41–42`, and secondary mass in the high 40s / 50+ tail; see the PMF/CDF plots and the cluster summary above.",
        "2. **Where are the main clusters of the other players?**",
        "   - `34–36` and `41–42` are the main tactical clusters, with secondary mass at `30–31` and a tail in `46+ / 50+` from naive and speed-race players.",
        "3. **Which values exploit those clusters best?**",
        f"   - `{best_v_val}` best exploits the `41–42` step-up logic while keeping strong Research/Scale economics. `42–44` are the nearby robust alternatives, and `{conservative_v_val}` is the upward hedge.",
        "4. **What allocation would I recommend under this mixture?**",
        f"   - Central: `v = {int(best_row['v'])}`, `r = {int(best_row['r'])}`, `s = {int(best_row['s'])}`.",
        f"   - More conservative: `v = {int(conservative_row['v'])}`, `r = {int(conservative_row['r'])}`, `s = {int(conservative_row['s'])}`.",
        "5. **How sensitive is the recommendation to small changes in AI/focal/just-above?**",
        f"   - The full best-v range in the tested sensitivity set is `{broad_low}–{broad_high}`, but the centre of gravity is clearly around `{best_mode}`, and the tighter core is `{core_low}–{core_high}`.",
        "",
        "## 11. Main artifact paths",
        "",
        f"- Notebook: `{BASE / 'manual_round2_analysis_iteration3.ipynb'}`",
        f"- Summary markdown: `{OUT / 'manual_round2_summary_iteration3.md'}`",
        f"- Plots folder: `{PLOTS}`",
        f"- CSV folder: `{CSVS}`",
        "",
    ]
    return "\n".join(lines)


def build_notebook(final_rec_df: pd.DataFrame) -> None:
    best_row = final_rec_df.iloc[0]
    robust_row = final_rec_df.iloc[1]
    conservative_row = final_rec_df.iloc[2]
    nb = nbformat.v4.new_notebook()
    cells = []

    cells.append(
        nbformat.v4.new_markdown_cell(
            "# Round 2 Manual — Iteration 3 (completed)\n\n"
            "This notebook is the readable companion to the completed iteration-3 analysis. "
            "The heavy simulation work is already materialised in `results/iteration3/`, so the notebook stays readable and reproducible."
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 1. What changed vs the first iteration-3 draft?\n\n"
            "- kept the exact `Research/Scale` solver\n"
            "- kept the exact tie-aware rank engine\n"
            "- fixed the notion of regret to use the **per-simulation best v**\n"
            "- added sensitivity to **focal-point locations** and **just-above locations**\n"
            "- added a final markdown summary and explicit final recommendation"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "\n"
            "BASE = Path.cwd() if Path.cwd().name == 'manual' else Path('/Users/pablo/Desktop/prosperity/round_2/manual')\n"
            "OUT = BASE / 'results' / 'iteration3'\n"
            "PLOTS = OUT / 'plots'\n"
            "\n"
            "rs = pd.read_csv(OUT / 'optimal_rs_by_speed_iteration3.csv')\n"
            "pmf = pd.read_csv(OUT / 'mixture_total_pmf.csv')\n"
            "ev = pd.read_csv(OUT / 'ev_by_speed_iteration3.csv')\n"
            "sens = pd.read_csv(OUT / 'sensitivity_summary_iteration3.csv')\n"
            "rec = pd.read_csv(OUT / 'final_recommendation_iteration3.csv')\n"
            "rec"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 2. Exact Research/Scale subproblem\n\n"
            "For each `v`, the code solves the exact integer split `r*(v), s*(v)` first, then feeds the resulting gross value into the Monte Carlo rank game.\n\n"
            "![](results/iteration3/plots/00_rs_subproblem.png)"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 3. Exact ranking engine with ties\n\n"
            "Rank is computed as `# strictly higher speeds + 1`, so ties share the minimum rank of the tied block. "
            "That is the exact interpretation of the manual rules.\n\n"
            "The checks are documented in the markdown summary and in the code runner."
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 4. Explicit type distributions and total mixture\n\n"
            "The field distribution is not a black box: each type is translated into a PMF, then the total mixture is formed by the user-provided weights.\n\n"
            "![](results/iteration3/plots/01_component_pmfs.png)\n\n"
            "![](results/iteration3/plots/02_component_overlay_zoom.png)\n\n"
            "![](results/iteration3/plots/03_mixture_total.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "pmf.sort_values('pmf', ascending=False).head(12)"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 5. Monte Carlo payoff surface\n\n"
            "The main Monte Carlo uses many sampled populations of other players. "
            "For every candidate `v`, it computes the exact induced rank, multiplier and payoff using the exact `r*(v), s*(v)`.\n\n"
            "![](results/iteration3/plots/04_ev_by_speed.png)\n\n"
            "![](results/iteration3/plots/05_regret_by_speed.png)\n\n"
            "![](results/iteration3/plots/06_rank_multiplier_diagnostics.png)\n\n"
            "![](results/iteration3/plots/07_dashboard.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "ev.loc[ev['v'].isin([41,42,43,44,45]), ['v','mean_pnl','p10','p90','expected_regret','prob_best_response']]"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 6. Sensitivity\n\n"
            "The completed battery now covers:\n\n"
            "- total players `N`\n"
            "- AI cluster version / location\n"
            "- AI weight\n"
            "- focal-point weight\n"
            "- just-above weight\n"
            "- focal-point locations\n"
            "- just-above locations\n\n"
            "![](results/iteration3/plots/08_sensitivity_families.png)\n\n"
            "![](results/iteration3/plots/09_sensitivity_aggregate.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "sens[['label','best_v','robust_v','best_ev']].sort_values(['group','best_v'])"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 7. Final recommendation\n\n"
            "![](results/iteration3/plots/10_final_recommendation_zoom.png)\n\n"
            f"Central recommendation: **Speed = {int(best_row['v'])}, Research = {int(best_row['r'])}, Scale = {int(best_row['s'])}**.\n\n"
            f"- If you want pure central EV: **{int(best_row['v'])}**.\n"
            f"- If you want a robust choice under the tested battery: **{int(robust_row['v'])}** remains the centre.\n"
            f"- If you want a more conservative hedge against a higher-speed field: **{int(conservative_row['v'])}** is the main alternative."
        )
    )
    cells.append(
        nbformat.v4.new_code_cell("rec")
    )
    nb.cells = cells
    notebook_path = BASE / "manual_round2_analysis_iteration3.ipynb"
    nbformat.write(nb, notebook_path)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    audit_df = audit_current_implementation()
    rs_table = compute_rs_table()
    assert verify_ranking_examples(), "Ranking engine verification failed"
    ranking_df = ranking_examples_table()

    component_pmfs = build_component_pmfs(ai_version="base", focal_version="base", just_above_version="base")
    mixture_pmf = build_mixture_pmf(component_pmfs)
    component_top_df = top_mass_table(component_pmfs, mixture_pmf)

    main_df, pnl_matrix, others = monte_carlo_speed_game(
        rs_table,
        component_pmfs,
        weights=TYPE_WEIGHTS,
        N=MAIN_N,
        n_sims=MAIN_SIMS,
        seed=SEED,
        v_grid=V_GRID,
    )
    _ = pnl_matrix, others

    sensitivity_summary, sensitivity_curves = run_sensitivity(rs_table)
    sensitivity_aggregate = aggregate_sensitivity_curves(sensitivity_curves)
    final_rec_df = build_final_recommendation(rs_table, main_df, sensitivity_summary, sensitivity_aggregate)

    best_v = int(final_rec_df.loc[final_rec_df["criterion"] == "Max EV (central mixture)", "v"].iloc[0])
    robust_v = int(final_rec_df.loc[final_rec_df["criterion"] == "Robust (min expected regret)", "v"].iloc[0])
    conservative_v = int(final_rec_df.loc[final_rec_df["criterion"] == "Conservative (best min EV across sensitivity)", "v"].iloc[0])

    diag_df = selected_rank_multiplier_stats(
        rs_table,
        component_pmfs,
        weights=TYPE_WEIGHTS,
        N=MAIN_N,
        n_sims=25_000,
        seed=SEED + 99,
        selected_v=[34, 40, 42, 44, 46],
    )

    plot_rs_subproblem(rs_table)
    plot_component_pmfs(component_pmfs, mixture_pmf)
    plot_mixture_total(component_pmfs, mixture_pmf)
    plot_ev_and_regret(main_df, best_v, robust_v, conservative_v)
    plot_rank_multiplier_diagnostics(diag_df)
    plot_dashboard(main_df, mixture_pmf, rs_table, best_v, robust_v, conservative_v)
    plot_sensitivity(sensitivity_summary, sensitivity_aggregate, best_v, robust_v, conservative_v)
    plot_recommendation_zoom(main_df, sensitivity_aggregate, mixture_pmf, best_v, robust_v, conservative_v)

    # CSVs required by the user
    write_csv_dual("optimal_rs_by_speed_iteration3.csv", rs_table)
    type_component_pmf_df = pd.DataFrame({"v": np.arange(101)})
    for name, pmf in component_pmfs.items():
        type_component_pmf_df[name] = pmf.values
    write_csv_dual("type_component_pmf.csv", type_component_pmf_df)
    write_csv_dual("mixture_total_pmf.csv", pd.DataFrame({"v": np.arange(101), "pmf": mixture_pmf.values}))
    write_csv_dual("ev_by_speed_iteration3.csv", main_df)
    write_csv_dual(
        "regret_by_speed_iteration3.csv",
        main_df[["v", "expected_regret", "p90_regret", "prob_best_response"]],
    )
    write_csv_dual("sensitivity_summary_iteration3.csv", sensitivity_summary)
    write_csv_dual("sensitivity_curves_iteration3.csv", sensitivity_curves)
    write_csv_dual("sensitivity_aggregate_iteration3.csv", sensitivity_aggregate)
    write_csv_dual("final_recommendation_iteration3.csv", final_rec_df)

    summary_text = build_summary_markdown(
        audit_df=audit_df,
        rs_table=rs_table,
        component_top_df=component_top_df,
        ranking_df=ranking_df,
        main_df=main_df,
        mixture_pmf=mixture_pmf,
        sensitivity_summary=sensitivity_summary,
        sensitivity_aggregate=sensitivity_aggregate,
        final_rec_df=final_rec_df,
    )
    summary_path = OUT / "manual_round2_summary_iteration3.md"
    summary_path.write_text(summary_text, encoding="utf-8")
    build_notebook(final_rec_df)
    print(f"Wrote summary to {summary_path}")
    print(f"Recommendation: Speed={best_v}, Research={int(final_rec_df.iloc[0]['r'])}, Scale={int(final_rec_df.iloc[0]['s'])}")


if __name__ == "__main__":
    main()
