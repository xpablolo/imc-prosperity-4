# IMC Prosperity Round 2 Manual — Iteration 3 summary

## 1. Executive summary

- I audited the existing `iter3_analysis.py` and kept what was already solid:
  - exact `Research/Scale` solver,
  - exact tie-aware ranking engine,
  - a useful first pass at the type mixture and the main plots.
- I then completed the missing pieces:
  - **expected regret vs the per-simulation best v**, not just regret vs the best mean EV,
  - **sensitivity to focal-point and just-above locations**,
  - a final markdown synthesis and notebook hand-off,
  - the required CSVs with the final recommendation.

- **Central recommendation:** `Speed* = 43`, `Research* = 15`, `Scale* = 42`.
- **Robust recommendation:** `v = 43` (same in this run).
- **More conservative recommendation:** `v = 46` if you want a hedge against a more speed-heavy field.
- **Broad sensitivity range:** `42–46`.
- **Core defendable range:** `42–46`.

## 2. Audit of the current iteration-3 implementation

| topic | status | detail |
| --- | --- | --- |
| Regret | needs_fix | The current iter3 script computes regret vs the best mean EV, not expected regret vs the per-simulation best action. |
| Sensitivity scope | needs_fix | The current iter3 script varies N and some weights, but not the exact location of focal-point and just-above clusters. |
| Artifacts | needs_fix | The existing iteration3 folder had plots/CSVs, but no markdown summary and no final notebook-level synthesis. |
| Ranking engine | ok | The tie-aware ranking logic itself is correct because rank depends only on the count of strictly higher speeds. |
| Research/Scale exact solver | ok | The exact integer subproblem is already correctly solved by compute_rs_table(). |

## 3. Exact Research/Scale subproblem

For each `v`, the remaining budget is `T = 100 - v`, and the exact integer split `r*(v), s*(v)` is solved first. Because both Research and Scale are increasing, the optimum always uses the whole budget, so `budget_used(v) = 50,000` for all feasible `v`.

### Key allocations around the candidate zone

| v | r_star | s_star | gross_value | budget_used |
| --- | --- | --- | --- | --- |
| 30.0 | 17.0 | 53.0 | 464702.0 | 50000.0 |
| 34.0 | 16.0 | 50.0 | 429728.6 | 50000.0 |
| 40.0 | 15.0 | 45.0 | 378480.0 | 50000.0 |
| 42.0 | 15.0 | 43.0 | 361658.7 | 50000.0 |
| 44.0 | 14.0 | 42.0 | 345025.3 | 50000.0 |
| 45.0 | 14.0 | 41.0 | 336810.4 | 50000.0 |

## 4. Exact ranking engine with ties

The rank engine remains exact:

- `rank(v) = # {players with strictly higher speed} + 1`
- all ties share the minimum rank of the tied block
- multiplier is linear from `0.9` (top rank) to `0.1` (bottom rank)

| example | my_speed | others | rank | multiplier |
| --- | --- | --- | --- | --- |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 70 | [70, 70, 50, 40, 40, 30] | 1 | 0.900 |
| ties | 50 | [70, 70, 70, 40, 40, 30] | 4 | 0.500 |
| ties | 40 | [70, 70, 70, 50, 40, 30] | 5 | 0.367 |
| ties | 40 | [70, 70, 70, 50, 40, 30] | 5 | 0.367 |
| ties | 30 | [70, 70, 70, 50, 40, 40] | 7 | 0.100 |
| three_players | 95 | [20, 10] | 1 | 0.900 |
| three_players | 20 | [95, 10] | 2 | 0.500 |
| three_players | 10 | [95, 20] | 3 | 0.100 |

## 5. Explicit type distributions used in the central mixture

### Weights

| type | weight |
| --- | --- |
| Nash-like / racionales | 0.20 |
| Focal points | 0.10 |
| Just-above focal points | 0.20 |
| AI / recomendaciones parecidas | 0.30 |
| Naive EV / incompleto | 0.10 |
| Speed-race agresivo | 0.05 |
| Random puro | 0.05 |

### Top masses by component and by total mixture

| component | top_speeds | top_probs_pct | mean_speed |
| --- | --- | --- | --- |
| nash_like | 32, 33, 31, 34, 30, 29, 35, 28 | 4.0%, 4.0%, 4.0%, 3.9%, 3.9%, 3.8%, 3.8%, 3.7% | 32.02 |
| focal_points | 33, 35, 34, 40, 30, 50, 20, 25 | 14.5%, 12.4%, 12.4%, 10.4%, 9.3%, 8.3%, 8.3%, 8.3% | 33.93 |
| just_above | 41, 31, 35, 36, 34, 21, 26, 46 | 14.0%, 13.0%, 12.0%, 12.0%, 10.0%, 9.0%, 8.0%, 8.0% | 33.28 |
| ai_similar | 37, 36, 38, 35, 39, 40, 34, 33 | 7.9%, 7.8%, 7.8%, 7.5%, 7.5%, 7.0%, 7.0%, 6.4% | 37.49 |
| naive_ev | 50, 51, 49, 48, 52, 53, 47, 54 | 2.2%, 2.2%, 2.2%, 2.2%, 2.2%, 2.2%, 2.2%, 2.2% | 50.00 |
| speed_race | 70, 69, 71, 68, 72, 67, 73, 66 | 3.3%, 3.3%, 3.3%, 3.3%, 3.3%, 3.2%, 3.2%, 3.2% | 69.81 |
| random_pure | 0, 64, 74, 73, 72, 71, 70, 69 | 1.0%, 1.0%, 1.0%, 1.0%, 1.0%, 1.0%, 1.0%, 1.0% | 50.00 |
| mixture_total | 35, 34, 36, 41, 31, 33, 40, 37 | 6.9%, 6.3%, 5.7%, 5.5%, 5.0%, 4.3%, 4.0%, 3.3% | 38.69 |

## 6. What total Speed distribution do these weights induce?

The main clusters of the field are: **35 (6.9%), 34 (6.3%), 36 (5.7%), 41 (5.5%), 31 (5.0%), 33 (4.3%)**.

Interpretation:

- `30` is a large focal/AI overlap.
- `33–36` is the equal-split / AI-adjacent / just-above battleground.
- `41–42` is the natural 'step above the 40 cluster' zone.
- `50+` still has mass, but much less than the central cluster.

## 7. Main Monte Carlo results (central mixture)

| v | mean_pnl | p10 | p90 | expected_regret | mean_multiplier | mean_rank | prob_best_response |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 41.0 | 198429.8 | 174307.3 | 222642.9 | 8508.6 | 0.7 | 15.0 | 0.2 |
| 42.0 | 199767.7 | 175114.1 | 222351.1 | 7170.7 | 0.7 | 13.8 | 0.2 |
| 43.0 | 200026.9 | 175646.2 | 221784.7 | 6911.5 | 0.7 | 12.8 | 0.1 |
| 44.0 | 199424.9 | 176026.8 | 221091.3 | 7513.6 | 0.7 | 11.8 | 0.1 |
| 45.0 | 197791.9 | 176144.2 | 214636.8 | 9146.6 | 0.7 | 11.1 | 0.1 |

### Reading the candidate zone

- `v = 43` is the **EV winner** in the central mixture.
- `v = 43` is also the **minimum expected regret** choice in the main run.
- `v = 46` gives up some EV, but improves the **worst-case sensitivity floor** when the field shifts upward.
- `v = 42–44` is the real central battleground; values below that are too exposed to the 40/41 cluster, and much above that you pay a clearer Research/Scale tax unless the field itself shifts upward.

## 8. Sensitivity

### Best v across sensitivity runs

| label | best_v | robust_v | best_ev |
| --- | --- | --- | --- |
| N=20 | 43 | 43 | 199692.1 |
| N=35 | 43 | 43 | 199833.6 |
| N=50 | 43 | 43 | 199369.5 |
| N=75 | 43 | 43 | 200193.5 |
| N=100 | 43 | 43 | 200084.8 |
| AI version = base | 43 | 43 | 199677.4 |
| AI version = concentrated | 42 | 42 | 212271.9 |
| AI version = higher | 46 | 46 | 181762.6 |
| AI weight = 20% | 42 | 42 | 199494.3 |
| AI weight = 30% | 43 | 43 | 200341.8 |
| AI weight = 40% | 46 | 46 | 201299.2 |
| AI weight = 50% | 46 | 46 | 204272.3 |
| Just-above weight = 10% | 43 | 43 | 200559.8 |
| Just-above weight = 20% | 43 | 43 | 200038.5 |
| Just-above weight = 30% | 42 | 42 | 199632.5 |
| Focal weight = 5% | 46 | 46 | 200407.5 |
| Focal weight = 10% | 43 | 43 | 199942.7 |
| Focal weight = 15% | 42 | 42 | 199158.9 |
| Focal weight = 20% | 42 | 42 | 199347.9 |
| Focal locations = base | 43 | 43 | 200063.8 |
| Focal locations = round_heavy | 43 | 43 | 201645.2 |
| Focal locations = low_mid | 43 | 43 | 203143.6 |
| Just-above locations = base | 43 | 43 | 199714.3 |
| Just-above locations = lower | 43 | 43 | 201829.8 |
| Just-above locations = higher | 43 | 43 | 200135.4 |

### Count of scenario winners

| v | count |
| --- | --- |
| 42 | 5 |
| 43 | 16 |
| 46 | 4 |

### Scenario-aggregated surface

| v | mean_ev_across_scenarios | median_ev_across_scenarios | min_ev_across_scenarios | p25_ev_across_scenarios | p75_ev_across_scenarios | mean_expected_regret_across_scenarios | max_expected_regret_across_scenarios |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 41.0 | 197234.7 | 198235.9 | 170410.3 | 197887.9 | 198767.6 | 9592.3 | 17643.5 |
| 42.0 | 199370.8 | 199671.4 | 173171.5 | 199469.9 | 199976.9 | 7456.2 | 14882.3 |
| 43.0 | 199584.7 | 200063.8 | 175323.2 | 199677.4 | 200559.8 | 7242.3 | 13593.3 |
| 44.0 | 198882.8 | 199382.6 | 176763.6 | 198976.1 | 200334.6 | 7944.2 | 14309.3 |
| 45.0 | 197283.0 | 197783.6 | 177587.1 | 197347.9 | 199101.2 | 9544.0 | 15937.5 |
| 46.0 | 198832.5 | 199454.7 | 181762.6 | 199002.1 | 199650.8 | 7994.5 | 14344.2 |

Interpretation:

- `43` is the centre of gravity across the sensitivity battery.
- `42` is the nearest competing value when the field shifts slightly lower or more focal-heavy.
- `46` is the hedge that becomes attractive when the field moves materially higher in Speed.

## 9. Final recommendation

| criterion | v | r | s | gross_value | expected_pnl | p10_pnl | p90_pnl | expected_regret | prob_best_response | broad_sensitivity_range_low | broad_sensitivity_range_high | core_defendable_range_low | core_defendable_range_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Max EV (central mixture) | 43 | 15 | 42 | 353248.0 | 200026.9 | 175646.2 | 221784.7 | 6911.5 | 0.1 | 42 | 46 | 42 | 46 |
| Robust (min expected regret) | 43 | 15 | 42 | 353248.0 | 200026.9 | 175646.2 | 221784.7 | 6911.5 | 0.1 | 42 | 46 | 42 | 46 |
| Conservative (best min EV across sensitivity) | 46 | 14 | 40 | 328595.6 | 199535.7 | 181358.1 | 218911.9 | 7402.7 | 0.2 | 42 | 46 | 42 | 46 |

### Why 43?

- It sits **just above the 41/42 bottleneck**, which is one of the main step-up zones created by the mixture.
- It still preserves a strong exact economic split: `r = 15`, `s = 42`.
- It wins on central EV **and** on main-run expected regret.

### When would I move to 46?

- If you want a more conservative hedge against the possibility that other players cluster a bit higher than the central mixture suggests.
- `46` is not the central EV leader, but it scores best on the worst EV across the tested sensitivity battery here.

## 10. Direct answers to the requested questions

1. **What total distribution of Speed do these weights induce?**
   - A highly clustered field with major mass around `34–36`, another clear knot at `41–42`, and secondary mass in the high 40s / 50+ tail; see the PMF/CDF plots and the cluster summary above.
2. **Where are the main clusters of the other players?**
   - `34–36` and `41–42` are the main tactical clusters, with secondary mass at `30–31` and a tail in `46+ / 50+` from naive and speed-race players.
3. **Which values exploit those clusters best?**
   - `43` best exploits the `41–42` step-up logic while keeping strong Research/Scale economics. `42–44` are the nearby robust alternatives, and `46` is the upward hedge.
4. **What allocation would I recommend under this mixture?**
   - Central: `v = 43`, `r = 15`, `s = 42`.
   - More conservative: `v = 46`, `r = 14`, `s = 40`.
5. **How sensitive is the recommendation to small changes in AI/focal/just-above?**
   - The full best-v range in the tested sensitivity set is `42–46`, but the centre of gravity is clearly around `43`, and the tighter core is `42–46`.

## 11. Main artifact paths

- Notebook: `/Users/pablo/Desktop/prosperity/round_2/manual/manual_round2_analysis_iteration3.ipynb`
- Summary markdown: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration3/manual_round2_summary_iteration3.md`
- Plots folder: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration3/plots`
- CSV folder: `/Users/pablo/Desktop/prosperity/round_2/manual/results/iteration3/csv`
