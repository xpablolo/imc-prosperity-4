# model_v3 — Combined round_1 summary

## Composition
- `ASH_COATED_OSMIUM`: logic from `/Users/pablo/Desktop/prosperity/round_1/models/ash_mm_v0.py`
- `INTARIAN_PEPPER_ROOT`: robust logic from `/Users/pablo/Desktop/prosperity/round_1/models/pepper_root_v3.py`

## Replay totals
- Ash: **57,123.5**
- Pepper: **117,769.5**
- Combined replay total: **174,893.0**

## Backtest totals
- Ash: **63,335.0**
- Pepper: **132,424.0**
- Combined backtest total: **195,759.0**

## Notes
- Ash was validated with the stationary market-making template.
- Pepper was upgraded to a more robust trend + pullback v3 with regime/inventory guards.
- The combined model dispatches by product in a single trader file: `/Users/pablo/Desktop/prosperity/round_1/models/model_v3.py`.
