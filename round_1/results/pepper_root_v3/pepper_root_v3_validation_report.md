# pepper_root_v3 — Validation Report

## Thesis
INTARIAN_PEPPER_ROOT muestra un drift intradía casi lineal y muy estable, pero con micro-pullbacks rápidos alrededor de esa tendencia. La lógica correcta no es mean reversion pura: es seguir la tendencia, comprar pullbacks y usar el libro para sesgar inventario y quotes.

## Strategy Design
- Template base: bloque conceptual de TOMATOES de `round_0/models/model_v3.py` / `model_v4.py`, no el de EMERALDS.
- Adaptación: anchor dinámico con fast/slow EMA + forecast de slope, microstructure overlay con L1/L2 imbalance y microprice, y pullback adjustment alrededor de la trend line.
- Interpretación financiera: Pepper recompensa llevar inventario a favor del drift y castiga vender demasiado temprano; por eso el quoting es asimétrico y los sells se frenan cuando la señal sigue larga.

## Tuned Parameters
- `POSITION_LIMIT` = `80`
- `MAX_PASSIVE_SIZE` = `18`
- `EMA_FAST_ALPHA` = `0.32`
- `EMA_SLOW_ALPHA` = `0.1`
- `FAST_WEIGHT` = `0.55`
- `SLOW_WEIGHT` = `0.3`
- `MID_WEIGHT` = `0.15`
- `TREND_FORECAST_HORIZON` = `24`
- `TREND_SLOPE_CLIP` = `0.18`
- `L1_IMBALANCE_BETA` = `1.1`
- `L2_IMBALANCE_BETA` = `4.4`
- `MICROPRICE_BETA` = `1.0`
- `CONTINUATION_BONUS` = `1.05`
- `PULLBACK_BONUS` = `1.55`
- `TARGET_INVENTORY_MAX` = `40`
- `INVENTORY_SKEW` = `0.14`
- `BASE_HALF_SPREAD` = `2`
- `VOL_MULTIPLIER` = `0.45`
- `TAKE_EDGE` = `1`
- `AGGRESSIVE_CAP` = `18`
- `SOFT_POSITION_LIMIT` = `60`
- `HARD_POSITION_LIMIT` = `76`
- `DIRECTIONAL_SIGNAL` = `1.15`

## Validation Snapshot
- Deterministic backtest total PnL: **132,424.0**
- Deterministic max drawdown: **-1,160.0**
- Replay total PnL: **117,769.5**
- Monte Carlo mean PnL: **97,999.1**
- Monte Carlo p05–p95: **85,217.5 → 111,574.1**
- Monte Carlo win rate: **100.0%**
- Monte Carlo mean sharpe-like: **5.20**
- Monte Carlo mean maker share: **26.1%**

## Interpretation
- Replay y backtest quedaron razonablemente alineados en magnitud y perfil diario, señal de que la tesis de trend + pullback sí captura el régimen dominante.
- Monte Carlo positivo en casi todo el rango sugiere que la edge depende del patrón estructural del asset: drift limpio + alpha de imbalance + reversión muy rápida de residual al trend.
- Un maker share más bajo que Ash es sano: Pepper necesita más iniciativa agresiva para enganchar los pullbacks y no quedarse mirando cómo sube el precio.
- El riesgo real no es “volatilidad pura”, sino descargar inventario demasiado pronto y perder carry del drift.

## Monte Carlo Method
- Método: stationary block bootstrap on synchronized book+trade records
- Bloque: 75 ticks
- Sesiones: 24
- Carpeta fuente: `/Users/pablo/Desktop/prosperity/round_1/results/montecarlo/pepper_root_v3/20260414_194515`
- Reset between days: `True`