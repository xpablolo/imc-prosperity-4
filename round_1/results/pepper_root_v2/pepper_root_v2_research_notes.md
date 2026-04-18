# pepper_root_v2 — Research notes

## What I verified in the data

### 1) Pepper Root is NOT an EMERALDS-style asset
- Intraday linear slope is ~`0.1000` ticks per snapshot on each day.
- That is roughly **+1000 price points per day**.
- Daily linear fit `R²` is effectively ~`0.9999+`.
- So a fixed-fair market maker like round_0 EMERALDS would systematically lean the wrong way and sell too early.

### 2) It *does* have fast mean reversion — but around a moving trend line
Using a per-day linear trend fit on `mid_price`:
- residual std is only ~`2.0` to `2.36` ticks
- residual lag-1 autocorrelation is near zero (`~0.005` to `0.014`)

Interpretation:
- the **level** trends strongly upward
- the **residual around that trend** snaps back very quickly

This is why the correct playbook is **trend + pullback**, not pure trend chase and not pure stationary MM.

### 3) Pullbacks have real edge
Conditional future move after detrending:
- when residual `z < -1`, average future move is about:
  - `+5.90` ticks at 1 step
  - `+6.37` ticks at 5 steps
  - `+6.80` ticks at 10 steps
- when residual `z > +1`, average future move is about:
  - `-6.00` ticks at 1 step
  - `-5.48` ticks at 5 steps
  - `-5.07` ticks at 10 steps

So buying pullbacks and being careful with sells on rallies makes financial sense.

### 4) Top-of-book imbalance is strong
For `INTARIAN_PEPPER_ROOT`:
- corr(`imbalance_1`, future 10-step mid move) ≈ **`0.646`**
- when `imbalance > 0.3`, mean future 10-step move ≈ **`+4.15`** ticks
- when `imbalance < -0.3`, mean future 10-step move ≈ **`-2.26`** ticks

That is much stronger directional structure than what we saw in round_0 TOMATOES at the L1 level.

## Which round_0 model transfers?

### Bad transfer
- **EMERALDS / model_v4 EMERALDS block**: no
- Reason: that block assumes a near-fixed fair value and spread capture around it.

### Good conceptual transfer
- **TOMATOES model_v3 / model_v4 directional block**: yes, conceptually
- Reason: it already combines:
  - moving anchor
  - microstructure pressure
  - continuation filter
  - reversion on stretch
  - asymmetric passive quoting

But Pepper is even cleaner than round_0 TOMATOES, so parameters had to be pushed toward:
- **more long inventory tolerance**
- **lower inventory penalty**
- **stronger trend carry**
- **pullback-first execution** instead of neutral quoting

## Final implementation choice
Chosen model: `/Users/pablo/Desktop/prosperity/round_1/models/pepper_root_v2.py`

Key idea:
- use a **fast/slow EMA trend anchor** plus **forecast slope**
- overlay **L1/L2 imbalance** and **microprice**
- add an **asymmetric pullback adjustment** around the moving trend line
- use **target inventory** aligned with the trend instead of staying neutral
- quote more aggressively on the bid when the trend signal is positive

## Validation summary
- Replay total PnL: `113,972`
- Deterministic backtest total PnL (day-reset): `126,834.5`
- Monte Carlo mean PnL: `89,995.5`

## Important Monte Carlo fix
Raw block bootstrap was INVALID for Pepper because blocks from different days have different absolute price levels, which created artificial jumps.

So I fixed the Monte Carlo stitching to **shift each sampled block to the previous synthetic mid level** before concatenating it. That preserves local microstructure while removing fake level jumps.
