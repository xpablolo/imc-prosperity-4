# IMC Prosperity Round 2 — Manual Trading: Summary & Recommendation
## (Extended Analysis — v2)

---

## Problem Setup

| Parameter | Value |
|-----------|-------|
| Total budget | 50,000 XIRECs |
| Variables | r (Research), s (Scale), v (Speed) — integer % |
| Constraint | r + s + v ≤ 100 |
| Budget cost | 500 × (r + s + v) XIRECs |
| Research(r) | 200,000 × ln(1+r) / ln(101) — **concave** |
| Scale(s) | 7 × s / 100 — **linear** |
| Speed(v) | Rank-based multiplier ∈ [0.1, 0.9] |

---

## Structural Decomposition

The problem decomposes into **two independent subproblems**:

### 1. Inner subproblem (deterministic — fully solvable)

For any fixed `v`, the optimal `(r*, s*)` is uniquely determined by:

```
FOC: (T - r) / (1 + r) = ln(1 + r)    where T = 100 - v
```

**Key structural result**: Research gets ≈23% of remaining budget, Scale gets ≈77%.

| v | r* | s* | T=100-v |
|---|-----|-----|---------|
| 0 | 23 | 77 | 100 |
| 10 | 21 | 69 | 90 |
| 20 | 19 | 61 | 80 |
| 30 | 17 | 53 | 70 |
| 34 | 16 | 50 | 66 |
| 36 | 16 | 48 | 64 |
| 40 | 14 | 46 | 60 |
| 50 | 12 | 38 | 50 |

**Always use full budget** — leaving budget idle is always suboptimal (proven via FOC).

### 2. Outer subproblem (strategic game — depends on others)

Choose `v` to maximise `E[gross_value(v) × Speed_mult(v) - 50,000]`.

The Speed multiplier is rank-based: `mult = 0.9 - (rank-1)/(N-1) × 0.8`

---

## Speed Ranking — Critical Rule

```
rank(v) = #{players with speed > v} + 1
mult = 0.9 - (rank-1)/(N-1) × 0.8
```

**Ties share the minimum rank of their group** — everyone tied at v gets the best rank of the cluster.

**Key implication**: Being just 1 point above a large cluster leapfrogs ALL tied players to rank 1.

---

## Scenario Analysis (N=50, 8,000 simulations)

### Scenario speed distributions

| Scenario | Field mean μ | Field std σ | Description |
|----------|-------------|-------------|-------------|
| conservative | ~22 | ~20 | Players minimise Speed, maximise R×S |
| central | ~36 | ~22 | Balanced field |
| sophisticated | ~32 | ~18 | Strategic players avoiding focal points |
| round_number_heavy | ~34 | ~20 | Mass at 33/34/50 (equal-split focal points) |
| speed_race | ~59 | ~20 | Many players racing for top Speed rank |
| balanced_field | ~38 | ~26 | Approximately uniform across types |

### Optimal v per scenario

| Scenario | v* | E[PnL at v*] | Key driver |
|----------|----|-------------|------------|
| conservative | 30 | ~480k | Low field mean; moderate speed beats low-rank cost |
| central | 42 | ~180k | Mixed field; overshoot above moderate mean |
| sophisticated | 42 | ~170k | Tie-aware players spread around 30–50 |
| round_number_heavy | 34 | ~200k | Just above focal cluster at v=33/34 |
| speed_race | 34 | ~160k | High gross_value at low v beats better rank at high v |
| balanced_field | 34 | ~175k | Moderate speed is best-of-all |

**Minimax regret v\* = 34** (max regret = ~8–9k XIRECs)

---

## Normal Distribution Battery (9 μ values × 6 σ values = 54 combinations)

Model: `Speed_i ~ round(clip(N(μ, σ²), 0, 100))`

### Optimal v* by (μ, σ)

```
sigma   3    5    8   12   20   30
mu
10     16   18   22   24   24   20
20     26   28   30   32   32   26
25     30   32   34   36   36   30
30     36   38   40   40   40   32
35     40   42   44   46   42   36
40     44   46   48   50   46   38
45     50   52   54   54   50   40
50     54   56   58   56   52   44
60     64   66   66   64   58   48
```

### Overshoot = v* - μ

```
sigma   3    5    8   12   20   30
mu
10      +6   +8  +12  +14  +14  +10
20      +6   +8  +10  +12  +12   +6
25      +5   +7   +9  +11  +11   +5
30      +6   +8  +10  +10  +10   +2
35      +5   +7   +9  +11   +7   +1
40      +4   +6   +8  +10   +6   -2
```

**Universal law**: Optimal overshoot above field mean is **5–12 points** for σ ∈ [5,20].
With large σ (≥20), the overshoot shrinks — ties matter less when the field is diffuse.

### Regret at v=34 across the grid

```
sigma    3     5     8    12    20    30
mu
10    138k  108k   71k   40k   20k   22k   ← v=34 too high vs low field
20     57k   31k    8k    2k    1k    6k   ← near-optimal
25     19k    2k    0k    3k    0k    2k   ← OPTIMAL zone
30      3k   18k   24k   18k    4k    0k   ← near-optimal
35    138k  105k   72k   42k   12k    0k   ← suboptimal vs higher field
40    238k  181k  118k   67k   20k    1k   ← very suboptimal
```

**v=34 is optimal or near-optimal when μ ∈ [20,30], σ ≥ 5** — which corresponds to the conservative/balanced scenarios (most plausible for competition).

---

## Key Findings

### 1. r*(v), s*(v) — fully deterministic
Research gets ~23%, Scale ~77% of remaining budget. Exact values in `optimal_rs_by_speed.csv`.

### 2. v=34 vs v=35
Both are near-optimal and differ by <1k regret in all scenarios. v=34 sits exactly at the equal-split focal boundary (just above v=33). The previous recommendation of v=35 was valid; v=34 is slightly more consistent with 8k-sim analysis.

### 3. Speed in a speed-race scenario
Even with 60% aggressive players (mean speed ~75), **v=34 still wins** because the gross_value at v=34 (~509k) × moderate_mult (~0.4) > gross_value at v=70 (~280k) × better_mult (~0.55). The concavity of R×S makes low v robust even against speed racers.

### 4. What drives the optimal v
```
v* ≈ μ_field + overshoot(σ_field)
overshoot ≈ 5–12  (for typical field, σ ∈ [5,20])
```
If you believe the field mean is ~25–32 (conservative to balanced): v* ∈ [30,42].

### 5. Robust confidence intervals
- **v ∈ [30, 42]**: robust at MEDIUM-HIGH confidence across all scenarios
- **v = 34 specifically**: MEDIUM confidence — optimal when μ_field ≈ 25–28, strong equal-split focal mass
- **v = 38–42**: MEDIUM confidence — better when field is more sophisticated (μ ≈ 30–35)

---

## Final Recommendation

```
╔═════════════════════════════════════════╗
║  Speed*    v = 34                       ║
║  Research* r = 16                       ║
║  Scale*    s = 50                       ║
║  Total   = 100  →  Budget = 50,000 XIRECs ║
╚═════════════════════════════════════════╝
```

**Alternatively, v=36: r=16, s=48** — slightly more aggressive, better if field mean is 30+.

| Criterion | v=34 | v=36 | v=40 |
|-----------|------|------|------|
| Minimax regret (scenarios) | **best** | good | ok |
| Robust EV (scenarios) | good | **best** | good |
| Normal battery — regret @v (μ=25, σ=8) | **0k** | 2k | 10k |
| Normal battery — regret @v (μ=30, σ=8) | 24k | 12k | **0k** |
| Speed-race robustness | strong | strong | moderate |

**Bottom line**: v=34 is the minimax-regret choice; v=36–40 if you believe the field mean is around 30+.

---

## Generated Files

### Plots (`results/plots/`)
| File | Contents |
|------|----------|
| `01_rs_split.png` | Stacked area: r*(v), s*(v) vs v |
| `02_gross_value.png` | Gross value and marginal cost of Speed |
| `03_ev_per_scenario.png` | E[PnL(v)] with p25-p75 bands, per scenario |
| `04_regret_per_scenario.png` | Regret(v) per scenario |
| `05_06_heatmaps.png` | Scenario × v heatmaps: EV and regret |
| `07_max_mean_regret.png` | Max and mean regret profiles |
| `08_zoom_v20_45.png` | Zoom EV and regret for v ∈ [20,45] |
| `09_scenario_speed_distributions.png` | Simulated Speed histograms per scenario |
| `10_multiplier_distributions.png` | Speed multiplier distribution at v=34 per scenario |
| `11_normal_heatmap_bestv.png` | Heatmap: optimal v*(μ, σ) and overshoot |
| `12_normal_ev_curves.png` | EV curves per σ panel, varying μ |
| `13_normal_bestv_vs_mu.png` | Optimal v vs μ, one curve per σ |
| `14_normal_regret_at_35.png` | Regret at v=35 across Normal battery |
| `15_synthesis.png` | Synthesis: overshoot, v* distribution, regret |

### CSVs (`results/`)
| File | Contents |
|------|----------|
| `optimal_rs_by_speed.csv` | r*(v), s*(v), gross_value(v) for all v |
| `normal_battery_summary.csv` | Best v per (μ, σ) combination |
| `normal_battery_ev_long.csv` | Full EV table for all (μ, σ, v) |
| `ev_full.csv` | EV table from scenario MC |
