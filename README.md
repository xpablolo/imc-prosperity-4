# IMC Prosperity 4 (Trading Challenge)

This repository is where we're building and iterating on strategies for the IMC Prosperity trading challenge.

## What the challenge is

The IMC Prosperity challenge is an algorithmic trading competition where you control a bot that interacts with a simulated limit order book. The goal is to maximize performance (typically PnL) while managing risk.

Each round introduces new products. The bot runs tick-by-tick and submits orders at every snapshot — no hardcoded trades, just logic reacting to live order book state.

This repo is our working area for the challenge.

---

## Estructura del proyecto

El proyecto tiene dos repos separados dentro del mismo directorio:

```
prosperity/
│
├── round_0/                        # nuestro repo — estrategias y herramientas
│   ├── models/                     # estrategias a submitear
│   │   ├── datamodel.py            # clases provistas por IMC
│   │   ├── emerald_only.py
│   │   ├── model_v0.py
│   │   ├── model_v1.py
│   │   └── model_v2.py
│   ├── tools/
│   │   ├── backtest.py             # backtester propio con plots y CSVs
│   │   ├── replay.py               # replay histórico vía prosperity3bt
│   │   ├── fill_stats.py           # análisis maker/taker de fills
│   │   ├── montecarlo.py           # Monte Carlo vía Rust simulator
│   │   ├── mc_plots.py             # plots matplotlib desde resultados MC
│   │   └── generate_plots.py       # visualización de precios del dataset
│   ├── results/
│   │   ├── model_v*/               # plots y CSVs del backtester propio
│   │   ├── logs/                   # logs de replay histórico
│   │   └── montecarlo/<model>/<ts>/# resultados Monte Carlo por modelo y run
│   └── research/                   # notas de investigación de rondas pasadas
│
├── montercarlo_backtester/         # repo externo — motor de backtest
│   ├── backtester/                 # paquetes Python (prosperity3bt, prosperity4mcbt)
│   ├── calibration/                # análisis de comportamiento de bots del mercado
│   ├── rust_simulator/             # simulador Monte Carlo en Rust (requiere Cargo)
│   ├── scripts/                    # scripts de análisis y comparación
│   └── visualizer/                 # dashboard React para Monte Carlo (requiere Node)
│
└── data/
    └── round_0/                    # CSVs de precios y trades del tutorial
```

---

## Historial de modelos — Fase 0: Tutorial

Productos: **EMERALDS** (fair value fijo en 10.000) y **TOMATOES** (drift lento, spread visible ~14 ticks). Position limit: 80 por producto.

- `emerald_only.py` — baseline solo EMERALDS. Toma agresiva cuando el precio cruza el fair value, quoting pasivo un tick adentro del libro externo. Incluye flattening de inventario opcional.

- `model_v0.py` — primera idea de modelo combinado (EMERALDS + TOMATOES). EMA simple para TOMATOES, señal de imbalance del libro, spread ajustado por volatilidad, inventory skew sobre el reservation price. Feature-flagged para ablation testing.

- `model_v1.py` — mejora el fair value de TOMATOES con dual EMA (fast α=0.32 + slow α=0.10) blended con el mid. Incluye detección de régimen en 4 estados como capa experimental — desactivada por default (la política defensiva perjudica fills en este dataset).
  - Backtest días −2/−1: **~30.900 PnL total** — TOMATOES 15.777 / EMERALDS 15.128

- `model_v2.py` — tres mejoras sobre v1 derivadas de análisis de fills:
  1. `EMERALDS_TAKE_EDGE = 0` — captures fills cuando 10.000 aparece en el libro (~10–15% de los ticks)
  2. `EMERALDS_MAX_PASSIVE_SIZE = 20` — evita agotar la queue cuando caen múltiples trades en el mismo snapshot
  3. `TOMATOES_MAX_PASSIVE_SIZE = 12` — el ~7 vol externo por snapshot superaba el size=5 anterior
  4. Position clearing a fair value cuando inventario ≥70 de 80
  - Backtest días −2/−1: **~33.900 PnL total** — TOMATOES 17.099 / EMERALDS 16.768
  - Sharpe +41% (3.93 → 5.55). Fill volume casi duplicado (5.553 → 10.897 unidades).

---

## Backtesting

Hay dos backtesting engines distintos y tres herramientas sobre ellos:

### Nuestro backtester — `round_0/tools/backtest.py`

Engine propio optimizado para generar plots y métricas comparativas. Guarda PnL curves, drawdown, distribución de fills y tablas de métricas en `round_0/results/`.

```bash
source .venv/bin/activate
python round_0/tools/backtest.py --model model_v2 --days -2 -1
```

### prosperity3bt — `round_0/tools/replay.py` y `fill_stats.py`

Usa el engine de [chrispyroberts/imc-prosperity-4](https://github.com/chrispyroberts/imc-prosperity-4), más fiel al matching oficial de IMC. Replay exacto de los días del tutorial.

```bash
source .venv/bin/activate

# replay histórico (ambos días por default, log en round_0/results/logs/)
python round_0/tools/replay.py model_v2
python round_0/tools/replay.py model_v2 0--2        # solo día -2
python round_0/tools/replay.py model_v2 --no-out    # sin guardar log

# desglose maker/taker de fills
python round_0/tools/fill_stats.py model_v2
python round_0/tools/fill_stats.py model_v2 0--2
```

### Monte Carlo — `round_0/tools/montecarlo.py`

Corre N sesiones sintéticas usando el simulador Rust calibrado desde los CSVs del tutorial. En vez de un PnL único, da una distribución completa. Útil para medir robustez.

Genera automáticamente plots matplotlib en `round_0/results/montecarlo/<model>/<timestamp>/plots/`.

```bash
source .venv/bin/activate

python round_0/tools/montecarlo.py model_v2             # 100 sesiones
python round_0/tools/montecarlo.py model_v2 --quick     # 100 sesiones, 10 trazas
python round_0/tools/montecarlo.py model_v2 --heavy     # 1000 sesiones, 100 trazas
python round_0/tools/montecarlo.py model_v2 --sessions 500
```

Resultados de `model_v2` (100 sesiones):
- Mean PnL: **13.608**  •  Std: **784**  •  Win rate: **100%**
- P05–P95: 12.462 → 14.902

Plots generados por run:
- `pnl_distribution.png` — histograma + fit normal + percentiles
- `pnl_by_product.png` — distribución separada EMERALDS / TOMATOES
- `pnl_paths.png` — bandas de PnL acumulado (±1σ, ±3σ, mediana, trazas individuales)
- `metrics_table.png` — tabla de métricas completa
