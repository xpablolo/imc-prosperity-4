# model_v4 summary

## Qué cambia
- `ASH_COATED_OSMIUM`: overlay microestructural moderado sobre el market maker estacionario de `model_v3`.
- `INTARIAN_PEPPER_ROOT`: carry mode más robusto y slope shrinkage con piso dinámico de inventario.

## Validación
### Replay vs baseline guardado de `model_v3`
- Ash: 56,789.5 vs 57,123.5 (Δ -334.0)
- Pepper: 120,538.0 vs 117,769.5 (Δ +2,768.5)
- Combined: 177,327.5 vs 174,893.0 (Δ +2,434.5)

### Backtest vs baseline guardado de `model_v3`
- Ash: 63,148.0 vs 63,335.0 (Δ -187.0)
- Pepper: 132,076.5 vs 132,424.0 (Δ -347.5)
- Combined: 195,224.5 vs 195,759.0 (Δ -534.5)

## Lectura honesta
- `model_v4` mejora claramente el replay combinado gracias a Pepper.
- En Ash la mejora quedó deliberadamente moderada: baja un poco el PnL bruto frente al baseline guardado, pero mantiene drawdown más controlado y explota micro-alpha sin romper la lógica de market making.
- En Pepper el carry mode suma agresividad útil sin convertir la estrategia en una persecución ciega del drift.

## Artefactos
- `/Users/pablo/Desktop/prosperity/round_1/results/model_v4/model_v4_vs_model_v3_scorecard.png`
- `/Users/pablo/Desktop/prosperity/round_1/results/model_v4/model_v4_vs_model_v3_metrics.csv`
- `/Users/pablo/Desktop/prosperity/round_1/models/model_v4.py`
