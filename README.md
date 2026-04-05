# IMC Prosperity 4 (Trading Challenge)

This repository is where I'm building and iterating on strategies for the IMC Prosperity trading challenge.

## What the challenge is

The IMC Prosperity challenge is an algorithmic trading competition where you control a bot that interacts with a simulated limit order book. The goal is to maximize performance (typically PnL) while managing risk.

Each round introduces new products. The bot runs tick-by-tick and submits orders at every snapshot — no hardcoded trades, just logic reacting to live order book state.

This repo is my working area for the challenge.

---

## Historial de modelos implementados

### Fase 0: Tutorial

Los siguientes modelos están en `round_0/models/`. Los productos de esta fase son **EMERALDS** (fair value fijo en 10.000) y **TOMATOES** (drift lento, spread visible amplio de ~14 ticks). Position limit: 80 por producto.

- **`emerald_only.py`** — baseline solo EMERALDS. Toma agresiva cuando el precio cruza el fair value, quoting pasivo un tick adentro del libro externo. Incluye flattening de inventario opcional.

- **`model_v0.py`** — primer modelo combinado (EMERALDS + TOMATOES). EMA simple para el fair value de TOMATOES, señal de imbalance del libro, spread ajustado por volatilidad, inventory skew sobre el reservation price. Feature-flagged para ablation testing.

- **`model_v1.py`** — mejora el fair value de TOMATOES con un dual EMA (fast α=0.32 + slow α=0.10) blended con el mid actual. Agrega detección de régimen en 4 estados (calm / normal / directional / volatile) como capa experimental — desactivada por default porque en este dataset la política defensiva perjudica los fills más de lo que ayuda.
  - Backtest (días −2, −1): **~30.900 PnL total** — TOMATOES 15.777 / EMERALDS 15.128

- **`model_v2.py`** — tres cambios concretos sobre v1, derivados de un análisis de los trades externos a nivel de fill:
  1. `EMERALDS_TAKE_EDGE = 0` (antes 1) — el libro muestra asks y bids en exactamente 10.000 en ~10–15% de los ticks. Con edge=1 esos fills se perdían todos.
  2. `EMERALDS_MAX_PASSIVE_SIZE = 20` (antes 6) — pueden caer múltiples trades externos en una misma ventana de 100 ticks; con size 6 la queue se agotaba temprano.
  3. `TOMATOES_MAX_PASSIVE_SIZE = 12` (antes 5) — ~2 trades externos por snapshot con ~3.5 unidades promedio cada uno. Size 5 se maxeaba en cada snapshot.
  4. Position clearing — cuando el inventario se acerca al límite (≥70 de 80), postea una orden a fair value para liberar capacidad antes del próximo fill positivo.
  - Backtest (días −2, −1): **~33.900 PnL total** — TOMATOES 17.099 / EMERALDS 16.768
  - Sharpe +41% (3.93 → 5.55). Volumen total de fills casi duplicado (5.553 → 10.897 unidades).

---

## Estructura del repo

```
prosperity/
├── data/
│   └── round_0/          # CSVs de precios y trades del tutorial
│       └── plots/
└── round_0/
    ├── models/            # estrategias a submitear
    │   ├── datamodel.py   # clases provistas por IMC
    │   ├── emerald_only.py
    │   ├── model_v0.py
    │   ├── model_v1.py
    │   └── model_v2.py
    ├── tools/             # scripts de desarrollo
    │   ├── backtest.py
    │   └── generate_plots.py
    └── results/           # outputs del backtester (plots + CSVs)
        └── model_v*/
```

## Correr un backtest

```bash
source .venv/bin/activate

python round_0/tools/backtest.py --model model_v2 --days -2 -1
```

Los plots y CSVs se guardan en `round_0/results/<model_name>/`.
