# No-limit comparison for model_A / model_B / model_C

## Combined totals

| Model | Backtest total | Replay no-limit total | Pepper backtest | Pepper replay no-limit | Pepper max abs pos | Pepper max DD |
|---|---:|---:|---:|---:|---:|---:|
| model_A | 186,851.5 | 168,094.5 | 123,703.5 | 111,305.0 | 89 | -1,201 |
| model_B | 195,369.5 | 165,475.0 | 132,221.5 | 108,685.5 | 108 | -1,728 |
| model_C | 295,947.5 | 266,616.5 | 232,799.5 | 209,827.0 | 180 | -3,879 |

## Lectura rápida

- `model_A` es el más conservador de los tres: menos PnL en Pepper pero drawdown y posición todavía contenidos.
- `model_B` quedó como punto medio: en backtest apenas supera a `model_A`, pero en replay sin límite rinde peor que `model_A`.
- `model_C` es el agresivo de verdad: domina fuerte en backtest y también en replay sin límite, a costa de mucho más inventario y drawdown.

## Artefactos

- `/Users/pablo/Desktop/prosperity/round_1/results/model_abc_nolimit_comparison.csv`
- `/Users/pablo/Desktop/prosperity/round_1/results/model_abc_pepper_replay_nolimit_by_day.csv`
