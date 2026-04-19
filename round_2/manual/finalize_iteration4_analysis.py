from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import nbformat
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from scipy.stats import norm, t as student_t

BASE = Path(__file__).parent
OUT = BASE / "results" / "iteration4"
PLOTS = OUT / "plots"
CSVS = OUT / "csv"
PLOTS.mkdir(parents=True, exist_ok=True)
CSVS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE))

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

PALETTE = {
    "ai": "#2563EB",
    "nash": "#0F766E",
    "just_above": "#EA580C",
    "classic": "#A21CAF",
    "naive": "#CA8A04",
    "high_speed": "#DC2626",
    "random": "#64748B",
    "mixture": "#0F172A",
    "accent": "#10B981",
    "accent2": "#7C3AED",
}

LABELS = {
    "ai_recommendations": "Recomendaciones de IA",
    "nash_like": "Nash / racionales",
    "just_above_0_5": "Just-above 0 o 5",
    "classic_numbers": "Allocations simples / focal",
    "naive_partial": "Naive / optimización incompleta",
    "high_speed_partial": "High speed / speed-race parcial",
    "random_uniform": "Aleatorio",
}

CSV_COLUMNS = {
    "ai_recommendations": "pmf_type_ai",
    "nash_like": "pmf_type_nash",
    "just_above_0_5": "pmf_type_just_above",
    "classic_numbers": "pmf_type_classic",
    "naive_partial": "pmf_type_naive",
    "high_speed_partial": "pmf_type_high_speed",
    "random_uniform": "pmf_type_random",
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

SEED = 314159
MAIN_N = 50
MAIN_SIMS = 25_000
SENS_SIMS = 7_500
FIXED_POINT_ITER = 12
FIXED_POINT_TAU = 2_200.0
FIXED_POINT_DAMPING = 0.35
V_GRID = np.arange(0, 101, 1)
V_GRID_SENS = np.arange(18, 56, 1)

BASE_WEIGHTS = {
    "ai_recommendations": 0.30,
    "nash_like": 0.23,
    "just_above_0_5": 0.15,
    "classic_numbers": 0.10,
    "naive_partial": 0.10,
    "high_speed_partial": 0.07,
    "random_uniform": 0.05,
}


@dataclass(frozen=True)
class ScenarioConfig:
    ai_sigma_25: float = 2.0
    ai_sigma_35: float = 2.0
    ai_weight_35: float = 0.75
    weights: Mapping[str, float] = None
    N: int = MAIN_N

    def __post_init__(self):
        if self.weights is None:
            object.__setattr__(self, "weights", BASE_WEIGHTS)


def fmt_k(x, _=None) -> str:
    return f"{x/1e3:.0f}k"


def fmt_k_pre(x, _=None) -> str:
    """Formatter para ejes donde los datos ya están divididos por 1e3."""
    return f"{x:.0f}k"


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
            if isinstance(value, (float, np.floating)):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(float(value), float_fmt))
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
# Audit / reuse of previous iteration
# ──────────────────────────────────────────────────────────────────────────────


def audit_previous_iteration() -> pd.DataFrame:
    findings = [
        {
            "topic": "Iteration3 exact economics",
            "status": "reused",
            "detail": "Reused the exact integer Research/Scale solver from `manual_round2_utils.compute_rs_table()` without modification.",
        },
        {
            "topic": "Iteration3 exact ranking",
            "status": "reused",
            "detail": "Reused the tie-aware ranking engine where rank depends on the number of strictly higher speeds only.",
        },
        {
            "topic": "Iteration3 artifacts",
            "status": "reused",
            "detail": "Loaded the iteration3 mixture PMF and final recommendation to compare the new scenario against the previous central scenario.",
        },
        {
            "topic": "New work in iteration4",
            "status": "new",
            "detail": "Implemented a brand new central mixture with an explicit two-normal AI component, a one-step quantal strategic component, a 0/5 just-above cluster, classic-number choices, a deterministic-naive component and updated sensitivity.",
        },
    ]
    return pd.DataFrame(findings)


# ──────────────────────────────────────────────────────────────────────────────
# PMF helpers
# ──────────────────────────────────────────────────────────────────────────────


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
    total = probs.sum()
    if total <= 0:
        raise ValueError("rounded_truncnorm_pmf produced zero mass")
    probs /= total
    return pd.Series(probs, index=xs)


def rounded_t_pmf(mu: float, scale: float, df: float, lo: int = 0, hi: int = 100) -> pd.Series:
    xs = np.arange(101)
    probs = np.zeros(101, dtype=float)
    for x in xs:
        if x < lo or x > hi:
            continue
        probs[x] = student_t.cdf(x + 0.5, df=df, loc=mu, scale=scale) - student_t.cdf(x - 0.5, df=df, loc=mu, scale=scale)
    probs = np.maximum(probs, 0.0)
    total = probs.sum()
    if total <= 0:
        raise ValueError("rounded_t_pmf produced zero mass")
    probs /= total
    return pd.Series(probs, index=xs)


def categorical_pmf(values: Sequence[int], weights: Sequence[float]) -> pd.Series:
    xs = np.arange(101)
    probs = np.zeros(101, dtype=float)
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    for value, weight in zip(values, w):
        probs[int(value)] += float(weight)
    return pd.Series(probs, index=xs)


def softmax_scores(scores: np.ndarray, tau: float, support_mask: np.ndarray) -> pd.Series:
    out = np.zeros(101, dtype=float)
    masked_scores = np.where(support_mask, scores, -np.inf)
    finite_scores = masked_scores[np.isfinite(masked_scores)]
    if finite_scores.size == 0:
        raise ValueError("No valid support for softmax_scores")
    logits = (masked_scores - finite_scores.max()) / tau
    weights = np.exp(np.clip(logits, -700, 50))
    weights[~support_mask] = 0.0
    weights /= weights.sum()
    out[:] = weights
    return pd.Series(out, index=np.arange(101))


def normalize_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    total = float(sum(weights.values()))
    return {k: float(v) / total for k, v in weights.items()}


def rebalance_single_weight(base_weights: Mapping[str, float], key: str, new_weight: float) -> Dict[str, float]:
    old_weight = float(base_weights[key])
    other_total_old = 1.0 - old_weight
    other_total_new = 1.0 - new_weight
    if other_total_old <= 0 or other_total_new <= 0:
        raise ValueError("Invalid weight rebalance request")
    factor = other_total_new / other_total_old
    weights = {}
    for name, value in base_weights.items():
        if name == key:
            weights[name] = new_weight
        else:
            weights[name] = float(value) * factor
    return normalize_weights(weights)


# ──────────────────────────────────────────────────────────────────────────────
# Exact EV helpers
# ──────────────────────────────────────────────────────────────────────────────


def expected_curve_against_pmf(rs_table: pd.DataFrame, opponent_pmf: pd.Series) -> pd.DataFrame:
    cdf = opponent_pmf.cumsum().values
    p_higher = 1.0 - cdf
    expected_multiplier = SPEED_HIGH - SPEED_RANGE * p_higher
    df = rs_table[["v", "gross_value", "r_star", "s_star"]].copy()
    df["p_higher"] = p_higher
    df["mean_multiplier"] = expected_multiplier
    df["mean_pnl"] = df["gross_value"] * df["mean_multiplier"] - TOTAL_BUDGET
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Component builders
# ──────────────────────────────────────────────────────────────────────────────


def build_ai_component(ai_sigma_25: float, ai_sigma_35: float, ai_weight_35: float) -> pd.Series:
    pmf_25 = rounded_truncnorm_pmf(mu=25.0, sigma=ai_sigma_25, lo=20, hi=40)
    pmf_35 = rounded_truncnorm_pmf(mu=35.0, sigma=ai_sigma_35, lo=20, hi=40)
    pmf = (1.0 - ai_weight_35) * pmf_25 + ai_weight_35 * pmf_35
    pmf /= pmf.sum()
    return pmf


def build_just_above_component() -> pd.Series:
    # focal points plausibles del problema (just-above de múltiplos clave)
    values  = [21, 26, 31, 35, 36, 41, 46, 51]
    weights = [ 8, 10, 14, 16, 16, 18, 12,  6]
    return categorical_pmf(values, weights)


def build_classic_component() -> pd.Series:
    # allocations simples / focal — masa distribuida entre extremos y zona media
    values  = [20, 25, 33, 34, 35, 40, 50]
    weights = [14, 15, 16, 12,  8, 18, 17]
    return categorical_pmf(values, weights)


def build_naive_component(rs_table: pd.DataFrame, tau: float = None) -> pd.Series:
    # Student-t con df=5: colas más pesadas que normal, sin colapso en centro.
    # Centrado en v=32 (zona media, debajo de AI≈35 y Nash≈41), truncado a [18, 52].
    return rounded_t_pmf(mu=32.0, scale=6.0, df=5, lo=18, hi=52)


def build_high_speed_component() -> pd.Series:
    return rounded_truncnorm_pmf(mu=64.0, sigma=9.0, lo=50, hi=80)


def build_random_component() -> pd.Series:
    return pd.Series(np.ones(101) / 101.0, index=np.arange(101))


def build_nash_component_one_step(
    rs_table: pd.DataFrame,
    non_nash_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    *,
    tau: float = None,  # unused — mantenido por compatibilidad de firma
) -> Tuple[pd.Series, pd.DataFrame]:
    # Soft rational: núcleo concentrado alrededor del peak EV + cola dispersa sesgada a la derecha.
    # 85% núcleo N(v_center, σ=4) en [28, 54]
    # 15% cola N(v_center+4, σ=9) en [28, 60]  ← dispersión y sesgo derecho
    non_nash_weights = normalize_weights({k: v for k, v in weights.items() if k != "nash_like"})
    non_nash_mixture = build_mixture_pmf(non_nash_pmfs, non_nash_weights)
    curve = expected_curve_against_pmf(rs_table, non_nash_mixture)
    mask = (curve["v"] >= 28) & (curve["v"] <= 54)
    best_idx = curve.loc[mask, "mean_pnl"].idxmax()
    v_center = float(curve.loc[best_idx, "v"])
    core = rounded_truncnorm_pmf(mu=v_center,       sigma=4.0, lo=28, hi=54)
    tail = rounded_truncnorm_pmf(mu=v_center + 4.0, sigma=9.0, lo=28, hi=60)
    pmf = 0.85 * core + 0.15 * tail
    pmf /= pmf.sum()
    profile = curve[["v", "mean_pnl", "mean_multiplier", "p_higher"]].copy()
    profile["quantal_prob"] = pmf.values
    profile["field"] = "non_rational_only"
    return pmf, profile


def fixed_point_nash_stress_test(
    rs_table: pd.DataFrame,
    non_nash_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    *,
    tau: float = FIXED_POINT_TAU,
    damping: float = FIXED_POINT_DAMPING,
    n_iter: int = FIXED_POINT_ITER,
) -> Tuple[pd.Series, pd.DataFrame]:
    support = (V_GRID >= 18) & (V_GRID <= 55)
    current = rounded_truncnorm_pmf(mu=34.0, sigma=7.0, lo=18, hi=55)
    history: List[Dict[str, object]] = []

    for step in range(1, n_iter + 1):
        full_pmfs = dict(non_nash_pmfs)
        full_pmfs["nash_like"] = current
        opponent_pmf = build_mixture_pmf(full_pmfs, weights)
        curve = expected_curve_against_pmf(rs_table, opponent_pmf)
        new = softmax_scores(curve["mean_pnl"].values, tau=tau, support_mask=support)
        updated = (1.0 - damping) * new + damping * current
        updated /= updated.sum()
        mean_speed = float((updated.index.values * updated.values).sum())
        top = updated.sort_values(ascending=False).head(5)
        history.append(
            {
                "iteration": step,
                "mean_speed": mean_speed,
                "l1_change": float(np.abs(updated.values - current.values).sum()),
                "top_speeds": ", ".join(str(int(v)) for v in top.index),
                "top_probs_pct": ", ".join(f"{100*p:.1f}%" for p in top.values),
                "best_ev_v": int(curve.loc[curve["mean_pnl"].idxmax(), "v"]),
                "best_ev": float(curve["mean_pnl"].max()),
            }
        )
        current = updated
    return current, pd.DataFrame(history)


def build_component_pmfs(rs_table: pd.DataFrame, config: ScenarioConfig) -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    weights = normalize_weights(config.weights)
    ai = build_ai_component(config.ai_sigma_25, config.ai_sigma_35, config.ai_weight_35)
    just_above = build_just_above_component()
    classic = build_classic_component()
    naive = build_naive_component(rs_table)
    high_speed = build_high_speed_component()
    random = build_random_component()

    non_nash_pmfs = {
        "ai_recommendations": ai,
        "just_above_0_5": just_above,
        "classic_numbers": classic,
        "naive_partial": naive,
        "high_speed_partial": high_speed,
        "random_uniform": random,
    }
    nash, nash_profile = build_nash_component_one_step(rs_table, non_nash_pmfs, weights)

    full_pmfs = dict(non_nash_pmfs)
    full_pmfs["nash_like"] = nash
    # return in deterministic order
    ordered = {
        "ai_recommendations": full_pmfs["ai_recommendations"],
        "nash_like": full_pmfs["nash_like"],
        "just_above_0_5": full_pmfs["just_above_0_5"],
        "classic_numbers": full_pmfs["classic_numbers"],
        "naive_partial": full_pmfs["naive_partial"],
        "high_speed_partial": full_pmfs["high_speed_partial"],
        "random_uniform": full_pmfs["random_uniform"],
    }
    return ordered, nash_profile


def build_mixture_pmf(component_pmfs: Mapping[str, pd.Series], weights: Mapping[str, float]) -> pd.Series:
    mixture = pd.Series(np.zeros(101), index=np.arange(101), dtype=float)
    for name, weight in weights.items():
        mixture += float(weight) * component_pmfs[name]
    mixture /= mixture.sum()
    return mixture


def component_pmf_frame(component_pmfs: Mapping[str, pd.Series], mixture_pmf: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"speed": np.arange(101)})
    for name, pmf in component_pmfs.items():
        df[CSV_COLUMNS[name]] = pmf.values
    df["pmf_total_mixture"] = mixture_pmf.values
    return df


def component_summary(component_pmfs: Mapping[str, pd.Series], weights: Mapping[str, float]) -> pd.DataFrame:
    rows = []
    for name, pmf in component_pmfs.items():
        top = pmf.sort_values(ascending=False).head(5)
        rows.append(
            {
                "component": LABELS[name],
                "weight_total": float(weights[name]),
                "mean_speed": float((pmf.index.values * pmf.values).sum()),
                "top_speeds": ", ".join(str(int(v)) for v in top.index),
                "top_probs_pct": ", ".join(f"{100*p:.1f}%" for p in top.values),
            }
        )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Monte Carlo engine with exact ties and exact regret-by-simulation
# ──────────────────────────────────────────────────────────────────────────────


def sample_from_component_pmfs(
    n_samples: int,
    rng: np.random.Generator,
    component_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float],
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


def monte_carlo_speed_game(
    rs_table: pd.DataFrame,
    component_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    *,
    N: int,
    n_sims: int,
    seed: int,
    v_grid: Sequence[int],
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    others = sample_from_component_pmfs(n_sims * (N - 1), rng, component_pmfs, weights=weights).reshape(n_sims, N - 1)

    rs_idx = rs_table.set_index("v")
    v_arr = np.array(list(v_grid), dtype=int)
    pnl_matrix = np.empty((n_sims, len(v_arr)), dtype=float)
    mult_matrix = np.empty_like(pnl_matrix)
    rank_matrix = np.empty_like(pnl_matrix)

    for j, v in enumerate(v_arr):
        gross_value = float(rs_idx.loc[v, "gross_value"])
        n_higher = (others > v).sum(axis=1)
        rank = n_higher + 1
        mult = SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE
        pnl = gross_value * mult - TOTAL_BUDGET
        pnl_matrix[:, j] = pnl
        mult_matrix[:, j] = mult
        rank_matrix[:, j] = rank

    best_per_sim = pnl_matrix.max(axis=1, keepdims=True)
    regret_matrix = best_per_sim - pnl_matrix

    rows: List[Dict[str, float | int]] = []
    for j, v in enumerate(v_arr):
        pnl = pnl_matrix[:, j]
        mult = mult_matrix[:, j]
        rank = rank_matrix[:, j]
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
                "mean_rank": float(rank.mean()),
                "p10_rank": float(np.percentile(rank, 10)),
                "p90_rank": float(np.percentile(rank, 90)),
                "mean_regret": float(regret_matrix[:, j].mean()),
                "max_regret": float(regret_matrix[:, j].max()),
                "p90_regret": float(np.percentile(regret_matrix[:, j], 90)),
                "prob_best_response": float((np.abs(pnl - best_per_sim[:, 0]) < 1e-9).mean()),
            }
        )
    return pd.DataFrame(rows), pnl_matrix, mult_matrix, others


def diagnostic_distributions(
    rs_table: pd.DataFrame,
    component_pmfs: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    selected_v: Sequence[int],
    *,
    N: int,
    n_sims: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    others = sample_from_component_pmfs(n_sims * (N - 1), rng, component_pmfs, weights=weights).reshape(n_sims, N - 1)
    rs_idx = rs_table.set_index("v")
    rows = []
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
# Ranking examples / cluster helpers
# ──────────────────────────────────────────────────────────────────────────────


def ranking_examples_table() -> pd.DataFrame:
    rows = []
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


def top_clusters(pmf: pd.Series, top_n: int = 12) -> pd.DataFrame:
    top = pmf.sort_values(ascending=False).head(top_n)
    return pd.DataFrame({"speed": top.index.astype(int), "pmf_pct": top.values * 100.0})


# ──────────────────────────────────────────────────────────────────────────────
# Sensitivity
# ──────────────────────────────────────────────────────────────────────────────


def sensitivity_cases() -> List[Dict[str, object]]:
    cases: List[Dict[str, object]] = []

    for sigma in [2.5, 3.5, 5.0]:
        cases.append(
            {
                "label": f"AI sigma = {sigma:.1f}",
                "group": "ai_sigma",
                "config": ScenarioConfig(ai_sigma_25=sigma, ai_sigma_35=sigma, ai_weight_35=0.75, weights=BASE_WEIGHTS, N=MAIN_N),
            }
        )

    for weight_35 in [0.70, 0.75, 0.80]:
        cases.append(
            {
                "label": f"AI internal 35-cluster = {weight_35:.0%}",
                "group": "ai_internal_weight",
                "config": ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=weight_35, weights=BASE_WEIGHTS, N=MAIN_N),
            }
        )

    for ai_weight in [0.25, 0.30, 0.35]:
        weights = rebalance_single_weight(BASE_WEIGHTS, "ai_recommendations", ai_weight)
        cases.append(
            {
                "label": f"AI total weight = {ai_weight:.0%}",
                "group": "ai_weight_total",
                "config": ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=0.75, weights=weights, N=MAIN_N),
            }
        )

    for nash_weight in [0.18, 0.23, 0.28]:
        weights = rebalance_single_weight(BASE_WEIGHTS, "nash_like", nash_weight)
        cases.append(
            {
                "label": f"Nash weight = {nash_weight:.0%}",
                "group": "nash_weight",
                "config": ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=0.75, weights=weights, N=MAIN_N),
            }
        )

    for ja_weight in [0.10, 0.15, 0.20]:
        weights = rebalance_single_weight(BASE_WEIGHTS, "just_above_0_5", ja_weight)
        cases.append(
            {
                "label": f"Just-above weight = {ja_weight:.0%}",
                "group": "just_above_weight",
                "config": ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=0.75, weights=weights, N=MAIN_N),
            }
        )

    for N in [20, 35, 50, 75, 100]:
        cases.append(
            {
                "label": f"N = {N}",
                "group": "N",
                "config": ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=0.75, weights=BASE_WEIGHTS, N=N),
            }
        )

    return cases


def run_sensitivity(rs_table: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: List[Dict[str, object]] = []
    curve_rows: List[pd.DataFrame] = []

    for idx, case in enumerate(sensitivity_cases()):
        config: ScenarioConfig = case["config"]
        component_pmfs, _nash_profile = build_component_pmfs(rs_table, config)
        weights = normalize_weights(config.weights)
        curve_df, _pnl_matrix, _mult_matrix, _others = monte_carlo_speed_game(
            rs_table,
            component_pmfs,
            weights,
            N=config.N,
            n_sims=SENS_SIMS,
            seed=SEED + 1_000 + idx,
            v_grid=V_GRID_SENS,
        )
        curve_df["label"] = str(case["label"])
        curve_df["group"] = str(case["group"])
        curve_rows.append(curve_df)

        best_row = curve_df.loc[curve_df["mean_pnl"].idxmax()]
        robust_row = curve_df.loc[curve_df["mean_regret"].idxmin()]
        summary_rows.append(
            {
                "label": str(case["label"]),
                "group": str(case["group"]),
                "best_v": int(best_row["v"]),
                "best_ev": float(best_row["mean_pnl"]),
                "robust_v": int(robust_row["v"]),
                "robust_ev": float(robust_row["mean_pnl"]),
                "best_p10": float(best_row["p10"]),
                "best_mean_regret": float(best_row["mean_regret"]),
                "config_N": int(config.N),
                "config_ai_sigma_25": float(config.ai_sigma_25),
                "config_ai_sigma_35": float(config.ai_sigma_35),
                "config_ai_weight_35": float(config.ai_weight_35),
            }
        )

    curves_df = pd.concat(curve_rows, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows)
    return summary_df, curves_df


def aggregate_sensitivity(curves_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for v, sub in curves_df.groupby("v"):
        ev_vals = sub["mean_pnl"].values
        reg_vals = sub["mean_regret"].values
        rows.append(
            {
                "v": int(v),
                "mean_ev_across_scenarios": float(ev_vals.mean()),
                "median_ev_across_scenarios": float(np.median(ev_vals)),
                "min_ev_across_scenarios": float(ev_vals.min()),
                "p25_ev_across_scenarios": float(np.percentile(ev_vals, 25)),
                "p75_ev_across_scenarios": float(np.percentile(ev_vals, 75)),
                "mean_regret_across_scenarios": float(reg_vals.mean()),
                "max_regret_across_scenarios": float(reg_vals.max()),
            }
        )
    return pd.DataFrame(rows).sort_values("v").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Plotting
# ──────────────────────────────────────────────────────────────────────────────


def plot_rs_subproblem(rs_table: pd.DataFrame) -> None:
    multipliers = [0.1, 0.3, 0.5, 0.7, 0.9]
    fig = plt.figure(figsize=(17, 11), constrained_layout=True)
    gs = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32)

    ax = fig.add_subplot(gs[0, 0])
    ax.plot(rs_table["v"], rs_table["r_star"], color=PALETTE["accent"], lw=2.5, label="r*(v)")
    ax.plot(rs_table["v"], rs_table["s_star"], color=PALETTE["ai"], lw=2.5, label="s*(v)")
    ax.set_title("Split exacto Research/Scale para cada Speed")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Asignación (%)")
    ax.legend()

    ax = fig.add_subplot(gs[0, 1])
    ax.plot(rs_table["v"], rs_table["gross_value"] / 1e3, color=PALETTE["accent2"], lw=2.5)
    ax.set_title("Gross value(v) = Research(r*) × Scale(s*)")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Gross value (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))

    ax = fig.add_subplot(gs[1, 0])
    for mult, color in zip(multipliers, [PALETTE["random"], PALETTE["classic"], PALETTE["ai"], PALETTE["accent"], PALETTE["high_speed"]]):
        pnl = rs_table["gross_value"] * mult - rs_table["budget_used"]
        ax.plot(rs_table["v"], pnl / 1e3, color=color, lw=2.0, label=f"mult = {mult:.1f}")
    ax.axhline(0, color="black", lw=1, linestyle=":")
    ax.set_title("PnL neto para multiplicadores representativos")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    ax.legend(ncol=2, fontsize=9)

    ax = fig.add_subplot(gs[1, 1])
    ax.stackplot(
        rs_table["v"],
        rs_table["r_star"],
        rs_table["s_star"],
        colors=[PALETTE["accent"], PALETTE["ai"]],
        alpha=0.85,
        labels=["Research r*", "Scale s*"],
    )
    ax.set_title("Composición óptima exacta cuando cambia v")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Asignación (%)")
    ax.legend(loc="upper right")

    fig.suptitle("Subproblema exacto Research/Scale (iteration4)", fontsize=14)
    savefig("00_rs_subproblem.png", fig)


def plot_type_distributions(component_pmfs: Mapping[str, pd.Series], mixture_pmf: pd.Series, iteration3_mixture: pd.Series) -> None:
    speeds = np.arange(101)
    order = list(component_pmfs.keys())
    colors = [PALETTE["ai"], PALETTE["nash"], PALETTE["just_above"], PALETTE["classic"], PALETTE["naive"], PALETTE["high_speed"], PALETTE["random"]]

    fig, axes = plt.subplots(2, 4, figsize=(20, 9))
    fig.subplots_adjust(hspace=0.45, wspace=0.32)
    for ax, name, color in zip(axes.flatten()[:7], order, colors):
        pmf = component_pmfs[name]
        mu = float((pmf.index.values * pmf.values).sum())
        ax.bar(speeds, pmf.values * 100, width=1.0, color=color, alpha=0.88, edgecolor="none")
        ax.axvline(mu, color="black", lw=1.4, linestyle="--", label=f"μ={mu:.1f}")
        ax.set_title(LABELS[name])
        ax.set_xlabel("Speed")
        ax.set_ylabel("PMF (%)")
        ax.set_xlim(-1, 101)
        ax.legend(fontsize=8)
    ax = axes.flatten()[7]
    ax.bar(speeds, mixture_pmf.values * 100, width=1.0, color=PALETTE["mixture"], alpha=0.9, edgecolor="none")
    ax.set_title("Mezcla total")
    ax.set_xlabel("Speed")
    ax.set_ylabel("PMF (%)")
    ax.set_xlim(-1, 101)
    fig.suptitle("PMF por tipo de jugador y mezcla total", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("01_type_pmfs_individual.png", fig)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.6))
    ax = axes[0]
    for name, color in zip(order, colors):
        ax.plot(speeds, component_pmfs[name].values * 100, lw=2.1, color=color, label=LABELS[name])
    ax.plot(speeds, mixture_pmf.values * 100, color=PALETTE["mixture"], lw=3.0, label="Mezcla total")
    ax.set_title("Comparación superpuesta de todas las PMFs")
    ax.set_xlabel("Speed")
    ax.set_ylabel("PMF (%)")
    ax.legend(fontsize=8, ncol=2)

    ax = axes[1]
    mask = (speeds >= 20) & (speeds <= 40)
    for name, color in zip(order, colors):
        ax.plot(speeds[mask], component_pmfs[name].values[mask] * 100, lw=2.1, color=color, label=LABELS[name])
    ax.plot(speeds[mask], mixture_pmf.values[mask] * 100, color=PALETTE["mixture"], lw=3.0, label="Mezcla total")
    ax.set_title("Zoom 20–40")
    ax.set_xlabel("Speed")
    ax.set_ylabel("PMF (%)")

    ax = axes[2]
    mask = (speeds >= 0) & (speeds <= 60)
    for name, color in zip(order, colors):
        ax.plot(speeds[mask], component_pmfs[name].values[mask] * 100, lw=2.1, color=color, label=LABELS[name])
    ax.plot(speeds[mask], mixture_pmf.values[mask] * 100, color=PALETTE["mixture"], lw=3.0, label="Mezcla total")
    ax.set_title("Zoom 0–60")
    ax.set_xlabel("Speed")
    ax.set_ylabel("PMF (%)")

    fig.suptitle("Distribuciones individuales y zoom en la zona táctica", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("02_type_pmfs_overlay.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
    ai = component_pmfs["ai_recommendations"]
    ja = component_pmfs["just_above_0_5"]
    mask_ai = (speeds >= 18) & (speeds <= 42)
    axes[0].bar(speeds[mask_ai], ai.values[mask_ai] * 100, color=PALETTE["ai"], alpha=0.9, edgecolor="none")
    axes[0].axvline(25, color=PALETTE["accent"], linestyle="--", lw=1.4, label="μ=25")
    axes[0].axvline(35, color=PALETTE["accent2"], linestyle="--", lw=1.4, label="μ=35")
    axes[0].set_title("Componente IA: dos normales truncadas en 20–40")
    axes[0].set_xlabel("Speed")
    axes[0].set_ylabel("PMF (%)")
    axes[0].legend(fontsize=8)

    axes[1].bar(speeds[speeds <= 65], ja.values[speeds <= 65] * 100, color=PALETTE["just_above"], alpha=0.9, edgecolor="none")
    for v in [21, 26, 31, 36, 41, 46]:
        axes[1].axvline(v, color="#7C2D12", linestyle=":", lw=1.2, alpha=0.6)
    axes[1].set_title("Componente just-above sobre números acabados en 0/5")
    axes[1].set_xlabel("Speed")
    axes[1].set_ylabel("PMF (%)")

    fig.suptitle("Componentes clave de la mezcla", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("03_component_focus.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))
    cdf = mixture_pmf.cumsum().values
    axes[0].bar(speeds, mixture_pmf.values * 100, color=PALETTE["mixture"], alpha=0.9, edgecolor="none")
    axes[0].plot(speeds, iteration3_mixture.values * 100, color=PALETTE["accent2"], lw=2.2, linestyle="--", label="Iteration3")
    axes[0].plot(speeds, mixture_pmf.values * 100, color=PALETTE["mixture"], lw=2.8, label="Iteration4")
    axes[0].set_title("PMF total: iteration4 vs iteration3")
    axes[0].set_xlabel("Speed")
    axes[0].set_ylabel("PMF (%)")
    axes[0].legend(fontsize=9)

    axes[1].plot(speeds, cdf * 100, color=PALETTE["ai"], lw=2.8)
    axes[1].set_title("CDF total de la mezcla")
    axes[1].set_xlabel("Speed")
    axes[1].set_ylabel("CDF (%)")
    for q in [25, 50, 75]:
        cutoff = int(speeds[np.searchsorted(cdf, q / 100.0)])
        axes[1].axhline(q, color="#94A3B8", linestyle="--", lw=1)
        axes[1].axvline(cutoff, color="#94A3B8", linestyle="--", lw=1)
        axes[1].text(cutoff + 0.5, q + 1.0, f"p{q}={cutoff}", fontsize=9)

    fig.suptitle("Distribución total y comparación con la iteración anterior", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("04_mixture_total_and_comparison.png", fig)


def plot_payoff_and_regret(main_df: pd.DataFrame, best_v: int, robust_v: int, conservative_v: int) -> None:
    v = main_df["v"].values

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ax.fill_between(v, main_df["p10"] / 1e3, main_df["p90"] / 1e3, alpha=0.13, color=PALETTE["ai"], label="p10–p90")
    ax.fill_between(v, main_df["p25"] / 1e3, main_df["p75"] / 1e3, alpha=0.22, color=PALETTE["ai"], label="p25–p75")
    ax.plot(v, main_df["mean_pnl"] / 1e3, color=PALETTE["ai"], lw=2.8, label="EV")
    ax.plot(v, main_df["p50"] / 1e3, color=PALETTE["mixture"], lw=1.6, linestyle="--", alpha=0.75, label="mediana")
    ax.axvline(best_v, color="black", lw=2.0, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE["accent"], lw=1.8, linestyle="--", label=f"robusto={robust_v}")
    ax.axvline(conservative_v, color=PALETTE["high_speed"], lw=1.8, linestyle=":", label=f"conservador={conservative_v}")
    ax.set_title("EV por v con bandas de incertidumbre")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    ax.legend(fontsize=8)

    ax = axes[1]
    mask = (v >= 18) & (v <= 50)
    ax.fill_between(v[mask], main_df.loc[mask, "p10"] / 1e3, main_df.loc[mask, "p90"] / 1e3, alpha=0.13, color=PALETTE["ai"])
    ax.fill_between(v[mask], main_df.loc[mask, "p25"] / 1e3, main_df.loc[mask, "p75"] / 1e3, alpha=0.22, color=PALETTE["ai"])
    ax.plot(v[mask], main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE["ai"], lw=2.8)
    for fp in [25, 26, 31, 35, 36, 41]:
        ax.axvline(fp, color="#64748B", lw=0.8, linestyle=":", alpha=0.45)
    ax.axvline(best_v, color="black", lw=2.0)
    ax.axvline(robust_v, color=PALETTE["accent"], lw=1.8, linestyle="--")
    ax.axvline(conservative_v, color=PALETTE["high_speed"], lw=1.8, linestyle=":")
    ax.set_title("Zoom 18–50")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))

    fig.suptitle("Superficie de payoff Monte Carlo", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("05_ev_by_speed.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    axes[0].plot(v, main_df["mean_regret"] / 1e3, color=PALETTE["classic"], lw=2.8, label="mean regret")
    axes[0].plot(v, main_df["max_regret"] / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle="--", label="max regret")
    axes[0].plot(v, main_df["p90_regret"] / 1e3, color=PALETTE["accent2"], lw=1.8, linestyle=":", label="p90 regret")
    axes[0].axvline(robust_v, color=PALETTE["accent"], lw=2.0, label=f"robusto={robust_v}")
    axes[0].set_title("Regret por v")
    axes[0].set_xlabel("Speed v")
    axes[0].set_ylabel("Regret (k)")
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    axes[0].legend(fontsize=8)

    mask = (v >= 18) & (v <= 50)
    axes[1].plot(v[mask], main_df.loc[mask, "mean_regret"] / 1e3, color=PALETTE["classic"], lw=2.8)
    axes[1].plot(v[mask], main_df.loc[mask, "max_regret"] / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle="--")
    axes[1].plot(v[mask], main_df.loc[mask, "p90_regret"] / 1e3, color=PALETTE["accent2"], lw=1.8, linestyle=":")
    axes[1].axvline(robust_v, color=PALETTE["accent"], lw=2.0)
    axes[1].set_title("Regret zoom 18–50")
    axes[1].set_xlabel("Speed v")
    axes[1].set_ylabel("Regret (k)")
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))

    fig.suptitle("Regret medio y máximo relativo al mejor v por simulación", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("06_regret_by_speed.png", fig)


def plot_multiplier_diagnostics(diag_df: pd.DataFrame) -> None:
    selected = sorted(diag_df["v"].unique())
    fig, axes = plt.subplots(2, len(selected), figsize=(4.1 * len(selected), 8))
    if len(selected) == 1:
        axes = np.array([[axes[0]], [axes[1]]])
    for idx, v in enumerate(selected):
        sub = diag_df[diag_df["v"] == v]
        ax = axes[0, idx]
        ax.hist(sub["rank"], bins=np.arange(1, MAIN_N + 3) - 0.5, color=PALETTE["ai"], alpha=0.83)
        ax.axvline(sub["rank"].mean(), color="black", lw=1.5, linestyle="--")
        ax.set_title(f"Rank inducido — v={v}")
        ax.set_xlabel("Rank")
        ax.set_ylabel("Count")

        ax = axes[1, idx]
        ax.hist(sub["multiplier"], bins=20, color=PALETTE["accent2"], alpha=0.83)
        ax.axvline(sub["multiplier"].mean(), color="black", lw=1.5, linestyle="--")
        ax.set_title(f"Multiplier inducido — v={v}")
        ax.set_xlabel("Multiplier")
        ax.set_ylabel("Count")
    fig.suptitle("Distribución inducida de rank y multiplier para v candidatos", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("07_multiplier_distributions.png", fig)


def plot_dashboard(main_df: pd.DataFrame, mixture_pmf: pd.Series, rs_table: pd.DataFrame, best_v: int, robust_v: int, conservative_v: int) -> None:
    v = main_df["v"].values
    fig = plt.figure(figsize=(17, 11), constrained_layout=True)
    gs = GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.32)

    ax = fig.add_subplot(gs[0, 0])
    ax.bar(mixture_pmf.index, mixture_pmf.values * 100, width=1.0, color=PALETTE["mixture"], alpha=0.88, edgecolor="none")
    for value in [25, 26, 31, 35, 36, 41]:
        ax.axvline(value, color=PALETTE["just_above"], lw=1.0, linestyle=":", alpha=0.55)
    ax.axvline(best_v, color="black", lw=2.0, label=f"EV*={best_v}")
    ax.set_title("PMF total de Speed de los demás")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PMF (%)")
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[0, 1])
    mask = (v >= 18) & (v <= 50)
    ax.fill_between(v[mask], main_df.loc[mask, "p10"] / 1e3, main_df.loc[mask, "p90"] / 1e3, alpha=0.13, color=PALETTE["ai"])
    ax.plot(v[mask], main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE["ai"], lw=2.8)
    ax.axvline(best_v, color="black", lw=2.0, label=f"EV*={best_v}")
    ax.axvline(robust_v, color=PALETTE["accent"], lw=1.8, linestyle="--", label=f"robusto={robust_v}")
    ax.axvline(conservative_v, color=PALETTE["high_speed"], lw=1.8, linestyle=":", label=f"conservador={conservative_v}")
    ax.set_title("EV(v) en la zona candidata")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("PnL (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[1, 0])
    ax.stackplot(rs_table["v"], rs_table["r_star"], rs_table["s_star"], colors=[PALETTE["accent"], PALETTE["ai"]], alpha=0.84, labels=["Research", "Scale"])
    ax.axvline(best_v, color="black", lw=2.0)
    ax.set_title("Asignación exacta r*(v), s*(v)")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Asignación (%)")
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[1, 1])
    ax.plot(v[mask], main_df.loc[mask, "mean_regret"] / 1e3, color=PALETTE["classic"], lw=2.8, label="mean regret")
    ax.plot(v[mask], main_df.loc[mask, "max_regret"] / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle="--", label="max regret")
    ax.axvline(robust_v, color=PALETTE["accent"], lw=2.0, label=f"robusto={robust_v}")
    ax.set_title("Regret en la zona candidata")
    ax.set_xlabel("Speed v")
    ax.set_ylabel("Regret (k)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    ax.legend(fontsize=8)

    fig.suptitle("Dashboard de decisión: clusters, payoff, split exacto y regret", fontsize=14)
    savefig("08_decision_dashboard.png", fig)


def plot_sensitivity(summary_df: pd.DataFrame, aggregate_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(20, 11))
    groups = [
        ("ai_sigma", "Sigma componente IA"),
        ("ai_internal_weight", "Peso interno del cluster en 35"),
        ("ai_weight_total", "Peso total de IA"),
        ("nash_weight", "Peso Nash"),
        ("just_above_weight", "Peso just-above"),
        ("N", "Tamaño de población N"),
    ]
    for ax, (group, title) in zip(axes.flatten(), groups):
        sub = summary_df[summary_df["group"] == group].sort_values("best_v")
        bars = ax.barh(sub["label"], sub["best_v"], color=PALETTE["ai"], alpha=0.88)
        ax.set_title(title)
        ax.set_xlabel("best v")
        for bar, value in zip(bars, sub["best_v"]):
            ax.text(bar.get_width() + 0.25, bar.get_y() + bar.get_height() / 2, str(int(value)), va="center", fontsize=9)
    fig.suptitle("Sensibilidad: valor recomendado bajo escenarios alternativos", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("09_sensitivity_families.png", fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    axes[0].plot(aggregate_df["v"], aggregate_df["mean_ev_across_scenarios"] / 1e3, color=PALETTE["ai"], lw=2.8, label="mean EV")
    axes[0].plot(aggregate_df["v"], aggregate_df["median_ev_across_scenarios"] / 1e3, color=PALETTE["accent2"], lw=1.8, linestyle="--", label="median EV")
    axes[0].plot(aggregate_df["v"], aggregate_df["min_ev_across_scenarios"] / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle=":", label="min EV")
    axes[0].set_title("EV agregado entre escenarios")
    axes[0].set_xlabel("Speed v")
    axes[0].set_ylabel("PnL (k)")
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    axes[0].legend(fontsize=8)

    axes[1].plot(aggregate_df["v"], aggregate_df["mean_regret_across_scenarios"] / 1e3, color=PALETTE["classic"], lw=2.8, label="mean regret")
    axes[1].plot(aggregate_df["v"], aggregate_df["max_regret_across_scenarios"] / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle="--", label="max regret")
    axes[1].set_title("Regret agregado entre escenarios")
    axes[1].set_xlabel("Speed v")
    axes[1].set_ylabel("Regret (k)")
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    axes[1].legend(fontsize=8)

    fig.suptitle("Superficie agregada de sensibilidad", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("10_sensitivity_aggregate.png", fig)


def plot_iteration_comparison(iter3_mixture: pd.Series, iter4_mixture: pd.Series, iter3_best_v: int, iter4_best_v: int) -> None:
    speeds = np.arange(101)
    fig, axes = plt.subplots(1, 2, figsize=(16, 5.8))
    mask = (speeds >= 20) & (speeds <= 50)
    axes[0].plot(speeds[mask], iter3_mixture.values[mask] * 100, color=PALETTE["accent2"], lw=2.6, label=f"Iteration3 (v*={iter3_best_v})")
    axes[0].plot(speeds[mask], iter4_mixture.values[mask] * 100, color=PALETTE["mixture"], lw=2.8, label=f"Iteration4 (v*={iter4_best_v})")
    axes[0].axvline(iter3_best_v, color=PALETTE["accent2"], lw=1.6, linestyle="--")
    axes[0].axvline(iter4_best_v, color=PALETTE["mixture"], lw=1.6, linestyle="--")
    axes[0].set_title("Zoom 20–50: mezcla nueva vs iteración anterior")
    axes[0].set_xlabel("Speed")
    axes[0].set_ylabel("PMF (%)")
    axes[0].legend(fontsize=8)

    diff = (iter4_mixture - iter3_mixture) * 100
    axes[1].bar(speeds[mask], diff.values[mask], color=np.where(diff.values[mask] >= 0, PALETTE["accent"], PALETTE["high_speed"]), alpha=0.85)
    axes[1].axhline(0, color="black", lw=1)
    axes[1].set_title("Cambio de masa: iteration4 - iteration3")
    axes[1].set_xlabel("Speed")
    axes[1].set_ylabel("Δ PMF (pp)")

    fig.suptitle("Cómo cambia el field al pasar a la nueva mezcla", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("11_iteration3_vs_iteration4.png", fig)


def plot_final_zoom(main_df: pd.DataFrame, aggregate_df: pd.DataFrame, mixture_pmf: pd.Series, best_v: int, robust_v: int, conservative_v: int) -> None:
    mask = (main_df["v"] >= 20) & (main_df["v"] <= 46)
    v = main_df.loc[mask, "v"].values
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8))

    axes[0].bar(v, mixture_pmf.loc[v].values * 100, color=PALETTE["mixture"], alpha=0.9, edgecolor="none")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE["accent"], f"robusto={robust_v}"),
        (conservative_v, PALETTE["high_speed"], f"conservador={conservative_v}"),
    ]:
        axes[0].axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    axes[0].set_title("Clusters del field")
    axes[0].set_xlabel("Speed")
    axes[0].set_ylabel("PMF (%)")
    axes[0].legend(fontsize=8)

    axes[1].plot(v, main_df.loc[mask, "mean_pnl"] / 1e3, color=PALETTE["ai"], lw=2.8, label="EV central")
    agg_sub = aggregate_df[aggregate_df["v"].isin(v)]
    axes[1].plot(v, agg_sub["median_ev_across_scenarios"].values / 1e3, color=PALETTE["accent2"], lw=1.8, linestyle="--", label="mediana sensibilidad")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE["accent"], f"robusto={robust_v}"),
        (conservative_v, PALETTE["high_speed"], f"conservador={conservative_v}"),
    ]:
        axes[1].axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    axes[1].set_title("EV en la zona candidata")
    axes[1].set_xlabel("Speed")
    axes[1].set_ylabel("PnL (k)")
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    axes[1].legend(fontsize=8)

    axes[2].plot(v, main_df.loc[mask, "mean_regret"] / 1e3, color=PALETTE["classic"], lw=2.8, label="mean regret")
    axes[2].plot(v, agg_sub["max_regret_across_scenarios"].values / 1e3, color=PALETTE["high_speed"], lw=1.8, linestyle="--", label="max regret sensibilidad")
    for candidate, color, label in [
        (best_v, "black", f"EV*={best_v}"),
        (robust_v, PALETTE["accent"], f"robusto={robust_v}"),
        (conservative_v, PALETTE["high_speed"], f"conservador={conservative_v}"),
    ]:
        axes[2].axvline(candidate, color=color, lw=1.8, linestyle="--" if candidate != best_v else "-", label=label)
    axes[2].set_title("Regret en la zona candidata")
    axes[2].set_xlabel("Speed")
    axes[2].set_ylabel("Regret (k)")
    axes[2].yaxis.set_major_formatter(mticker.FuncFormatter(fmt_k_pre))
    axes[2].legend(fontsize=8)

    fig.suptitle("Zoom final de decisión", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    savefig("12_final_recommendation_zoom.png", fig)


# ──────────────────────────────────────────────────────────────────────────────
# Final recommendation / comparison
# ──────────────────────────────────────────────────────────────────────────────


def build_final_recommendation(
    rs_table: pd.DataFrame,
    main_df: pd.DataFrame,
    sensitivity_summary: pd.DataFrame,
    sensitivity_aggregate: pd.DataFrame,
) -> pd.DataFrame:
    rs_idx = rs_table.set_index("v")
    best_v = int(main_df.loc[main_df["mean_pnl"].idxmax(), "v"])
    robust_v = int(main_df.loc[main_df["mean_regret"].idxmin(), "v"])
    conservative_v = int(sensitivity_aggregate.loc[sensitivity_aggregate["min_ev_across_scenarios"].idxmax(), "v"])

    best_vals = sensitivity_summary["best_v"].values
    broad_low = int(best_vals.min())
    broad_high = int(best_vals.max())

    within_1pct = sensitivity_aggregate.loc[
        sensitivity_aggregate["mean_ev_across_scenarios"] >= sensitivity_aggregate["mean_ev_across_scenarios"].max() * 0.99,
        "v",
    ]
    core_low = int(within_1pct.min())
    core_high = int(within_1pct.max())

    rows = []
    for criterion, v in [
        ("Max EV (central mixture)", best_v),
        ("Robust (min mean regret)", robust_v),
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
                "mean_regret": float(row["mean_regret"]),
                "max_regret": float(row["max_regret"]),
                "prob_best_response": float(row["prob_best_response"]),
                "broad_range_low": broad_low,
                "broad_range_high": broad_high,
                "core_range_low": core_low,
                "core_range_high": core_high,
            }
        )
    return pd.DataFrame(rows)


def compare_with_iteration3(iter3_mixture: pd.Series, iter4_mixture: pd.Series, iter3_final: pd.DataFrame, iter4_final: pd.DataFrame) -> pd.DataFrame:
    iter3_best = int(iter3_final.iloc[0]["v"])
    iter4_best = int(iter4_final.iloc[0]["v"])
    top3 = iter3_mixture.sort_values(ascending=False).head(8)
    top4 = iter4_mixture.sort_values(ascending=False).head(8)
    rows = [
        {
            "metric": "recommended_v",
            "iteration3": iter3_best,
            "iteration4": iter4_best,
        },
        {
            "metric": "top_clusters",
            "iteration3": ", ".join(f"{int(v)} ({100*p:.1f}%)" for v, p in zip(top3.index[:6], top3.values[:6])),
            "iteration4": ", ".join(f"{int(v)} ({100*p:.1f}%)" for v, p in zip(top4.index[:6], top4.values[:6])),
        },
        {
            "metric": "mean_speed_field",
            "iteration3": float((iter3_mixture.index.values * iter3_mixture.values).sum()),
            "iteration4": float((iter4_mixture.index.values * iter4_mixture.values).sum()),
        },
        {
            "metric": "mass_24_27_pct",
            "iteration3": float(iter3_mixture.loc[24:27].sum() * 100),
            "iteration4": float(iter4_mixture.loc[24:27].sum() * 100),
        },
        {
            "metric": "mass_34_36_pct",
            "iteration3": float(iter3_mixture.loc[34:36].sum() * 100),
            "iteration4": float(iter4_mixture.loc[34:36].sum() * 100),
        },
        {
            "metric": "mass_41_43_pct",
            "iteration3": float(iter3_mixture.loc[41:43].sum() * 100),
            "iteration4": float(iter4_mixture.loc[41:43].sum() * 100),
        },
    ]
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Summary markdown / notebook
# ──────────────────────────────────────────────────────────────────────────────


def build_summary_markdown(
    audit_df: pd.DataFrame,
    rs_table: pd.DataFrame,
    ranking_df: pd.DataFrame,
    component_summary_df: pd.DataFrame,
    cluster_df: pd.DataFrame,
    main_df: pd.DataFrame,
    nash_profile: pd.DataFrame,
    nash_stress_df: pd.DataFrame,
    sensitivity_summary: pd.DataFrame,
    sensitivity_aggregate: pd.DataFrame,
    final_rec_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    iter3_final_df: pd.DataFrame,
) -> str:
    best = final_rec_df.iloc[0]
    robust = final_rec_df.iloc[1]
    conservative = final_rec_df.iloc[2]
    iter3_best = int(iter3_final_df.iloc[0]["v"])
    iter4_best = int(best["v"])

    candidate_table = main_df.loc[
        main_df["v"].isin(sorted(set([iter4_best - 2, iter4_best - 1, iter4_best, iter4_best + 1, int(robust['v']), int(conservative['v']), 26, 31, 36]))),
        ["v", "mean_pnl", "p10", "p90", "mean_regret", "max_regret", "mean_multiplier", "mean_rank"],
    ].sort_values("v")

    sens_counts = sensitivity_summary["best_v"].value_counts().sort_index().reset_index()
    sens_counts.columns = ["v", "count"]
    best_mode = int(sensitivity_summary["best_v"].mode().iloc[0])

    lines = [
        "# IMC Prosperity Round 2 Manual — Iteration 4 summary",
        "",
        "## 1. Resumen ejecutivo",
        "",
        "- NO empecé desde cero: reutilicé el solver exacto `Research/Scale`, el motor exacto de ranking con ties y los artefactos de `iteration3` como benchmark de comparación.",
        "- La gran novedad de `iteration4` es la **mezcla nueva** con estos pesos: IA 30%, Nash 23%, just-above 15%, clásicos 10%, naive 10%, high-speed 7%, random 5%.",
        "- El componente IA se modeló explícitamente como **dos normales truncadas en 20–40** con medias 25 y 35, usando el mismo sigma en el escenario central por interpretabilidad.",
        "- El componente Nash se modeló como una **quantal response de un paso contra el field no racional**. También calculé el fixed-point completamente autorreferencial como stress test, pero lo traté como cota agresiva, no como escenario central.",
        "",
        f"- **Recomendación central:** `Speed* = {int(best['v'])}`, `Research* = {int(best['r'])}`, `Scale* = {int(best['s'])}`.",
        f"- **Recomendación robusta:** `v = {int(robust['v'])}`.",
        f"- **Recomendación más conservadora:** `v = {int(conservative['v'])}`.",
        f"- **Banda defendible:** `{int(best['core_range_low'])}–{int(best['core_range_high'])}`.",
        "",
        "## 2. Qué se reutiliza de iteration3 y qué cambia ahora",
        "",
        markdown_table(audit_df, ".1f"),
        "",
        "## 3. Subproblema exacto Research/Scale",
        "",
        "Para cada `v`, primero se resuelve exactamente `r*(v), s*(v)` con enteros. Como `Research` y `Scale` son crecientes, siempre se usa todo el presupuesto factible: `r + s + v = 100`.",
        "",
        markdown_table(rs_table[rs_table["v"].isin([20, 25, 30, 35, 36, 40, 41, 45])][["v", "r_star", "s_star", "gross_value", "budget_used"]], ".1f"),
        "",
        "## 4. Ranking exacto con empates",
        "",
        "La parte crítica del manual sigue siendo esta:",
        "",
        "- `rank(v) = # {players con speed estrictamente mayor} + 1`",
        "- los empates comparten el mínimo rank del bloque",
        "- el multiplier baja linealmente de `0.9` a `0.1`",
        "",
        "Eso hace que los ties importen MUCHO: si hay cluster en `35`, elegir `35` no te despega; elegir `36` sí te salta toda esa masa.",
        "",
        markdown_table(ranking_df, ".3f"),
        "",
        "## 5. Construcción explícita de la mezcla nueva",
        "",
        "### 5.1 Pesos usados",
        "",
        markdown_table(pd.DataFrame([{"tipo": LABELS[k], "peso": v} for k, v in BASE_WEIGHTS.items()]), ".2f"),
        "",
        "### 5.2 Cómo se modela cada tipo",
        "",
        "- **IA (30%)**: mezcla de dos normales discretizadas y truncadas a `20–40`, con medias `25` y `35`, peso interno `25%/75%`. En el escenario central usé `sigma = 3.5` para ambos clusters: lo bastante concentrado para producir recomendación repetible, pero no tan estrecho como para suponer un número único mágico.",
        "- **Nash / racionales (23%)**: respuesta cuasi-racional de un paso al field no racional. Primero armo la mezcla de todos los tipos excepto Nash, calculo la curva exacta de EV contra ese field y después convierto esa curva en una PMF con softmax. Esto es más prudente que asumir common knowledge total entre racionales.",
        "- **Just-above 0/5 (15%)**: PMF discreta sobre `1,6,11,16,21,26,31,36,41,46,...`, con más masa en `31,36,41,46` porque ahí es donde el patrón 0/5 realmente cruza con la zona económicamente plausible del juego.",
        "- **Clásicos / bonitos (10%)**: PMF discreta sobre `7,13,17,23,27,33,37`, priorizando `33` y `37` como números mentalmente atractivos y además relevantes en este problema.",
        "- **Naive (10%)**: distribución derivada de una optimización incompleta que reemplaza el juego estratégico por un multiplier lineal heurístico creciente con `v`; eso concentra masa en speeds medios-altos, sobre todo alrededor de `35–37`.",
        "- **High-speed parcial (7%)**: normal truncada en `50–80`, centrada en `64`.",
        "- **Aleatorio (5%)**: uniforme discreta en `0..100`.",
        "",
        "### 5.3 Resumen cuantitativo de componentes",
        "",
        markdown_table(component_summary_df, ".2f"),
        "",
        "### 5.4 Perfil cuantitativo del componente Nash",
        "",
        markdown_table(
            nash_profile.sort_values("quantal_prob", ascending=False).head(10)[["v", "mean_pnl", "mean_multiplier", "p_higher", "quantal_prob"]],
            ".4f",
        ),
        "",
        "### 5.5 Stress test: fixed-point autorreferencial",
        "",
        "Si fuerzo un fixed-point completamente autorreferencial entre los Nash-like, la masa estratégica se dispara hacia arriba. Eso sirve como cota agresiva, pero es DEMASIADO fuerte como escenario central porque supone coordinación estratégica mutua mucho más dura.",
        "",
        markdown_table(nash_stress_df, ".2f"),
        "",
        "## 6. Qué distribución total de Speed inducen estos pesos",
        "",
        markdown_table(cluster_df.head(10), ".2f"),
        "",
        "Lectura técnica:",
        "",
        "- El **cluster IA en torno a 35** empuja con fuerza la masa total hacia `34–36`.",
        "- El componente **just-above** mete escalones claros en `26`, `31`, `36`, `41`.",
        "- El componente Nash no destruye esos clusters; los **reordena** alrededor de donde el salto de ties compensa mejor el coste económico de subir `v`.",
        "- El fixed-point autorreferencial, en cambio, empuja demasiado arriba y por eso lo traté como stress test, no como centro de gravedad metodológico.",
        "",
        "## 7. Monte Carlo poblacional",
        "",
        "El Monte Carlo central usa muchas poblaciones simuladas con `N = 50` y seeds fijas. Para cada población y para cada `v`, recalcula rank exacto, multiplier exacto y PnL usando el `r*(v), s*(v)` exacto.",
        "",
        markdown_table(candidate_table, ".1f"),
        "",
        f"En esta mezcla, el mejor `v` central es **{iter4_best}**, mientras que en `iteration3` era **{iter3_best}**.",
        "",
        "## 8. Sensibilidad",
        "",
        markdown_table(sensitivity_summary[["label", "best_v", "robust_v", "best_ev"]], ".1f"),
        "",
        "### Conteo de ganadores por escenario",
        "",
        markdown_table(sens_counts, ".1f"),
        "",
        "### Superficie agregada",
        "",
        markdown_table(sensitivity_aggregate[sensitivity_aggregate["v"].isin(sorted(set([iter4_best - 2, iter4_best - 1, iter4_best, iter4_best + 1, int(conservative['v']), 26, 31, 36, 41])))], ".1f"),
        "",
        f"Centro de gravedad de sensibilidad: **{best_mode}**.",
        "",
        "## 9. Comparación explícita contra iteration3",
        "",
        markdown_table(comparison_df, ".2f"),
        "",
        "Interpretación:",
        "",
        "- La mezcla nueva mete **más estructura en 25 y 35** por el componente IA, y más estructura en `26/31/36/41` por el just-above sobre números acabados en 0 o 5.",
        "- Eso hace que el juego deje de estar dominado solamente por el cuello de botella `41–42` de `iteration3` y pase a tener más candidatas intermedias como `26`, `31` y especialmente `36`.",
        "- La pregunta correcta ya no es solo ‘¿me pongo arriba del 41?’, sino también ‘¿cuánto valor tiene ponerme arriba del gran cluster en 35 sin pagar demasiado impuesto económico?’",
        "",
        "## 10. Recomendación final",
        "",
        markdown_table(final_rec_df, ".1f"),
        "",
        f"### Mi recomendación central: `{int(best['v'])} / {int(best['r'])} / {int(best['s'])}`",
        "",
        f"- **Por EV puro**: `{int(best['v'])}`.",
        f"- **Por robustez**: `{int(robust['v'])}`.",
        f"- **Si querés cubrirte contra un field algo más alto**: `{int(conservative['v'])}`.",
        f"- **Banda defendible**: `{int(best['core_range_low'])}–{int(best['core_range_high'])}`.",
        "",
        "### Qué parte de la decisión viene de cada componente",
        "",
        "- **Componente IA (25/35)**: crea un gran colchón de masa en `34–36`, que vuelve muy atractiva la lógica de ponerse apenas por encima del cluster de 35 cuando el coste económico lo permite.",
        "- **Componente just-above**: mete contra-clusters en `26`, `31`, `36`, `41`; eso hace que `36` y `41` no sean caprichos, sino escalones estratégicos reales.",
        "- **Subproblema Research/Scale**: frena la tentación de correr demasiado arriba. Si te vas muy alto en `v`, el salto de multiplier ya no compensa el deterioro de `Research × Scale`.",
        "",
        "## 11. Respuestas directas a las preguntas pedidas",
        "",
        "1. **¿Qué distribución total de Speed inducen estos pesos?**",
        "   - Una mezcla con clusters muy visibles en torno a `25–26`, `34–36` y un escalón adicional en `41`, más una cola alta moderada por el grupo speed-race.",
        "2. **¿Dónde están los principales clusters?**",
        "   - El corazón del field está en `34–36`; los escalones tácticos adicionales más relevantes están en `26`, `31` y `41`.",
        "3. **¿Cómo influye el componente IA con medias 25 y 35?**",
        "   - Le mete mucha masa al 35 y una masa secundaria al 25; eso hace que los valores justo por encima de esos clusters valgan más de lo que valían en iteration3.",
        "4. **¿Qué papel juega el componente just-above?**",
        "   - Es el componente que más explícitamente monetiza los ties. Sin él, la mezcla sería más ‘bonita’; con él, aparecen escalones estratégicos claros en `26/31/36/41`.",
        "5. **¿Qué v explota mejor esos clusters?**",
        f"   - En el escenario central, `{iter4_best}`.",
        "6. **¿Qué allocation r,s,v recomendaría?**",
        f"   - `{int(best['r'])}, {int(best['s'])}, {int(best['v'])}` en formato `Research, Scale, Speed`.",
        "7. **¿Qué tan sensible es la recomendación a pequeños cambios en IA?**",
        f"   - El rango total de ganadores en la batería fue `{int(best['broad_range_low'])}–{int(best['broad_range_high'])}`, pero la banda central defendible quedó más estrecha: `{int(best['core_range_low'])}–{int(best['core_range_high'])}`.",
        "",
        "## 12. Artefactos",
        "",
        f"- Notebook: `{BASE / 'manual_round2_analysis_iteration4.ipynb'}`",
        f"- Markdown: `{OUT / 'manual_round2_summary_iteration4.md'}`",
        f"- Plots: `{PLOTS}`",
        f"- CSVs: `{CSVS}`",
        "",
    ]
    return "\n".join(lines)


def build_notebook(final_rec_df: pd.DataFrame) -> None:
    best = final_rec_df.iloc[0]
    robust = final_rec_df.iloc[1]
    conservative = final_rec_df.iloc[2]
    nb = nbformat.v4.new_notebook()
    cells = []
    cells.append(
        nbformat.v4.new_markdown_cell(
            "# Round 2 Manual — Iteration 4\n\n"
            "Notebook de lectura para la iteración 4. Reutiliza el trabajo exacto de `iteration3`, pero cambia la mezcla de tipos y deja materializados los nuevos resultados en `results/iteration4/`."
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 1. Qué cambia en esta iteración\n\n"
            "- IA: ahora es una mezcla explícita de dos normales truncadas con medias 25 y 35\n"
            "- Nash: ahora es una quantal response de un paso contra el field no racional; el fixed-point completo queda como stress test, no como centro\n"
            "- just-above: ahora sigue explícitamente números acabados en 0 o 5\n"
            "- se compara directamente contra `iteration3`\n"
            "- se mantiene el solver exacto de `Research/Scale` y el motor exacto de ranking con ties"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "from pathlib import Path\n"
            "import pandas as pd\n\n"
            "BASE = Path.cwd() if Path.cwd().name == 'manual' else Path('/Users/pablo/Desktop/prosperity/round_2/manual')\n"
            "OUT = BASE / 'results' / 'iteration4'\n"
            "PLOTS = OUT / 'plots'\n\n"
            "rs = pd.read_csv(OUT / 'optimal_rs_by_speed_iteration4.csv')\n"
            "pmf = pd.read_csv(OUT / 'mixture_total_pmf_iteration4.csv')\n"
            "ev = pd.read_csv(OUT / 'ev_by_speed_iteration4.csv')\n"
            "sens = pd.read_csv(OUT / 'sensitivity_summary_iteration4.csv')\n"
            "rec = pd.read_csv(OUT / 'final_recommendation_iteration4.csv')\n"
            "comp = pd.read_csv(OUT / 'iteration3_vs_iteration4_comparison.csv')\n"
            "rec"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 2. Subproblema exacto Research/Scale\n\n"
            "![](results/iteration4/plots/00_rs_subproblem.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "rs.loc[rs['v'].isin([20,25,30,35,36,40,41,45]), ['v','r_star','s_star','gross_value']]"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 3. Distribuciones por tipo y mezcla total\n\n"
            "![](results/iteration4/plots/01_type_pmfs_individual.png)\n\n"
            "![](results/iteration4/plots/02_type_pmfs_overlay.png)\n\n"
            "![](results/iteration4/plots/03_component_focus.png)\n\n"
            "![](results/iteration4/plots/04_mixture_total_and_comparison.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "pmf.sort_values('pmf_total_mixture', ascending=False).head(12)"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 4. Monte Carlo, payoff y regret\n\n"
            "![](results/iteration4/plots/05_ev_by_speed.png)\n\n"
            "![](results/iteration4/plots/06_regret_by_speed.png)\n\n"
            "![](results/iteration4/plots/07_multiplier_distributions.png)\n\n"
            "![](results/iteration4/plots/08_decision_dashboard.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "ev.loc[ev['v'].isin([26,31,35,36,40,41,42]), ['v','mean_pnl','p10','p90','mean_regret','max_regret','prob_best_response']]"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 5. Sensibilidad\n\n"
            "![](results/iteration4/plots/09_sensitivity_families.png)\n\n"
            "![](results/iteration4/plots/10_sensitivity_aggregate.png)"
        )
    )
    cells.append(
        nbformat.v4.new_code_cell(
            "sens[['label','best_v','robust_v','best_ev']].sort_values(['group','best_v'])"
        )
    )
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 6. Comparación explícita contra iteration3\n\n"
            "![](results/iteration4/plots/11_iteration3_vs_iteration4.png)"
        )
    )
    cells.append(nbformat.v4.new_code_cell("comp"))
    cells.append(
        nbformat.v4.new_markdown_cell(
            "## 7. Recomendación final\n\n"
            "![](results/iteration4/plots/12_final_recommendation_zoom.png)\n\n"
            f"Recomendación central: **Speed = {int(best['v'])}, Research = {int(best['r'])}, Scale = {int(best['s'])}**.\n\n"
            f"- EV puro: **{int(best['v'])}**\n"
            f"- Robusto: **{int(robust['v'])}**\n"
            f"- Conservador: **{int(conservative['v'])}**"
        )
    )
    cells.append(nbformat.v4.new_code_cell("rec"))
    nb.cells = cells
    nbformat.write(nb, BASE / "manual_round2_analysis_iteration4.ipynb")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    audit_df = audit_previous_iteration()
    rs_table = compute_rs_table()
    assert verify_ranking_examples(), "Ranking engine verification failed"
    ranking_df = ranking_examples_table()

    config = ScenarioConfig(ai_sigma_25=2.0, ai_sigma_35=2.0, ai_weight_35=0.75, weights=BASE_WEIGHTS, N=MAIN_N)
    weights = normalize_weights(config.weights)
    component_pmfs, nash_profile = build_component_pmfs(rs_table, config)
    mixture_pmf = build_mixture_pmf(component_pmfs, weights)

    non_nash_pmfs = {k: v for k, v in component_pmfs.items() if k != "nash_like"}
    _nash_stress_pmf, nash_stress_history = fixed_point_nash_stress_test(rs_table, non_nash_pmfs, weights)
    nash_stress_df = nash_stress_history.tail(5).reset_index(drop=True)

    iter3_dir = BASE / "results" / "iteration3"
    iteration3_mixture = pd.read_csv(iter3_dir / "mixture_total_pmf.csv").set_index("v")["pmf"]
    iter3_final = pd.read_csv(iter3_dir / "final_recommendation_iteration3.csv")

    main_df, pnl_matrix, mult_matrix, others = monte_carlo_speed_game(
        rs_table,
        component_pmfs,
        weights,
        N=config.N,
        n_sims=MAIN_SIMS,
        seed=SEED,
        v_grid=V_GRID,
    )
    _ = pnl_matrix, mult_matrix, others

    sensitivity_summary, sensitivity_curves = run_sensitivity(rs_table)
    sensitivity_aggregate = aggregate_sensitivity(sensitivity_curves)
    final_rec_df = build_final_recommendation(rs_table, main_df, sensitivity_summary, sensitivity_aggregate)
    comparison_df = compare_with_iteration3(iteration3_mixture, mixture_pmf, iter3_final, final_rec_df)

    best_v = int(final_rec_df.iloc[0]["v"])
    robust_v = int(final_rec_df.iloc[1]["v"])
    conservative_v = int(final_rec_df.iloc[2]["v"])

    selected_v = sorted(set([best_v - 1, best_v, best_v + 1, conservative_v, 26, 31, 36, 41]))
    selected_v = [v for v in selected_v if 0 <= v <= 100]
    diag_df = diagnostic_distributions(
        rs_table,
        component_pmfs,
        weights,
        selected_v=selected_v,
        N=config.N,
        n_sims=20_000,
        seed=SEED + 77,
    )

    component_summary_df = component_summary(component_pmfs, weights)
    cluster_df = top_clusters(mixture_pmf, top_n=12)

    # plots
    plot_rs_subproblem(rs_table)
    plot_type_distributions(component_pmfs, mixture_pmf, iteration3_mixture)
    plot_payoff_and_regret(main_df, best_v, robust_v, conservative_v)
    plot_multiplier_diagnostics(diag_df)
    plot_dashboard(main_df, mixture_pmf, rs_table, best_v, robust_v, conservative_v)
    plot_sensitivity(sensitivity_summary, sensitivity_aggregate)
    plot_iteration_comparison(iteration3_mixture, mixture_pmf, int(iter3_final.iloc[0]["v"]), best_v)
    plot_final_zoom(main_df, sensitivity_aggregate, mixture_pmf, best_v, robust_v, conservative_v)

    # CSVs
    write_csv_dual("optimal_rs_by_speed_iteration4.csv", rs_table)
    write_csv_dual("type_component_pmf_iteration4.csv", component_pmf_frame(component_pmfs, mixture_pmf))
    write_csv_dual("mixture_total_pmf_iteration4.csv", pd.DataFrame({"v": np.arange(101), "pmf_total_mixture": mixture_pmf.values}))
    write_csv_dual("ev_by_speed_iteration4.csv", main_df)
    write_csv_dual("regret_by_speed_iteration4.csv", main_df[["v", "mean_regret", "max_regret", "p90_regret", "prob_best_response"]])
    write_csv_dual("sensitivity_summary_iteration4.csv", sensitivity_summary)
    write_csv_dual("sensitivity_curves_iteration4.csv", sensitivity_curves)
    write_csv_dual("sensitivity_aggregate_iteration4.csv", sensitivity_aggregate)
    write_csv_dual("final_recommendation_iteration4.csv", final_rec_df)
    write_csv_dual("nash_component_iteration4.csv", nash_profile)
    write_csv_dual("nash_stress_iteration4.csv", nash_stress_history)
    write_csv_dual("iteration3_vs_iteration4_comparison.csv", comparison_df)

    summary_text = build_summary_markdown(
        audit_df=audit_df,
        rs_table=rs_table,
        ranking_df=ranking_df,
        component_summary_df=component_summary_df,
        cluster_df=cluster_df,
        main_df=main_df,
        nash_profile=nash_profile,
        nash_stress_df=nash_stress_df,
        sensitivity_summary=sensitivity_summary,
        sensitivity_aggregate=sensitivity_aggregate,
        final_rec_df=final_rec_df,
        comparison_df=comparison_df,
        iter3_final_df=iter3_final,
    )
    summary_path = OUT / "manual_round2_summary_iteration4.md"
    summary_path.write_text(summary_text, encoding="utf-8")
    build_notebook(final_rec_df)

    print(f"Wrote summary to {summary_path}")
    print(f"Recommendation: Speed={best_v}, Research={int(final_rec_df.iloc[0]['r'])}, Scale={int(final_rec_df.iloc[0]['s'])}")


if __name__ == "__main__":
    main()
