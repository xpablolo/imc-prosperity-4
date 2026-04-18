# Round 1 deep research report

## Executive summary

I inspected the workspace data for Round 1 and found usable raw market data in `data/round_1/` for both products across days -2, -1, and 0. The `/mnt/data` paths mentioned in the prompt were not present in this environment, so I used the workspace equivalents.

The high-confidence conclusion is the same at a deeper level:
- **ASH_COATED_OSMIUM** behaves like a near-stationary product around ~10000 with small, unstable drift and strong short-horizon order-book imbalance / microprice information.
- **INTARIAN_PEPPER_ROOT** behaves like a nearly linear upward moving fair value with day-to-day slope stability and only tiny residual pullbacks around that trend.

Two important refinements came out of the deeper analysis:
1. The one-tick negative autocorrelation in both products is mostly microstructure. It persists at multiple short horizons, so it is **not** safe to read it as a clean tradable mean-reversion edge by itself.
2. Pepper has a very strong trend, but the order-book imbalance signal is still present and is **stronger in wide-spread regimes**, not obviously in narrow-spread regimes. That is a useful correction to the initial intuition.

## Data inventory

| filename | granularity | rows | products | time_span | limitations |
|---|---|---|---|---|---|
| data/round_1/prices_round_1_day_-2.csv | event / quote snapshots | 20000 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 0..999900 | Missing best quote fields on ~8% of rows; 49 mid_price=0 rows total |
| data/round_1/prices_round_1_day_-1.csv | event / quote snapshots | 20000 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 0..999900 | Missing best quote fields on ~8% of rows; 49 mid_price=0 rows total |
| data/round_1/prices_round_1_day_0.csv | event / quote snapshots | 20000 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 0..999900 | Missing best quote fields on ~8% of rows; 49 mid_price=0 rows total |
| data/round_1/trades_round_1_day_-2.csv | trade events | 773 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 700..997500 | Buyer/seller metadata absent (all NaN) |
| data/round_1/trades_round_1_day_-1.csv | trade events | 760 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 2800..998300 | Buyer/seller metadata absent (all NaN) |
| data/round_1/trades_round_1_day_0.csv | trade events | 743 | ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT | 200..998400 | Buyer/seller metadata absent (all NaN) |

### Main data limitations
- There is no separate event-level raw order-book stream beyond the price snapshots and trades files in `data/round_1/`.
- Best-bid/best-ask fields are missing on about 8% of quote rows, so order-book signal tests must use the book-valid subset.
- The trade files do not contain buyer/seller identities; only price, quantity, timestamp, and symbol are available.

## Product-by-product analysis

### ASH_COATED_OSMIUM

| day | start_mid | end_mid | net_move | trend_per_10k_ts | trend_r2 | residual_std | residual_half_life | lag1_mid_change_autocorr | raw_variance_ratio_20 | avg_spread | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|
| -2.0000 | 10010.0000 | 9993.5000 | -16.5000 | -0.0139 | 0.0059 | 5.2045 | 2.2801 | -0.5005 | 0.0559 | 16.1498 | 429.0000 |
| -1.0000 | 10003.0000 | 10002.0000 | -1.0000 | -0.0088 | 0.0033 | 4.4428 | 1.6062 | -0.4980 | 0.0563 | 16.1913 | 425.0000 |
| 0.0000 | 10013.0000 | 10007.0000 | -6.0000 | 0.0155 | 0.0062 | 5.6662 | 2.9057 | -0.4873 | 0.0569 | 16.1845 | 411.0000 |

**What is strongly supported by the data**
- The product is centered near 10000, with a very small day-level trend relative to its spread and intraday range.
- Linear trend explains almost nothing economically meaningful: day-level R² is around 0.003-0.006.
- The imbalance signal is robust: correlation with future return is around 0.57-0.61 across horizons and days; microprice improves short-horizon MSE versus raw mid by roughly 4-11%.

**What is plausible but weaker**
- There is some short-horizon mean reversion after detrending, but the effect is not so clean that I would call it a pure stationary Ornstein-Uhlenbeck style series.
- A weak quadratic / curvature component may exist, but it does not generalize strongly enough across days to claim a stable intraday shape.

**What is not supported**
- A strong or stable intraday directional trend.
- A claim that trade activity is a useful standalone alpha signal; the correlations with future returns are tiny and unstable.

### INTARIAN_PEPPER_ROOT

| day | start_mid | end_mid | net_move | trend_per_10k_ts | trend_r2 | residual_std | residual_half_life | lag1_mid_change_autocorr | raw_variance_ratio_20 | avg_spread | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|
| -2.0000 | 9998.5000 | 11001.5000 | 1003.0000 | 10.0003 | 1.0000 | 2.0095 | 0.1599 | -0.4956 | 0.0503 | 11.9948 | 344.0000 |
| -1.0000 | 10998.5000 | 11998.0000 | 999.5000 | 10.0008 | 0.9999 | 2.2206 | 0.1522 | -0.4949 | 0.0505 | 13.0123 | 335.0000 |
| 0.0000 | 11998.5000 | 13000.0000 | 1001.5000 | 10.0008 | 0.9999 | 2.3599 | 0.1186 | -0.5093 | 0.0501 | 14.1287 | 332.0000 |

**What is strongly supported by the data**
- The price path is almost a straight line upward each day. The fitted slope is ~10 per 10k timestamp units, with R² above 0.9999 on every day.
- The day-to-day slope is extremely stable.
- Once detrended, the residual is tiny relative to the main move; short-horizon pullbacks exist, but they are much smaller than the dominant drift.
- Passive symmetric quoting is structurally dangerous because the main risk is being carried against the trend.

**What is plausible but weaker**
- There is a residual mean-reverting component around the moving fair value, but it is much smaller than the trend. This is more a tactical timing effect than a primary alpha source.
- The order-book imbalance signal is real and stable, but it is subordinate to the trend and should be interpreted as timing around the moving fair, not as the main driver.

**What is not supported**
- Any idea that the product is close to stationary around a fixed fair value.
- Any assumption that time-of-day directional effects are noisy or unstable; the main path itself is almost perfectly repeatable.

## Cross-asset comparison

| product | trend_per_10k_mean | trend_r2_mean | residual_std_mean | residual_half_life_mean | avg_spread_mean | trade_count_total |
|---|---|---|---|---|---|---|
| ASH_COATED_OSMIUM | -0.0024 | 0.0051 | 5.1045 | 2.2640 | 16.1752 | 1265 |
| INTARIAN_PEPPER_ROOT | 10.0006 | 0.9999 | 2.1967 | 0.1436 | 13.0453 | 1011 |

### The key contrast
- **ASH**: stationary/fair-value archetype, microstructure-driven, alpha comes mostly from imbalance / microprice / short-horizon mean reversion.
- **Pepper**: trend-dominant moving-fair archetype, alpha comes first from the directional drift and second from tactical timing around that drift.

## Deep price-process analysis

### Trend model comparison

The per-day model comparison shows that:
- For **ASH**, a linear trend is only a tiny improvement over intercept-only; quadratic terms fit a bit of in-sample curvature but do not generalize cleanly enough to matter.
- For **Pepper**, a linear trend is already sufficient; quadratic terms do not improve the fit in any meaningful way.

| product | day | intercept | linear | quadratic |
|---|---|---|---|---|
| ASH_COATED_OSMIUM | -2 | 0.0000 | 0.0059 | 0.1008 |
| ASH_COATED_OSMIUM | -1 | 0.0000 | 0.0033 | 0.0517 |
| ASH_COATED_OSMIUM | 0 | -0.0000 | 0.0062 | 0.0204 |
| INTARIAN_PEPPER_ROOT | -2 | 0.0000 | 1.0000 | 1.0000 |
| INTARIAN_PEPPER_ROOT | -1 | 0.0000 | 0.9999 | 0.9999 |
| INTARIAN_PEPPER_ROOT | 0 | 0.0000 | 0.9999 | 0.9999 |

### Return / increment structure

- Both products have a very strong one-tick negative autocorrelation in raw mid changes, around -0.49 to -0.51.
- That negative autocorrelation decays quickly to near zero at longer lags, which is a signature of microstructure effects rather than a clean long-memory signal.
- Variance ratios are far below 1 at horizons 20, 50, and 100, so the raw series are anti-persistent in short increments.

### Residual structure

- For **ASH**, detrending leaves a stationary-looking residual with a half-life of a few ticks, not an immediate snap-back and not a random walk.
- For **Pepper**, detrending leaves a very small residual; the main structure is the trend itself.

## Day-pattern and time-pattern analysis

Normalized intraday paths were compared after binning each day into 100 equal sections.

| product | feature | pairwise_corr_mean |
|---|---|---|
| ASH_COATED_OSMIUM | mid_price | -0.1175 |
| ASH_COATED_OSMIUM | spread | -0.0602 |
| ASH_COATED_OSMIUM | abs_ret | 0.2096 |
| ASH_COATED_OSMIUM | imbalance | 0.0440 |
| ASH_COATED_OSMIUM | trade_count | -0.1270 |
| INTARIAN_PEPPER_ROOT | mid_price | 1.0000 |
| INTARIAN_PEPPER_ROOT | spread | 0.6128 |
| INTARIAN_PEPPER_ROOT | abs_ret | 0.2592 |
| INTARIAN_PEPPER_ROOT | imbalance | -0.0018 |
| INTARIAN_PEPPER_ROOT | trade_count | -0.0672 |

### Interpretation
- **Pepper mid path** is almost perfectly repeatable day-to-day (pairwise correlation ~1.0).
- **ASH mid path** is not repeatable in a strong directional sense; day-to-day correlations are near zero or mildly negative.
- Trade activity does **not** show a stable intraday shape across days, so it is not a robust standalone state variable.

## Order book / microstructure signal analysis

### Imbalance signal quality

| product | horizon | imbalance_corr_future_return | micro_corr_future_return | microprice_mse_ratio_vs_mid | imbalance_directional_hit_rate |
|---|---|---|---|---|---|
| ASH_COATED_OSMIUM | 1 | 0.5869 | 0.4996 | 0.9301 | 0.6021 |
| ASH_COATED_OSMIUM | 5 | 0.5480 | 0.4662 | 0.9553 | 0.4908 |
| ASH_COATED_OSMIUM | 10 | 0.5206 | 0.4420 | 0.9499 | 0.4347 |
| ASH_COATED_OSMIUM | 20 | 0.4699 | 0.4018 | 0.9576 | 0.3844 |
| ASH_COATED_OSMIUM | 50 | 0.3846 | 0.3293 | 0.9710 | 0.3236 |
| ASH_COATED_OSMIUM | 100 | 0.3176 | 0.2722 | 0.9772 | 0.2929 |
| INTARIAN_PEPPER_ROOT | 1 | 0.5639 | 0.4569 | 0.9017 | 0.6328 |
| INTARIAN_PEPPER_ROOT | 5 | 0.5608 | 0.4556 | 0.9048 | 0.3738 |
| INTARIAN_PEPPER_ROOT | 10 | 0.5667 | 0.4608 | 0.9201 | 0.2815 |
| INTARIAN_PEPPER_ROOT | 20 | 0.5649 | 0.4605 | 0.9553 | 0.1951 |
| INTARIAN_PEPPER_ROOT | 50 | 0.5607 | 0.4557 | 0.9881 | 0.1659 |
| INTARIAN_PEPPER_ROOT | 100 | 0.5616 | 0.4573 | 0.9960 | 0.1574 |

Main takeaways:
- Imbalance predicts future returns in **both** products, and the relation is stable across days.
- Microprice is a modest but consistent improvement over raw mid for short-horizon fair-value estimation.
- For **Pepper**, the imbalance signal is actually stronger in **wide-spread** regimes than in narrow-spread regimes; that weakens the naive hypothesis that narrow spreads are always the best timing windows.

### Spread dynamics

- Spread is fairly stable in each product: around 16.18 for Ash and 11.99 / 13.01 / 14.13 for Pepper by day.
- Spread is mildly persistent, but not strongly so.
- Wider spreads are associated with *smaller* subsequent absolute moves in these data, which is counterintuitive but consistent across days.

### Trade flow and activity

- Trade count / trade quantity have very small correlations with future price direction and only weak correlations with future volatility.
- Activity is not the main alpha source here; it is more a context variable than a predictive signal.

## Candidate hidden patterns

| product | hypothesis | confidence | robustness |
|---|---|---|---|
| ASH_COATED_OSMIUM | Fixed fair value near 10000 with no meaningful drift | high | stable across all 3 days |
| ASH_COATED_OSMIUM | Short-horizon mean reversion around fair value | medium | moderately stable |
| ASH_COATED_OSMIUM | Predictive order book imbalance / microprice signal | high | stable across all 3 days |
| ASH_COATED_OSMIUM | No reliable time-of-day directional pattern | high | stable across days |
| INTARIAN_PEPPER_ROOT | Fair value increases approximately linearly with timestamp | very high | extremely stable across all 3 days |
| INTARIAN_PEPPER_ROOT | Residual around moving fair is mean-reverting at short horizons | medium-high | stable across all 3 days |
| INTARIAN_PEPPER_ROOT | Imbalance improves timing around moving fair | high | stable across all 3 days |
| INTARIAN_PEPPER_ROOT | Intraday path is highly repeatable day-to-day | very high | extremely stable |
| INTARIAN_PEPPER_ROOT | Passive symmetric quoting would suffer adverse selection | high | stable across all 3 days |

I would treat the following as the main robust hidden patterns:
- Ash: fixed fair value + imbalance-driven short-horizon reversion.
- Pepper: linear moving fair + directional inventory bias + tactical pullback timing.

## Anti-overfitting assessment

- The strongest conclusions are stable across days -2, -1, and 0.
- I did **not** rely on a single threshold or a single horizon; the imbalance signal persists across 1, 5, 10, 20, 50, and 100 quote-update horizons.
- The negative autocorrelation of raw increments is not by itself a tradable alpha; it is likely dominated by microstructure bounce.
- Any quadratic / curvature effect in Ash should be treated as speculative until it passes explicit out-of-sample day tests.

## Implications for future strategy design

### ASH_COATED_OSMIUM
- Most justified future family: **stationary fair-value market making / reversion with imbalance-aware shading**.
- Dangerous / unsupported: pure trend-following, time-of-day directional bias, or heavy reliance on trade activity.
- Likely core state variables: best-bid/best-ask imbalance, microprice, spread regime, short-horizon residual.
- Likely red herrings: global trend, long-memory in raw returns, and trade count alone.

### INTARIAN_PEPPER_ROOT
- Most justified future family: **moving-fair directional strategy with residual pullback timing**.
- Dangerous / unsupported: symmetric passive quoting without inventory control, or treating the product like a stationary mean-reversion asset.
- Likely core state variables: trend / fair-value slope, residual-to-fair, imbalance, spread regime, and inventory state.
- Likely red herrings: trade count as a standalone edge, or a fixed fair value near the day mean.

## Final conclusion

The data support two very different research tracks. Ash looks like a stationary microstructure product with a useful imbalance signal. Pepper looks like a moving-fair product with an almost deterministic upward drift and only a small residual timing component. The right next step is not to code strategies yet, but to validate which *state variables* really survive simple out-of-sample tests and whether the imbalance effect survives stricter controls on time, spread, and inventory.

## What I would test next before writing any strategy code

1. Leave-one-day-out validation of the imbalance signal for both products, using only the book-valid subset and fixed horizons.
2. A stricter decomposition of Pepper into trend + residual to confirm how much of the imbalance effect survives after controlling for the moving fair value.
3. A spread-conditioned analysis of both products with coarse bins only, to avoid over-interpreting discrete imbalance quantization.
4. Separate early / mid / late session tests to see whether the alpha is time-stable or concentrated in a small part of the day.
5. A simple execution-cost sanity check: compare the expected edge from imbalance / microprice against the average spread and likely slippage.

## Key supporting files
- Report: `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/round_1_deep_research_report.md`
- Data inventory: `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/data_inventory.csv`
- Product-day metrics: `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/product_day_metrics.csv`
- Signal tables: `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/imbalance_signal_table.csv`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/spread_regime_table.csv`
- Figures: `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/mid_paths_by_day.png`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/detrended_residuals_by_day.png`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/horizon_signal_strength.png`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/intraday_normalized_paths.png`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/intraday_similarity_heatmap.png`, `/Users/pablo/Desktop/prosperity/round_1/results/deep_research/spread_regime_signal.png`