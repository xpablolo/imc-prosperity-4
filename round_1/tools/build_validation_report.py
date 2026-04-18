from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path('/Users/pablo/Desktop/prosperity')
ROUND_1 = ROOT / 'round_1'
RESULTS = ROUND_1 / 'results'
MODELS = ROUND_1 / 'models'

BG = '#0f172a'
PANEL = '#111827'
GRID = '#334155'
TEXT = '#e5e7eb'
MUTED = '#94a3b8'
ACCENT = '#22c55e'
ACCENT_2 = '#38bdf8'
ACCENT_3 = '#f59e0b'
ACCENT_4 = '#f472b6'
NEG = '#fb7185'


def style() -> None:
    plt.style.use('dark_background')
    plt.rcParams.update(
        {
            'figure.facecolor': BG,
            'axes.facecolor': PANEL,
            'axes.edgecolor': GRID,
            'axes.labelcolor': TEXT,
            'axes.titlecolor': TEXT,
            'xtick.color': MUTED,
            'ytick.color': MUTED,
            'grid.color': GRID,
            'grid.alpha': 0.25,
            'font.size': 11,
            'axes.titlesize': 13,
            'axes.titleweight': 'bold',
        }
    )


def load_model_params(model_name: str) -> dict[str, Any]:
    sys.path.insert(0, str(MODELS))
    path = MODELS / f'{model_name}.py'
    spec = importlib.util.spec_from_file_location(model_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'No pude cargar {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    keys = [
        'POSITION_LIMIT',
        'BASE_FAIR',
        'ANCHOR_ALPHA',
        'ANCHOR_CLIP_TICKS',
        'DEFAULT_QUOTE_OFFSET',
        'INVENTORY_SKEW_TICKS',
        'MAX_PASSIVE_SIZE',
        'SIZE_PRESSURE',
        'FAIR_REPAIR_MIN_POSITION',
        'FAIR_UNWIND_SAME_PRICE_VOLUME',
        'EMA_FAST_ALPHA',
        'EMA_SLOW_ALPHA',
        'FAST_WEIGHT',
        'SLOW_WEIGHT',
        'MID_WEIGHT',
        'TREND_FORECAST_HORIZON',
        'TREND_SLOPE_CLIP',
        'L1_IMBALANCE_BETA',
        'L2_IMBALANCE_BETA',
        'MICROPRICE_BETA',
        'CONTINUATION_BONUS',
        'PULLBACK_BONUS',
        'TARGET_INVENTORY_MAX',
        'INVENTORY_SKEW',
        'BASE_HALF_SPREAD',
        'VOL_MULTIPLIER',
        'TAKE_EDGE',
        'AGGRESSIVE_CAP',
        'SOFT_POSITION_LIMIT',
        'HARD_POSITION_LIMIT',
        'DIRECTIONAL_SIGNAL',
    ]
    holder = getattr(module, 'Trader', module)
    return {k: getattr(holder, k) for k in keys if hasattr(holder, k)}


def narrative_for(product: str) -> dict[str, Any]:
    if product == 'INTARIAN_PEPPER_ROOT':
        return {
            'title': 'Trend + pullback market making validation overview',
            'thesis': 'INTARIAN_PEPPER_ROOT muestra un drift intradía casi lineal y muy estable, pero con micro-pullbacks rápidos alrededor de esa tendencia. La lógica correcta no es mean reversion pura: es seguir la tendencia, comprar pullbacks y usar el libro para sesgar inventario y quotes.',
            'design': [
                '- Template base: bloque conceptual de TOMATOES de `round_0/models/model_v3.py` / `model_v4.py`, no el de EMERALDS.',
                '- Adaptación: anchor dinámico con fast/slow EMA + forecast de slope, microstructure overlay con L1/L2 imbalance y microprice, y pullback adjustment alrededor de la trend line.',
                '- Interpretación financiera: Pepper recompensa llevar inventario a favor del drift y castiga vender demasiado temprano; por eso el quoting es asimétrico y los sells se frenan cuando la señal sigue larga.',
            ],
            'interpretation': [
                '- Replay y backtest quedaron razonablemente alineados en magnitud y perfil diario, señal de que la tesis de trend + pullback sí captura el régimen dominante.',
                '- Monte Carlo positivo en casi todo el rango sugiere que la edge depende del patrón estructural del asset: drift limpio + alpha de imbalance + reversión muy rápida de residual al trend.',
                '- Un maker share más bajo que Ash es sano: Pepper necesita más iniciativa agresiva para enganchar los pullbacks y no quedarse mirando cómo sube el precio.',
                '- El riesgo real no es “volatilidad pura”, sino descargar inventario demasiado pronto y perder carry del drift.',
            ],
            'takeaway': 'Takeaway: setup consistente con asset tendencial; el edge viene de drift capture + pullback entries + sesgo dinámico de inventario, no de market making neutro.',
            'param_1_label': 'EMA fast / slow',
            'param_2_label': 'Inventory skew / target max',
        }
    return {
        'title': 'Market making validation overview',
        'thesis': 'ASH_COATED_OSMIUM se comporta como un asset de fair value casi fijo alrededor de 10000; por eso la lógica correcta no es perseguir momentum sino hacer market making con anchor lento, skew por inventario y captura disciplinada de spread.',
        'design': [
            '- Template base: bloque de EMERALDS de `round_0/models/model_v4.py`.',
            '- Adaptación: anchor lento alrededor de 10000, clipped para no sobre-reaccionar, reservation price sesgado por inventario, quoting one-tick-inside y reparación táctica cuando el precio vuelve al fair.',
            '- Interpretación financiera: el asset parece mean-reverting/stationary, así que la edge viene más de comprar barato/vender caro alrededor del ancla que de estimar drift fuerte.',
        ],
        'interpretation': [
            '- El replay quedó MUY alineado con el backtest; eso es buena señal de robustez y de que la lógica no está sobreajustada a un simulador alternativo.',
            '- Monte Carlo mantiene PnL positivo incluso en el percentil 5, lo que sugiere que la edge principal depende del régimen estructural del asset y no de una sola secuencia afortunada.',
            '- El maker share alto tiene sentido financiero: la estrategia gana mayormente capturando spread, pero conserva flexibilidad para hacer takes de reparación cuando el inventario pide ayuda.',
            '- El drawdown está contenido para el nivel de PnL obtenido; el costo es usar casi todo el inventario permitido en algunos tramos, algo razonable para un market maker en activo estacionario.',
        ],
        'takeaway': 'Takeaway: setup consistente con asset estacionario; el edge viene de spread capture + inventory control, no de adivinar tendencia.',
        'param_1_label': 'Anchor alpha / clip',
        'param_2_label': 'Inventory skew / max passive',
    }


def load_inputs(model_name: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, Path]:
    model_dir = RESULTS / model_name
    bt = pd.read_csv(model_dir / f'backtest_{model_name}_results_-2_-1_0.csv')
    replay = pd.read_csv(model_dir / 'replay_summary.csv')

    mc_root = RESULTS / 'montecarlo' / model_name
    candidates = sorted([p for p in mc_root.iterdir() if p.is_dir()])
    if not candidates:
        raise RuntimeError(f'No encontré runs de Monte Carlo en {mc_root}')
    mc_dir = candidates[-1]
    with open(mc_dir / 'dashboard.json') as fh:
        mc_dashboard = json.load(fh)
    mc_sessions = pd.read_csv(mc_dir / 'session_summary.csv')
    return bt, replay, mc_dashboard, mc_sessions, mc_dir


def summarize(bt: pd.DataFrame, replay: pd.DataFrame, mc_dashboard: dict[str, Any], mc_sessions: pd.DataFrame) -> pd.DataFrame:
    pnl = bt['pnl'].astype(float)
    increments = pnl.diff().fillna(0.0)
    running_max = pnl.cummax()
    drawdown = pnl - running_max

    bt_row = {
        'section': 'deterministic_backtest',
        'metric': 'total_pnl',
        'value': float(pnl.iloc[-1]),
    }
    rows = [bt_row]
    rows.extend(
        [
            {'section': 'deterministic_backtest', 'metric': 'max_drawdown', 'value': float(drawdown.min())},
            {'section': 'deterministic_backtest', 'metric': 'mean_pnl_increment', 'value': float(increments.mean())},
            {
                'section': 'deterministic_backtest',
                'metric': 'pnl_increment_vol',
                'value': float(increments.std(ddof=0)),
            },
            {
                'section': 'deterministic_backtest',
                'metric': 'sharpe_like',
                'value': float(increments.mean() / increments.std(ddof=0) * math.sqrt(len(increments)))
                if increments.std(ddof=0) > 0
                else np.nan,
            },
            {
                'section': 'deterministic_backtest',
                'metric': 'max_abs_position',
                'value': float(bt['position'].abs().max()),
            },
            {
                'section': 'replay',
                'metric': 'total_pnl',
                'value': float(replay.loc[replay['day'].astype(str) == 'ALL', 'final_pnl'].iloc[0]),
            },
        ]
    )

    for _, row in replay[replay['day'].astype(str) != 'ALL'].iterrows():
        rows.append(
            {
                'section': 'replay_daily',
                'metric': f"day_{row['day']}_pnl",
                'value': float(row['final_pnl']),
            }
        )

    overall = mc_dashboard['overall']
    for name, key in [
        ('mean_total_pnl', ('totalPnl', 'mean')),
        ('p05_total_pnl', ('totalPnl', 'p05')),
        ('p50_total_pnl', ('totalPnl', 'p50')),
        ('p95_total_pnl', ('totalPnl', 'p95')),
        ('win_rate', ('totalPnl', 'positiveRate')),
        ('mean_max_drawdown', ('maxDrawdown', 'mean')),
        ('mean_sharpe_like', ('sharpeLike', 'mean')),
        ('mean_maker_share', ('makerShare', 'mean')),
    ]:
        rows.append({'section': 'monte_carlo', 'metric': name, 'value': float(overall[key[0]][key[1]])})

    return pd.DataFrame(rows)


def write_markdown(
    out_path: Path,
    model_name: str,
    product: str,
    params: dict[str, Any],
    summary: pd.DataFrame,
    mc_dashboard: dict[str, Any],
    mc_dir: Path,
) -> None:
    narrative = narrative_for(product)
    metric = lambda s, m: summary.loc[(summary['section'] == s) & (summary['metric'] == m), 'value'].iloc[0]
    bt_pnl = metric('deterministic_backtest', 'total_pnl')
    bt_dd = metric('deterministic_backtest', 'max_drawdown')
    replay_total = metric('replay', 'total_pnl')
    mc_mean = metric('monte_carlo', 'mean_total_pnl')
    mc_p05 = metric('monte_carlo', 'p05_total_pnl')
    mc_p95 = metric('monte_carlo', 'p95_total_pnl')
    mc_win = metric('monte_carlo', 'win_rate')
    mc_sharpe = metric('monte_carlo', 'mean_sharpe_like')
    mc_maker = metric('monte_carlo', 'mean_maker_share')

    lines = [
        f'# {model_name} — Validation Report',
        '',
        '## Thesis',
        narrative['thesis'],
        '',
        '## Strategy Design',
        *narrative['design'],
        '',
        '## Tuned Parameters',
    ]
    for k, v in params.items():
        lines.append(f'- `{k}` = `{v}`')

    lines.extend(
        [
            '',
            '## Validation Snapshot',
            f'- Deterministic backtest total PnL: **{bt_pnl:,.1f}**',
            f'- Deterministic max drawdown: **{bt_dd:,.1f}**',
            f'- Replay total PnL: **{replay_total:,.1f}**',
            f'- Monte Carlo mean PnL: **{mc_mean:,.1f}**',
            f'- Monte Carlo p05–p95: **{mc_p05:,.1f} → {mc_p95:,.1f}**',
            f'- Monte Carlo win rate: **{mc_win * 100:.1f}%**',
            f'- Monte Carlo mean sharpe-like: **{mc_sharpe:.2f}**',
            f'- Monte Carlo mean maker share: **{mc_maker * 100:.1f}%**',
            '',
            '## Interpretation',
            *narrative['interpretation'],
            '',
            '## Monte Carlo Method',
            f"- Método: {mc_dashboard['meta']['method']}",
            f"- Bloque: {mc_dashboard['meta']['blockLength']} ticks",
            f"- Sesiones: {mc_dashboard['meta']['sessions']}",
            f"- Carpeta fuente: `{mc_dir}`",
            f"- Reset between days: `{mc_dashboard['meta'].get('resetBetweenDays', False)}`",
        ]
    )
    out_path.write_text('\n'.join(lines))


def plot_overview(
    bt: pd.DataFrame,
    replay: pd.DataFrame,
    mc_sessions: pd.DataFrame,
    params: dict[str, Any],
    product: str,
    out_path: Path,
) -> None:
    narrative = narrative_for(product)
    style()
    pnl = bt['pnl'].astype(float)
    drawdown = pnl - pnl.cummax()
    by_day = bt.groupby('day', sort=True).agg(cumulative_pnl=('pnl', 'last')).reset_index()
    by_day['final_pnl'] = by_day['cumulative_pnl'].diff().fillna(by_day['cumulative_pnl'])
    replay_days = replay[replay['day'].astype(str) != 'ALL'].copy()
    replay_days['day'] = replay_days['day'].astype(int)
    replay_days = replay_days.sort_values('day')

    fig = plt.figure(figsize=(18, 12), facecolor=BG)
    gs = fig.add_gridspec(2, 2, hspace=0.25, wspace=0.18)

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(bt['global_ts'], pnl, color=ACCENT, linewidth=2.2, label='Backtest PnL')
    ax1.fill_between(bt['global_ts'], drawdown, 0, color=NEG, alpha=0.18, label='Drawdown vs peak')
    ax1.set_title('Backtest equity curve + drawdown')
    ax1.set_xlabel('Global timestamp')
    ax1.set_ylabel('PnL')
    ax1.grid(True)
    ax1.legend(frameon=False, loc='upper left')

    ax2 = fig.add_subplot(gs[0, 1])
    x = np.arange(len(replay_days))
    ax2.bar(x - 0.18, by_day['final_pnl'].values, width=0.36, color=ACCENT_2, label='Backtest final PnL')
    ax2.bar(x + 0.18, replay_days['final_pnl'].values, width=0.36, color=ACCENT_3, label='Replay final PnL')
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"day {d}" for d in replay_days['day']])
    ax2.set_title('Daily validation: backtest vs replay (per-day)')
    ax2.set_ylabel('PnL')
    ax2.grid(True, axis='y')
    ax2.legend(frameon=False, loc='upper left')
    for xi, val in zip(x - 0.18, by_day['final_pnl'].values):
        ax2.text(xi, val + 180, f'{val:,.0f}', ha='center', va='bottom', color=TEXT, fontsize=9)
    for xi, val in zip(x + 0.18, replay_days['final_pnl'].values):
        ax2.text(xi, val + 180, f'{val:,.0f}', ha='center', va='bottom', color=TEXT, fontsize=9)

    ax3 = fig.add_subplot(gs[1, 0])
    ax3.hist(mc_sessions['total_pnl'], bins=22, color=ACCENT_4, alpha=0.75, edgecolor=BG)
    for q, label, color in [
        (mc_sessions['total_pnl'].quantile(0.05), 'p05', ACCENT_2),
        (mc_sessions['total_pnl'].quantile(0.50), 'p50', ACCENT),
        (mc_sessions['total_pnl'].quantile(0.95), 'p95', ACCENT_3),
    ]:
        ax3.axvline(q, color=color, linestyle='--', linewidth=2)
        ax3.text(q, ax3.get_ylim()[1] * 0.92, label, color=color, rotation=90, va='top', ha='right')
    ax3.set_title('Monte Carlo distribution of total PnL')
    ax3.set_xlabel('Total PnL')
    ax3.set_ylabel('Sessions')
    ax3.grid(True, axis='y')

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')
    replay_total = float(replay.loc[replay['day'].astype(str) == 'ALL', 'final_pnl'].iloc[0])
    table_lines = [
        ('Backtest total PnL', f"{pnl.iloc[-1]:,.1f}"),
        ('Backtest max drawdown', f"{drawdown.min():,.1f}"),
        ('Replay total PnL', f"{replay_total:,.1f}"),
        ('MC mean / p05 / p95', f"{mc_sessions['total_pnl'].mean():,.1f} / {mc_sessions['total_pnl'].quantile(0.05):,.1f} / {mc_sessions['total_pnl'].quantile(0.95):,.1f}"),
        ('MC win rate', f"{(mc_sessions['total_pnl'] > 0).mean() * 100:.1f}%"),
        ('MC mean drawdown', f"{mc_sessions['max_drawdown'].mean():,.1f}"),
        ('MC mean maker share', f"{mc_sessions['maker_share'].mean() * 100:.1f}%"),
        ('Position limit', str(params.get('POSITION_LIMIT', 'n/a'))),
        (
            narrative['param_1_label'],
            f"{params.get('ANCHOR_ALPHA', params.get('EMA_FAST_ALPHA', 'n/a'))} / {params.get('ANCHOR_CLIP_TICKS', params.get('EMA_SLOW_ALPHA', 'n/a'))}",
        ),
        (
            narrative['param_2_label'],
            f"{params.get('INVENTORY_SKEW_TICKS', params.get('INVENTORY_SKEW', 'n/a'))} / {params.get('MAX_PASSIVE_SIZE', params.get('TARGET_INVENTORY_MAX', 'n/a'))}",
        ),
    ]
    y = 0.95
    ax4.text(0.0, y, 'Validation scorecard', fontsize=16, fontweight='bold', color=TEXT)
    y -= 0.08
    for label, value in table_lines:
        ax4.text(0.0, y, label, color=MUTED, fontsize=11)
        ax4.text(0.98, y, value, color=TEXT, fontsize=11, ha='right', fontweight='bold')
        y -= 0.075
    ax4.text(
        0.0,
        0.08,
        narrative['takeaway'],
        color=TEXT,
        fontsize=11,
        wrap=True,
    )

    fig.suptitle(f'{product} — {narrative["title"]}', fontsize=18, fontweight='bold', color=TEXT)
    fig.savefig(out_path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='ash_mm_v0')
    parser.add_argument('--product', default='ASH_COATED_OSMIUM')
    args = parser.parse_args()

    bt, replay, mc_dashboard, mc_sessions, mc_dir = load_inputs(args.model)
    params = load_model_params(args.model)
    summary = summarize(bt, replay, mc_dashboard, mc_sessions)

    out_dir = RESULTS / args.model
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / f'{args.model}_validation_metrics.csv', index=False)
    plot_overview(bt, replay, mc_sessions, params, args.product, out_dir / f'{args.model}_validation_overview.png')
    write_markdown(
        out_dir / f'{args.model}_validation_report.md',
        args.model,
        args.product,
        params,
        summary,
        mc_dashboard,
        mc_dir,
    )
    print(f'Validation report created in {out_dir}')


if __name__ == '__main__':
    main()
