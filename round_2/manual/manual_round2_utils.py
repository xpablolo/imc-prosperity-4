"""
IMC Prosperity Round 2 — Manual Trading Utilities
===================================================

Utility module for the Resource Allocation problem:
    PnL = Research(r) * Scale(s) * Speed(v) - Budget_Used

Allocation:
    r, s, v ∈ {0,...,100} (integer percentage points)
    r + s + v ≤ 100
    Budget_Used = 500 * (r + s + v)

Functions:
    Research(r) = 200_000 * log(1+r) / log(101)
    Scale(s)    = 7 * s / 100
    Speed(v)    = rank-based multiplier ∈ [0.1, 0.9]
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq

# ─── Constants ────────────────────────────────────────────────────────────────

TOTAL_BUDGET = 50_000          # XIRECs
BUDGET_PER_POINT = 500         # = TOTAL_BUDGET / 100
RESEARCH_MAX_OUTPUT = 200_000
SCALE_MAX_MULTIPLIER = 7
SPEED_HIGH = 0.9
SPEED_LOW  = 0.1
SPEED_RANGE = SPEED_HIGH - SPEED_LOW   # 0.8

# ─── Core Economic Functions ──────────────────────────────────────────────────

def research(r: float) -> float:
    """Research output. Concave (logarithmic), r ∈ [0,100].

    Research(0)   = 0
    Research(100) = 200_000
    """
    return RESEARCH_MAX_OUTPUT * np.log1p(r) / np.log(101)


def scale(s: float) -> float:
    """Scale multiplier. Linear, s ∈ [0,100].

    Scale(0)   = 0
    Scale(100) = 7
    """
    return SCALE_MAX_MULTIPLIER * s / 100.0


def budget_used(r: float, s: float, v: float) -> float:
    """Total budget consumed."""
    return BUDGET_PER_POINT * (r + s + v)


def gross_pnl(r: float, s: float, speed_mult: float) -> float:
    """Gross PnL before budget subtraction."""
    return research(r) * scale(s) * speed_mult


def pnl(r: float, s: float, v: float, speed_mult: float) -> float:
    """Net PnL = Research(r) * Scale(s) * Speed_mult - Budget_Used."""
    return gross_pnl(r, s, speed_mult) - budget_used(r, s, v)


# ─── Research/Scale Subproblem ────────────────────────────────────────────────

def _rs_foc(r: float, T: float) -> float:
    """First-order condition for the continuous RS optimisation.

    Maximise log(1+r) * (T-r)  s.t.  r ∈ (0, T).
    FOC: (T-r)/(1+r) = log(1+r)
    """
    return (T - r) / (1.0 + r) - np.log1p(r)


def _continuous_optimal_r(T: float) -> float:
    """Solve continuous FOC for r* given remaining budget T."""
    if T <= 0:
        return 0.0
    if T < 1e-9:
        return 0.0
    # FOC is positive near r=0 (= T > 0) and negative near r=T (= -log(1+T))
    try:
        return brentq(lambda r: _rs_foc(r, T), 1e-10, T - 1e-10, xtol=1e-9)
    except ValueError:
        return T / 4.0  # Fallback (edge case)


def optimal_rs_continuous(v: float) -> dict:
    """Solve continuous RS optimisation for given speed allocation v."""
    T = 100.0 - v
    if T <= 0:
        return dict(v=v, r_star=0.0, s_star=0.0, gross_value=0.0, r_over_T=float("nan"))
    r = _continuous_optimal_r(T)
    s = T - r
    return dict(
        v=v,
        r_star=r,
        s_star=s,
        gross_value=research(r) * scale(s),
        r_over_T=r / T if T > 0 else float("nan"),
    )


def optimal_rs_integer(v: int) -> dict:
    """Solve integer RS optimisation for given speed allocation v.

    Searches integers near the continuous optimum.
    Always uses full remaining budget (r+s = 100-v) because both
    Research and Scale are increasing — leaving budget idle is suboptimal.
    """
    T = 100 - v
    if T <= 0:
        return dict(v=v, r_star=0, s_star=0, gross_value=0.0,
                    budget_used=v * BUDGET_PER_POINT, net_mid=0.0 - v * BUDGET_PER_POINT)
    if T == 1:
        # Research(1)*Scale(0) = 0, Research(0)*Scale(1) = 0 — both zero
        # Give single point to Scale (Scale is more "efficient" per unit in the limit)
        return dict(v=v, r_star=0, s_star=1, gross_value=0.0,
                    budget_used=100 * BUDGET_PER_POINT, net_mid=0.0 - 50_000)

    r_cont = _continuous_optimal_r(float(T))
    # Evaluate integers around continuous solution
    r_lo = max(0, int(np.floor(r_cont)) - 1)
    r_hi = min(T, int(np.ceil(r_cont)) + 1)

    best_r, best_val = 0, -np.inf
    for r_cand in range(r_lo, r_hi + 1):
        s_cand = T - r_cand
        val = research(r_cand) * scale(s_cand)
        if val > best_val:
            best_val = val
            best_r = r_cand

    best_s = T - best_r
    bu = budget_used(best_r, best_s, v)
    net_mid = best_val * 0.5 - bu   # net at middle-speed multiplier (0.5)

    return dict(v=v, r_star=best_r, s_star=best_s,
                gross_value=best_val, budget_used=bu, net_mid=net_mid)


def compute_rs_table() -> pd.DataFrame:
    """Return DataFrame with optimal r*,s* and derived quantities for all v ∈ [0,100]."""
    rows = [optimal_rs_integer(v) for v in range(101)]
    df = pd.DataFrame(rows)
    df["r_frac"] = df["r_star"] / (100 - df["v"]).clip(lower=1)
    df["s_frac"] = df["s_star"] / (100 - df["v"]).clip(lower=1)
    return df


# ─── Speed Ranking Engine ─────────────────────────────────────────────────────

def speed_rank(my_v: int, others_v: list[int] | np.ndarray) -> int:
    """Compute rank of my_v among all players.

    rank = (# players with strictly higher speed) + 1
    Ties share the minimum rank of the group (best possible rank).
    """
    return int(np.sum(np.asarray(others_v) > my_v)) + 1


def speed_multiplier(my_v: int, others_v: list[int] | np.ndarray) -> float:
    """Compute Speed multiplier for my_v given all other players' speeds.

    N = total players (len(others_v) + 1)
    multiplier = 0.9 - (rank-1)/(N-1) * 0.8

    Edge case N=1: returns 0.5 (midpoint — single player is unranked).
    """
    others = np.asarray(others_v)
    N = len(others) + 1
    if N == 1:
        return 0.5
    rank = speed_rank(my_v, others)
    return SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE


def verify_ranking_examples() -> bool:
    """Unit tests from the problem statement."""
    ok = True

    # Example 1: 70,70,70,50,40,40,30 → ranks 1,1,1,4,5,5,7
    speeds = [70, 70, 70, 50, 40, 40, 30]
    expected_ranks = [1, 1, 1, 4, 5, 5, 7]
    for i, (v, expected_r) in enumerate(zip(speeds, expected_ranks)):
        others = speeds[:i] + speeds[i+1:]
        r = speed_rank(v, others)
        if r != expected_r:
            print(f"  FAIL rank test 1 index {i}: got {r}, expected {expected_r}")
            ok = False

    # Example 2: 95,20,10 → multipliers 0.9, 0.5, 0.1
    speeds2 = [95, 20, 10]
    expected_mults = [0.9, 0.5, 0.1]
    for i, (v, expected_m) in enumerate(zip(speeds2, expected_mults)):
        others = speeds2[:i] + speeds2[i+1:]
        m = speed_multiplier(v, others)
        if not np.isclose(m, expected_m, atol=1e-9):
            print(f"  FAIL mult test 2 index {i}: got {m:.4f}, expected {expected_m}")
            ok = False

    return ok


# ─── Player Behavioral Types ──────────────────────────────────────────────────

def _sample_speed(player_type: str, rng: np.random.Generator, **kw) -> int:
    """Sample a speed allocation for one player of a given type."""
    if player_type == "low_speed":
        # Allocates mostly to Research/Scale, treats Speed as a tax
        mu = kw.get("mean", 12)
        sigma = kw.get("std", 8)
        return int(np.clip(rng.normal(mu, sigma), 0, 100))

    elif player_type == "rational_smooth":
        # Smooth continuous approximation of rational behaviour
        # Understands the concavity of Research — optimal v around 20-40
        mu = kw.get("mean", 28)
        sigma = kw.get("std", 12)
        return int(np.clip(rng.normal(mu, sigma), 0, 100))

    elif player_type == "rational_tie_aware":
        # Strategically avoids obvious focal points
        focal = kw.get("focal_points", [15, 22, 29, 31, 37, 41, 47, 53])
        weights = np.ones(len(focal))
        weights /= weights.sum()
        return int(rng.choice(focal, p=weights))

    elif player_type == "naive_ev":
        # Naively thinks "higher Speed = more PnL" — doesn't account for RS loss
        mu = kw.get("mean", 70)
        sigma = kw.get("std", 12)
        return int(np.clip(rng.normal(mu, sigma), 0, 100))

    elif player_type == "round_numbers":
        # Strong preference for multiples of 10, 25, or 33
        options = kw.get("options", [0, 10, 20, 25, 30, 33, 40, 50, 60, 66, 70, 75, 80, 90, 100])
        return int(rng.choice(options))

    elif player_type == "equal_split":
        # Defaults to equal 33/33/34 allocation → v ∈ {33, 34}
        return int(rng.choice([33, 34]))

    elif player_type == "random":
        return int(rng.integers(0, 101))

    elif player_type == "high_speed":
        # Aggressively races for top Speed rank
        mu = kw.get("mean", 75)
        sigma = kw.get("std", 12)
        return int(np.clip(rng.normal(mu, sigma), 0, 100))

    elif player_type == "moderate_speed":
        mu = kw.get("mean", 45)
        sigma = kw.get("std", 15)
        return int(np.clip(rng.normal(mu, sigma), 0, 100))

    else:
        raise ValueError(f"Unknown player type: {player_type!r}")


# ─── Population Scenarios ─────────────────────────────────────────────────────

SCENARIOS: dict[str, dict] = {
    "conservative": {
        "description": (
            "Players prefer Research/Scale over Speed. "
            "Most treat Speed as a cost, not a weapon."
        ),
        "mixture": [
            ("low_speed",        0.40),
            ("rational_smooth",  0.30),
            ("round_numbers",    0.20),
            ("random",           0.10),
        ],
    },
    "central": {
        "description": (
            "Balanced field. Mix of rational and naive players. "
            "Reflects a typical competition population."
        ),
        "mixture": [
            ("rational_smooth",   0.28),
            ("round_numbers",     0.22),
            ("naive_ev",          0.18),
            ("rational_tie_aware",0.15),
            ("random",            0.17),
        ],
    },
    "sophisticated": {
        "description": (
            "Majority of players think carefully about strategy. "
            "Many are tie-aware and avoid obvious focal points."
        ),
        "mixture": [
            ("rational_tie_aware", 0.35),
            ("rational_smooth",    0.35),
            ("round_numbers",      0.20),
            ("random",             0.10),
        ],
    },
    "round_number_heavy": {
        "description": (
            "Strong coordination on round numbers (10, 25, 33, 50 etc.). "
            "Reflects anchoring to simple allocations."
        ),
        "mixture": [
            ("round_numbers",    0.55),
            ("rational_smooth",  0.15),
            ("random",           0.20),
            ("naive_ev",         0.10),
        ],
    },
    "speed_race": {
        "description": (
            "Many players race hard on Speed, competing for top multiplier. "
            "High Speed inflation across the field."
        ),
        "mixture": [
            ("high_speed",       0.35),
            ("naive_ev",         0.25),
            ("rational_smooth",  0.20),
            ("round_numbers",    0.15),
            ("random",           0.05),
        ],
    },
    "balanced_field": {
        "description": (
            "Approximately uniform distribution. No dominant strategy type."
        ),
        "mixture": [
            ("low_speed",        0.20),
            ("rational_smooth",  0.20),
            ("naive_ev",         0.20),
            ("round_numbers",    0.20),
            ("random",           0.20),
        ],
    },
}


def sample_population(scenario_name: str, N: int, rng: np.random.Generator) -> np.ndarray:
    """Sample speeds for N-1 other players under a scenario."""
    scenario = SCENARIOS[scenario_name]
    types, raw_weights = zip(*scenario["mixture"])
    weights = np.asarray(raw_weights, dtype=float)
    weights /= weights.sum()
    speeds = []
    for _ in range(N - 1):
        ptype = rng.choice(list(types), p=weights)
        speeds.append(_sample_speed(ptype, rng))
    return np.asarray(speeds, dtype=int)


# ─── Monte Carlo Engine ───────────────────────────────────────────────────────

def monte_carlo_ev(
    rs_table: pd.DataFrame,
    scenario_name: str,
    N: int = 50,
    n_sims: int = 10_000,
    seed: int = 42,
    v_candidates: Optional[list[int]] = None,
) -> pd.DataFrame:
    """Estimate E[PnL(v)] for each candidate v under a population scenario.

    Uses optimal r*(v), s*(v) from rs_table.
    Speed multiplier is computed exactly (with ties).

    Returns DataFrame with columns:
        v, scenario, mean_pnl, std_pnl, p10, p25, p50, p75, p90
    """
    rng = np.random.default_rng(seed)
    if v_candidates is None:
        v_candidates = list(range(101))

    # Pre-index rs_table for fast lookup
    rs_idx = rs_table.set_index("v")

    results = []
    for v in v_candidates:
        row = rs_idx.loc[v]
        r_star = int(row["r_star"])
        s_star = int(row["s_star"])

        pnls = np.empty(n_sims)
        for i in range(n_sims):
            others = sample_population(scenario_name, N, rng)
            mult = speed_multiplier(v, others)
            pnls[i] = pnl(r_star, s_star, v, mult)

        results.append(dict(
            v=v,
            scenario=scenario_name,
            N=N,
            mean_pnl=pnls.mean(),
            std_pnl=pnls.std(),
            p10=np.percentile(pnls, 10),
            p25=np.percentile(pnls, 25),
            p50=np.percentile(pnls, 50),
            p75=np.percentile(pnls, 75),
            p90=np.percentile(pnls, 90),
        ))

    return pd.DataFrame(results)


def run_all_scenarios(
    rs_table: pd.DataFrame,
    N: int = 50,
    n_sims: int = 10_000,
    seed: int = 42,
    v_candidates: Optional[list[int]] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Run Monte Carlo for all defined scenarios."""
    frames = []
    for name in SCENARIOS:
        if verbose:
            print(f"  → {name}...", end=" ", flush=True)
        df = monte_carlo_ev(rs_table, name, N=N, n_sims=n_sims,
                            seed=seed, v_candidates=v_candidates)
        frames.append(df)
        if verbose:
            best_v = df.loc[df["mean_pnl"].idxmax(), "v"]
            print(f"best v={best_v}")
    return pd.concat(frames, ignore_index=True)


# ─── Sensitivity Helpers ──────────────────────────────────────────────────────

def sensitivity_over_N(
    rs_table: pd.DataFrame,
    scenario_name: str,
    N_values: list[int],
    n_sims: int = 5_000,
    seed: int = 42,
    v_candidates: Optional[list[int]] = None,
) -> pd.DataFrame:
    """Run MC for different population sizes N."""
    frames = []
    for N in N_values:
        df = monte_carlo_ev(rs_table, scenario_name, N=N, n_sims=n_sims,
                            seed=seed, v_candidates=v_candidates)
        df["N"] = N
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ─── Regret Analysis ──────────────────────────────────────────────────────────

def compute_regret(ev_df: pd.DataFrame) -> pd.DataFrame:
    """Compute regret(v, scenario) = best_EV(scenario) - EV(v, scenario).

    Adds columns: best_ev, regret.
    """
    pieces = []
    for scenario, group in ev_df.groupby("scenario"):
        g = group.copy()
        best_ev = g["mean_pnl"].max()
        g["best_ev"] = best_ev
        g["regret"] = best_ev - g["mean_pnl"]
        pieces.append(g)
    return pd.concat(pieces, ignore_index=True)


def minimax_regret(regret_df: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame indexed by v with max_regret across scenarios.

    Minimax-regret v* = argmin_v max_scenario regret(v, scenario).
    """
    pivot = regret_df.pivot_table(index="v", columns="scenario", values="regret")
    max_regret = pivot.max(axis=1).rename("max_regret")
    mean_regret = pivot.mean(axis=1).rename("mean_regret")
    result = pd.concat([pivot, max_regret, mean_regret], axis=1).reset_index()
    result = result.sort_values("max_regret")
    return result


def robust_ev(ev_df: pd.DataFrame) -> pd.DataFrame:
    """Return mean EV across scenarios for each v (equal-weighted scenarios)."""
    return (
        ev_df.groupby("v")["mean_pnl"]
        .mean()
        .rename("robust_ev")
        .reset_index()
        .sort_values("robust_ev", ascending=False)
    )


# ─── Vectorised Normal-Population MC ─────────────────────────────────────────

def mc_normal_vectorized(
    rs_table: pd.DataFrame,
    mu: float,
    sigma: float,
    N: int = 50,
    n_sims: int = 10_000,
    seed: int = 42,
    v_candidates: Optional[list[int]] = None,
) -> pd.DataFrame:
    """Fast MC: other players' speeds ~ round(clip(N(mu, sigma), 0, 100)).

    Fully vectorised over simulations — ~100x faster than per-sim loop.

    Returns DataFrame with: v, mean_pnl, std_pnl, p10, p25, p50, p75, p90,
                             mean_mult, std_mult.
    """
    rng = np.random.default_rng(seed)
    if v_candidates is None:
        v_candidates = list(range(101))

    # Sample all (n_sims × N-1) others at once
    raw = rng.normal(mu, sigma, size=(n_sims, N - 1))
    others = np.clip(raw, 0, 100).round().astype(np.int16)   # (n_sims, N-1)

    rs_idx = rs_table.set_index("v")
    results = []
    for v in v_candidates:
        gv = rs_idx.loc[v, "gross_value"]
        # rank = #{others > v} + 1  (vectorised over sims)
        n_higher = (others > v).sum(axis=1)            # (n_sims,)
        rank = n_higher + 1
        mult = SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE   # (n_sims,)
        p = gv * mult - TOTAL_BUDGET
        results.append(dict(
            v=v,
            mean_pnl=float(p.mean()),
            std_pnl=float(p.std()),
            p10=float(np.percentile(p, 10)),
            p25=float(np.percentile(p, 25)),
            p50=float(np.percentile(p, 50)),
            p75=float(np.percentile(p, 75)),
            p90=float(np.percentile(p, 90)),
            mean_mult=float(mult.mean()),
            std_mult=float(mult.std()),
        ))
    return pd.DataFrame(results)


def normal_battery(
    rs_table: pd.DataFrame,
    mus: list[float],
    sigmas: list[float],
    N: int = 50,
    n_sims: int = 10_000,
    seed: int = 42,
    v_candidates: Optional[list[int]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run mc_normal_vectorized over a grid of (mu, sigma) values.

    Returns:
        ev_long   — long DataFrame with all (mu, sigma, v, stats)
        summary   — one row per (mu, sigma): best_v, best_ev, regret_at_35
    """
    if v_candidates is None:
        v_candidates = list(range(0, 101, 2))

    ev_frames, summary_rows = [], []
    for mu in mus:
        for sigma in sigmas:
            df = mc_normal_vectorized(
                rs_table, mu, sigma, N=N, n_sims=n_sims,
                seed=seed, v_candidates=v_candidates,
            )
            df["mu"] = mu
            df["sigma"] = sigma
            ev_frames.append(df)

            best_idx = df["mean_pnl"].idxmax()
            best_v = int(df.loc[best_idx, "v"])
            best_ev = float(df.loc[best_idx, "mean_pnl"])
            # Regret at v=35 (our recommendation)
            row_35 = df[df["v"] == 35]
            ev_35 = float(row_35["mean_pnl"].values[0]) if len(row_35) > 0 else np.nan
            regret_35 = best_ev - ev_35

            summary_rows.append(dict(
                mu=mu, sigma=sigma,
                best_v=best_v, best_ev=best_ev,
                ev_at_35=ev_35, regret_at_35=regret_35,
            ))

    ev_long = pd.concat(ev_frames, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    return ev_long, summary


# ─── Rank / Multiplier Distribution Sampler ──────────────────────────────────

def sample_multiplier_distribution(
    my_v: int,
    scenario_name: str,
    N: int = 50,
    n_sims: int = 20_000,
    seed: int = 42,
) -> np.ndarray:
    """Return array of n_sims multiplier samples for my_v under a scenario."""
    rng = np.random.default_rng(seed)
    mults = np.empty(n_sims)
    for i in range(n_sims):
        others = sample_population(scenario_name, N, rng)
        mults[i] = speed_multiplier(my_v, others)
    return mults


def sample_multiplier_distribution_normal(
    my_v: int,
    mu: float,
    sigma: float,
    N: int = 50,
    n_sims: int = 20_000,
    seed: int = 42,
) -> np.ndarray:
    """Return array of multipliers for my_v when others ~ N(mu, sigma)."""
    rng = np.random.default_rng(seed)
    raw = rng.normal(mu, sigma, size=(n_sims, N - 1))
    others = np.clip(raw, 0, 100).round().astype(int)
    n_higher = (others > my_v).sum(axis=1)
    rank = n_higher + 1
    return SPEED_HIGH - (rank - 1) / (N - 1) * SPEED_RANGE
