# ash_mm_v0 — Validation Report

## Thesis
ASH_COATED_OSMIUM se comporta como un asset de fair value casi fijo alrededor de 10000; por eso la lógica correcta no es perseguir momentum sino hacer market making con anchor lento, skew por inventario y captura disciplinada de spread.

## Strategy Design
- Template base: bloque de EMERALDS de `round_0/models/model_v4.py`.
- Adaptación: anchor lento alrededor de 10000, clipped para no sobre-reaccionar, reservation price sesgado por inventario, quoting one-tick-inside y reparación táctica cuando el precio vuelve al fair.
- Interpretación financiera: el asset parece mean-reverting/stationary, así que la edge viene más de comprar barato/vender caro alrededor del ancla que de estimar drift fuerte.

## Tuned Parameters
- `POSITION_LIMIT` = `80`
- `BASE_FAIR` = `10000.0`
- `ANCHOR_ALPHA` = `0.03`
- `ANCHOR_CLIP_TICKS` = `6.0`
- `DEFAULT_QUOTE_OFFSET` = `1`
- `INVENTORY_SKEW_TICKS` = `3.5`
- `MAX_PASSIVE_SIZE` = `20`
- `SIZE_PRESSURE` = `1.2`
- `FAIR_REPAIR_MIN_POSITION` = `6`
- `FAIR_UNWIND_SAME_PRICE_VOLUME` = `20`

## Validation Snapshot
- Deterministic backtest total PnL: **63,335.0**
- Deterministic max drawdown: **-1,311.0**
- Replay total PnL: **57,123.5**
- Monte Carlo mean PnL: **57,393.3**
- Monte Carlo p05–p95: **53,136.5 → 61,165.5**
- Monte Carlo win rate: **100.0%**
- Monte Carlo mean sharpe-like: **2.75**
- Monte Carlo mean maker share: **50.6%**

## Interpretation
- El replay quedó MUY alineado con el backtest; eso es buena señal de robustez y de que la lógica no está sobreajustada a un simulador alternativo.
- Monte Carlo mantiene PnL positivo incluso en el percentil 5, lo que sugiere que la edge principal depende del régimen estructural del asset y no de una sola secuencia afortunada.
- El maker share ~50–58% tiene sentido financiero: la estrategia gana mayormente capturando spread, pero conserva flexibilidad para hacer takes de reparación cuando el inventario pide ayuda.
- El drawdown está contenido para el nivel de PnL obtenido; el costo es usar casi todo el inventario permitido en algunos tramos, algo razonable para un market maker en activo estacionario.

## Monte Carlo Method
- Método: stationary block bootstrap on synchronized book+trade records
- Bloque: 75 ticks
- Sesiones: 120
- Carpeta fuente: `/Users/pablo/Desktop/prosperity/round_1/results/montecarlo/ash_mm_v0/20260414_184904`