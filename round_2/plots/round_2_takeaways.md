# Round 2 market takeaways

## Cleaning note
- Rows where both `bid_price_1` and `ask_price_1` were missing had `mid_price = 0.0`; those were treated as missing values before plotting or computing metrics.

## Key observations
- **Ash Coated Osmium** behaves like a stable anchor around **10000.9**, with average spread **16.2 ticks** (**16.2 bps**) and almost no directional drift (**-0.01 price units per 10k timestamps**).
- **Intarian Pepper Root** trends hard intraday, climbing roughly **10.0 price units per 10k timestamps**, which works out to about **999.7 points per day** on average.
- Top-of-book imbalance is a REAL signal in both assets. Correlation with the next **10**-tick mid move is **0.629** for Ash Coated Osmium and **0.651** for Intarian Pepper Root.
- Cross-asset return correlation is basically zero (**0.001**), so the two products look structurally different enough to model separately and diversify inventory risk.

## Mid-only regime diagnostics
- **Ash Coated Osmium**: `trend R² = 0.007`, `smooth eff50 = 0.001`, `drift/noise = 0.001`, `residual half-life = 2.63`. Eso grita **Stationary mean reversion / market making**.
- **Intarian Pepper Root**: `trend R² = 1.000`, `smooth eff50 = 0.926`, `drift/noise = 4.217`, `residual half-life = 0.70`. Acá el mejor encuadre es **Trend + pullback mean reversion**.
- Ojo: los dos assets tienen lag-1 autocorrelation de cambios de mid cerca de **-0.50** y **-0.50**. Eso significa que a micro-escala hay rebote de microestructura, incluso cuando el asset grande viene en tendencia.

## How to use this
- **Ash Coated Osmium** → Conviene anclar a un fair value casi estático, capturar spread y desvanecer excursiones en vez de perseguir momentum.
- **Intarian Pepper Root** → Usá una fair value móvil, sesgo de inventario a favor de la tendencia y entradas en pullbacks en vez de perseguir cada tick.
- Traducido a ejecución: no uses el mismo fair value para ambos. Uno necesita ancla casi fija; el otro necesita ancla móvil y sesgo de inventario a favor del drift.