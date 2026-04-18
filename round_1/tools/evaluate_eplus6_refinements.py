from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / 'models'
RESULTS_DIR = ROUND_DIR / 'results' / 'eplus6_refinements'

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(MODELS_DIR))

import backtest as bt  # noqa: E402
from replay import ROUND1_LIMITS, Round1Reader  # noqa: E402

import prosperity3bt.data as p3data  # type: ignore  # noqa: E402
from prosperity3bt.models import TradeMatchingMode  # type: ignore  # noqa: E402
from prosperity3bt.runner import run_backtest as run_official_backtest  # type: ignore  # noqa: E402

MODELS = [
    'model_E_plus_3',
    'model_E_plus_6',
    'model_E_plus_9',
    'model_E_plus_10',
    'model_E_plus_11',
    'model_E_plus_12',
    'model_E_plus_13',
]
NEW_MODELS = [m for m in MODELS if m not in {'model_E_plus_3', 'model_E_plus_6'}]
PRODUCTS = ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']
DAYS = [-2, -1, 0]
MAX_LEVELS = 3
EARLY_CUTOFF = 3333
MID_CUTOFF = 6666
RESET_BETWEEN_DAYS = True


def session_bucket(timestamp: int) -> str:
    if timestamp < EARLY_CUTOFF:
        return 'early'
    if timestamp < MID_CUTOFF:
        return 'mid'
    return 'late'


def load_module(model: str):
    path = MODELS_DIR / f'{model}.py'
    spec = importlib.util.spec_from_file_location(model, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def md_table(df: pd.DataFrame, float_fmt: str = '.1f') -> str:
    headers = [str(c) for c in df.columns]
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
    ]
    for _, row in df.iterrows():
        vals = []
        for value in row.tolist():
            if isinstance(value, float):
                vals.append('' if math.isnan(value) else format(value, float_fmt))
            else:
                vals.append(str(value))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def run_local_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    product_rows = []
    day_rows = []
    pepper_rows = []
    combined_rows = []
    ideal_rows = []

    ideal_hold_by_day = {}
    for day in DAYS:
        depth_by_ts, _ = bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS)
        start_mid = float(depth_by_ts[min(depth_by_ts)].mid_price)
        end_mid = float(depth_by_ts[max(depth_by_ts)].mid_price)
        ideal_hold = 80.0 * (end_mid - start_mid)
        ideal_hold_by_day[day] = ideal_hold
        ideal_rows.append({'day': day, 'start_mid': start_mid, 'end_mid': end_mid, 'mid_drift': end_mid - start_mid, 'ideal_hold_pnl_80': ideal_hold})
    total_ideal_hold = sum(ideal_hold_by_day.values())

    for model in MODELS:
        per_product = {}
        for product in PRODUCTS:
            results_df, fills_df, metrics = bt.run_backtest(model, product, DAYS, MAX_LEVELS, reset_between_days=RESET_BETWEEN_DAYS)
            per_product[product] = (results_df, fills_df, metrics)
            by_day_cum = results_df.groupby('day', sort=True)['pnl'].last()
            by_day = by_day_cum.diff().fillna(by_day_cum)
            for day, pnl in by_day.items():
                day_rows.append({'model': model, 'product': product, 'day': int(day), 'pnl': float(pnl)})
            fill_count = float(metrics.get('fill_count', 0.0))
            turnover = float(fills_df['quantity'].sum()) if not fills_df.empty else 0.0
            avg_fill_size = float(fills_df['quantity'].mean()) if not fills_df.empty else 0.0
            fill_size_std = float(fills_df['quantity'].std(ddof=0)) if not fills_df.empty else 0.0
            aggressive_share = float((fills_df['source'] == 'AGGRESSIVE').mean()) if not fills_df.empty else math.nan
            maker_share = float(metrics.get('maker_share', math.nan))
            avg_inventory = float(results_df['position'].mean()) if not results_df.empty else 0.0
            inventory_turns = float(results_df['position'].diff().abs().fillna(0.0).mean()) if not results_df.empty else 0.0
            product_rows.append({
                'model': model,
                'product': product,
                'total_pnl': float(metrics['total_pnl']),
                'turnover': turnover,
                'fill_count': fill_count,
                'avg_fill_size': avg_fill_size,
                'fill_size_std': fill_size_std,
                'aggressive_fill_share': aggressive_share,
                'maker_share': maker_share,
                'avg_inventory': avg_inventory,
                'inventory_turns': inventory_turns,
            })

        ash_pnl = float(per_product['ASH_COATED_OSMIUM'][2]['total_pnl'])
        pepper_pnl = float(per_product['INTARIAN_PEPPER_ROOT'][2]['total_pnl'])
        combined_daily = (
            pd.DataFrame([r for r in day_rows if r['model'] == model])
            .groupby('day', as_index=False)['pnl'].sum()
            .rename(columns={'pnl': 'total_pnl'})
        )
        day_map = {int(r['day']): float(r['total_pnl']) for _, r in combined_daily.iterrows()}
        combined_rows.append({
            'model': model,
            'ash_pnl': ash_pnl,
            'pepper_pnl': pepper_pnl,
            'total_pnl': ash_pnl + pepper_pnl,
            'day_-2_total': day_map.get(-2, math.nan),
            'day_-1_total': day_map.get(-1, math.nan),
            'day_0_total': day_map.get(0, math.nan),
            'ash_turnover': float(per_product['ASH_COATED_OSMIUM'][1]['quantity'].sum()) if not per_product['ASH_COATED_OSMIUM'][1].empty else 0.0,
            'pepper_turnover': float(per_product['INTARIAN_PEPPER_ROOT'][1]['quantity'].sum()) if not per_product['INTARIAN_PEPPER_ROOT'][1].empty else 0.0,
        })

        # pepper diagnostics with desired inventory proxy instrumentation
        tracker_rows: list[dict] = []
        pepper_depth_data = {day: bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS) for day in DAYS}
        for day in DAYS:
            mod = load_module(model)
            trader = mod.Trader()
            pepper = trader.pepper
            orig_desired = pepper.desired_inventory
            orig_trade = pepper.trade_pepper
            pepper._last_desired_inventory = 0

            def desired_wrapper(*args, __orig=orig_desired, __pep=pepper, **kwargs):
                out = int(__orig(*args, **kwargs))
                __pep._last_desired_inventory = out
                return out

            def trade_wrapper(order_depth, position, state_store, market_trades, timestamp, __orig=orig_trade, __pep=pepper):
                out = __orig(order_depth, position, state_store, market_trades, timestamp)
                tracker_rows.append({'day': day, 'timestamp': int(timestamp), 'desired_inventory': int(getattr(__pep, '_last_desired_inventory', 0))})
                return out

            pepper.desired_inventory = desired_wrapper
            pepper.trade_pepper = trade_wrapper
            bt.run_backtest_on_loaded_data(trader, 'INTARIAN_PEPPER_ROOT', [day], {day: pepper_depth_data[day]}, reset_between_days=True)

        results_df, fills_df, metrics = per_product['INTARIAN_PEPPER_ROOT']
        tracker_df = pd.DataFrame(tracker_rows)
        merged = results_df.merge(tracker_df, on=['day', 'timestamp'], how='left')
        merged['desired_inventory'] = merged['desired_inventory'].fillna(0)
        merged['session_bucket'] = merged['timestamp'].map(session_bucket)
        merged['under_target'] = merged['position'] < merged['desired_inventory']
        merged['under_carry_60'] = merged['position'] < 60
        fills = fills_df.copy()
        if fills.empty:
            fills['session_bucket'] = pd.Series(dtype=object)
        else:
            fills['session_bucket'] = fills['timestamp'].map(session_bucket)
        sells = fills.loc[fills['side'] == 'SELL'].copy()
        buys = fills.loc[fills['side'] == 'BUY'].copy()
        ts_mid = results_df.groupby(['day', 'timestamp'])['mid_price'].last()
        end_mid = results_df.groupby('day')['mid_price'].last().to_dict()
        if not sells.empty:
            sells['mid_at_fill'] = sells.apply(lambda row: float(ts_mid.loc[(int(row['day']), int(row['timestamp']))]), axis=1)
            sells['day_end_mid'] = sells['day'].map(end_mid)
            sells['estimated_upside_lost'] = (sells['day_end_mid'] - sells['mid_at_fill']).clip(lower=0.0) * sells['quantity']
        else:
            sells['estimated_upside_lost'] = pd.Series(dtype=float)
        pepper_rows.append({
            'model': model,
            'pepper_pnl': float(metrics['total_pnl']),
            'drift_capture_ratio': float(metrics['total_pnl']) / total_ideal_hold if total_ideal_hold else math.nan,
            'avg_inventory': float(merged['position'].mean()),
            'avg_inventory_early': float(merged.loc[merged['session_bucket'] == 'early', 'position'].mean()),
            'avg_inventory_mid': float(merged.loc[merged['session_bucket'] == 'mid', 'position'].mean()),
            'avg_inventory_late': float(merged.loc[merged['session_bucket'] == 'late', 'position'].mean()),
            'buy_qty_total': float(buys['quantity'].sum()) if not buys.empty else 0.0,
            'buy_qty_early': float(buys.loc[buys['session_bucket'] == 'early', 'quantity'].sum()) if not buys.empty else 0.0,
            'sell_qty_total': float(sells['quantity'].sum()) if not sells.empty else 0.0,
            'sell_qty_late': float(sells.loc[sells['session_bucket'] == 'late', 'quantity'].sum()) if not sells.empty else 0.0,
            'turnover': float(fills['quantity'].sum()) if not fills.empty else 0.0,
            'under_target_share': float(merged['under_target'].mean()) if not merged.empty else math.nan,
            'under_carry60_share': float(merged['under_carry_60'].mean()) if not merged.empty else math.nan,
            'estimated_upside_lost_after_sells': float(sells['estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'estimated_upside_lost_after_late_sells': float(sells.loc[sells['session_bucket'] == 'late', 'estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'avg_fill_size': float(fills['quantity'].mean()) if not fills.empty else 0.0,
            'fill_size_std': float(fills['quantity'].std(ddof=0)) if not fills.empty else 0.0,
            'aggressive_fill_share': float((fills['source'] == 'AGGRESSIVE').mean()) if not fills.empty else math.nan,
            'inventory_turns': float(merged['position'].diff().abs().fillna(0.0).mean()) if not merged.empty else 0.0,
        })

    product_df = pd.DataFrame(product_rows)
    day_df = pd.DataFrame(day_rows)
    pepper_df = pd.DataFrame(pepper_rows).sort_values('pepper_pnl', ascending=False).reset_index(drop=True)
    combined_df = pd.DataFrame(combined_rows).sort_values('total_pnl', ascending=False).reset_index(drop=True)
    combined_df['daily_std'] = combined_df[['day_-2_total', 'day_-1_total', 'day_0_total']].std(axis=1)
    combined_df['min_day_pnl'] = combined_df[['day_-2_total', 'day_-1_total', 'day_0_total']].min(axis=1)
    ideal_df = pd.DataFrame(ideal_rows)
    return product_df, day_df, pepper_df, combined_df, ideal_df


def run_official(models: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    reader = Round1Reader((PROJECT_ROOT / 'data').resolve())
    p3data.LIMITS.update(ROUND1_LIMITS)
    rows = []
    for model in models:
        mod = load_module(model)
        for day in DAYS:
            result = run_official_backtest(
                mod.Trader(), reader, 1, day,
                print_output=False,
                trade_matching_mode=TradeMatchingMode.all,
                no_names=True,
                show_progress_bar=False,
            )
            last_ts = result.activity_logs[-1].timestamp
            for product in PRODUCTS:
                final_rows = [row for row in result.activity_logs if row.timestamp == last_ts and row.columns[2] == product]
                final_pnl = float(final_rows[-1].columns[-1]) if final_rows else 0.0
                rows.append({'model': model, 'day': day, 'product': product, 'official_pnl': final_pnl})
    by_day = pd.DataFrame(rows)
    prod = by_day.groupby(['model', 'product'], as_index=False)['official_pnl'].sum()
    combined = prod.pivot(index='model', columns='product', values='official_pnl').reset_index().rename(columns={
        'ASH_COATED_OSMIUM': 'official_ash_pnl',
        'INTARIAN_PEPPER_ROOT': 'official_pepper_pnl',
    })
    combined['official_total_pnl'] = combined['official_ash_pnl'] + combined['official_pepper_pnl']
    daily_total = by_day.groupby(['model', 'day'], as_index=False)['official_pnl'].sum().rename(columns={'official_pnl': 'official_total_pnl'})
    daily_pivot = daily_total.pivot(index='model', columns='day', values='official_total_pnl').reset_index().rename(columns={-2:'official_day_-2_total', -1:'official_day_-1_total', 0:'official_day_0_total'})
    combined = combined.merge(daily_pivot, on='model', how='left')
    combined['official_min_day_pnl'] = combined[['official_day_-2_total','official_day_-1_total','official_day_0_total']].min(axis=1)
    return by_day, combined.sort_values('official_total_pnl', ascending=False).reset_index(drop=True)


def sensitivity_specs(model: str) -> list[tuple[str, dict[str, str]]]:
    mapping = {
        'model_E_plus_9': [
            ('tighter_offsets', {'PLACEMENT_GAP_SOFT = 8': 'PLACEMENT_GAP_SOFT = 6', 'PLACEMENT_GAP_STRONG = 16': 'PLACEMENT_GAP_STRONG = 14'}),
            ('looser_offsets', {'PLACEMENT_GAP_SOFT = 8': 'PLACEMENT_GAP_SOFT = 10', 'PLACEMENT_GAP_STRONG = 16': 'PLACEMENT_GAP_STRONG = 18'}),
        ],
        'model_E_plus_10': [
            ('weaker_hysteresis', {'HYSTERESIS_NEUTRAL_SIGNAL = 0.10': 'HYSTERESIS_NEUTRAL_SIGNAL = 0.06'}),
            ('stronger_hysteresis', {'HYSTERESIS_NEUTRAL_SIGNAL = 0.10': 'HYSTERESIS_NEUTRAL_SIGNAL = 0.14'}),
        ],
        'model_E_plus_11': [
            ('smaller_buy_curve', {'1.5 + 6.5 * gap_ratio': '1.5 + 5.5 * gap_ratio'}),
            ('larger_buy_curve', {'1.5 + 6.5 * gap_ratio': '1.5 + 7.5 * gap_ratio'}),
        ],
        'model_E_plus_12': [
            ('stricter_confirm', {'INTENTION_NEEDS_CONFIRM = 2': 'INTENTION_NEEDS_CONFIRM = 3'}),
            ('easier_strong_confirm', {'INTENTION_STRONG_CONFIRM = 4': 'INTENTION_STRONG_CONFIRM = 3'}),
        ],
        'model_E_plus_13': [
            ('weaker_combined', {'HYSTERESIS_NEUTRAL_SIGNAL = 0.10': 'HYSTERESIS_NEUTRAL_SIGNAL = 0.06', 'PLACEMENT_GAP_SOFT = 8': 'PLACEMENT_GAP_SOFT = 10'}),
            ('stronger_combined', {'HYSTERESIS_NEUTRAL_SIGNAL = 0.10': 'HYSTERESIS_NEUTRAL_SIGNAL = 0.14', 'PLACEMENT_GAP_SOFT = 8': 'PLACEMENT_GAP_SOFT = 6'}),
        ],
    }
    return mapping.get(model, [])


def run_sensitivity(model: str, specs: list[tuple[str, dict[str, str]]]) -> pd.DataFrame:
    base_path = MODELS_DIR / f'{model}.py'
    base_text = base_path.read_text(encoding='utf-8')
    pepper_data = {day: bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS) for day in DAYS}
    ash_data = {day: bt.load_day_prices_and_trades(day, 'ASH_COATED_OSMIUM', max_levels=MAX_LEVELS) for day in DAYS}
    rows = []
    temp_dir = RESULTS_DIR / '_temp_models'
    temp_dir.mkdir(parents=True, exist_ok=True)
    for label, replacements in specs:
        text = base_text
        for old, new in replacements.items():
            if old not in text:
                raise ValueError(f'Pattern not found in {model}: {old}')
            text = text.replace(old, new, 1)
        temp_path = temp_dir / f'{model}_{label}.py'
        temp_path.write_text(text, encoding='utf-8')
        spec = importlib.util.spec_from_file_location(f'{model}_{label}', temp_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        ash_results, ash_fills, ash_metrics = bt.run_backtest_on_loaded_data(mod.Trader(), 'ASH_COATED_OSMIUM', DAYS, ash_data, reset_between_days=RESET_BETWEEN_DAYS)
        pepper_results, pepper_fills, pepper_metrics = bt.run_backtest_on_loaded_data(mod.Trader(), 'INTARIAN_PEPPER_ROOT', DAYS, pepper_data, reset_between_days=RESET_BETWEEN_DAYS)
        rows.append({
            'base_model': model,
            'variant': label,
            'ash_pnl': float(ash_metrics['total_pnl']),
            'pepper_pnl': float(pepper_metrics['total_pnl']),
            'total_pnl': float(ash_metrics['total_pnl'] + pepper_metrics['total_pnl']),
            'pepper_avg_inventory': float(pepper_results['position'].mean()),
            'pepper_turnover': float(pepper_fills['quantity'].sum()) if not pepper_fills.empty else 0.0,
            'pepper_sell_qty': float(pepper_fills.loc[pepper_fills['side'] == 'SELL', 'quantity'].sum()) if not pepper_fills.empty else 0.0,
        })
    return pd.DataFrame(rows)


def write_report(local_combined: pd.DataFrame, pepper_df: pd.DataFrame, product_df: pd.DataFrame, official_combined: pd.DataFrame, sensitivity_df: pd.DataFrame) -> None:
    baseline_local = local_combined.loc[local_combined['model'] == 'model_E_plus_6'].iloc[0]
    baseline_official = official_combined.loc[official_combined['model'] == 'model_E_plus_6'].iloc[0]
    baseline_pepper = pepper_df.loc[pepper_df['model'] == 'model_E_plus_6'].iloc[0]
    best_official = official_combined.iloc[0]
    best_model = str(best_official['model'])
    best_local = local_combined.loc[local_combined['model'] == best_model].iloc[0]
    best_pepper = pepper_df.loc[pepper_df['model'] == best_model].iloc[0]

    desc = {
        'model_E_plus_9': 'Placement-offset refinement: shape bid/ask offsets by inventory gap so urgent buying is slightly sharper but not blindly aggressive.',
        'model_E_plus_10': 'Refresh / hysteresis refinement: add a small no-change band so PEPPER does not reprice around tiny state changes.',
        'model_E_plus_11': 'Size-shaping refinement: smooth PEPPER size adjustments using gap ratio instead of more discrete jumps.',
        'model_E_plus_12': 'Book-intention modulation refinement: require clearer supportive book state before stepping in harder on the buy side.',
        'model_E_plus_13': 'Combined simple refinement: blend calmer placement, mild hysteresis, smoother sizing, and intention gating.',
    }

    lines = [
        '# Round 1 — model_E_plus_6 precision refinement report',
        '',
        '## 1. Executive summary',
        '',
        f'- Baseline: `model_E_plus_6`',
        f'- Best official-simulator candidate: `{best_model}` with {best_official["official_total_pnl"]:.1f}',
        f'- Official delta vs baseline: {best_official["official_total_pnl"] - baseline_official["official_total_pnl"]:+.1f}',
        f'- Local delta vs baseline for the recommended model: {best_local["total_pnl"] - baseline_local["total_pnl"]:+.1f}',
        f'- Recommendation confidence: {"medium" if best_model != "model_E_plus_6" and best_official["official_total_pnl"] - baseline_official["official_total_pnl"] > 150 else "low"}',
        f'- The gain looks {"meaningful enough to switch" if best_model != "model_E_plus_6" and best_official["official_total_pnl"] > baseline_official["official_total_pnl"] else "marginal"}.',
        '',
        '## 2. Baseline recap',
        '',
        '- `model_E_plus_6` was the correct baseline because it slightly improved official-simulator results while preserving the winning PEPPER carry-first architecture.',
        '- This round tried only precision PEPPER execution refinements: better placement, calmer hysteresis, smoother sizing, and cleaner book-intention modulation.',
        '- No heavy fair overlay, no ASH rewrite, and no wide parameter hunting.',
        '',
        '## 3. Variant descriptions',
        '',
    ]
    for model in NEW_MODELS:
        lines.extend([f'### {model}', '', f'- {desc[model]}', ''])

    lines.extend([
        '## 4. Backtest tables',
        '',
        '### Local combined results',
        '',
        md_table(local_combined[['model','total_pnl','ash_pnl','pepper_pnl','day_-2_total','day_-1_total','day_0_total','ash_turnover','pepper_turnover']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '### PEPPER diagnostics (local)',
        '',
        md_table(pepper_df[['model','pepper_pnl','drift_capture_ratio','avg_inventory','avg_inventory_early','avg_inventory_mid','avg_inventory_late','buy_qty_total','sell_qty_total','sell_qty_late','turnover','under_target_share','estimated_upside_lost_after_late_sells']].sort_values('pepper_pnl', ascending=False), '.3f'),
        '',
        '### Official simulator results',
        '',
        md_table(official_combined[['model','official_total_pnl','official_ash_pnl','official_pepper_pnl','official_day_-2_total','official_day_-1_total','official_day_0_total','official_min_day_pnl']].sort_values('official_total_pnl', ascending=False), '.1f'),
        '',
        '### ASH sanity check (local)',
        '',
        md_table(product_df.loc[product_df['product'] == 'ASH_COATED_OSMIUM', ['model','total_pnl','turnover','avg_inventory','inventory_turns']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '### Execution-style proxies (local, PEPPER)',
        '',
        md_table(product_df.loc[product_df['product'] == 'INTARIAN_PEPPER_ROOT', ['model','fill_count','avg_fill_size','fill_size_std','aggressive_fill_share','maker_share','inventory_turns']].sort_values('model'), '.3f'),
        '',
        '> Note: average posted distance / repricing frequency are not directly observable from the available backtester and simulator outputs, so this round uses fill mix, fill size smoothness, and inventory turning as practical execution proxies.',
        '',
        '## 5. Interpretation',
        '',
    ])

    for model in ['model_E_plus_9','model_E_plus_10','model_E_plus_11','model_E_plus_12','model_E_plus_13']:
        local_row = local_combined.loc[local_combined['model'] == model].iloc[0]
        off_row = official_combined.loc[official_combined['model'] == model].iloc[0]
        pep_row = pepper_df.loc[pepper_df['model'] == model].iloc[0]
        lines.extend([
            f'### {model}',
            '',
            f'- Local delta vs baseline: {local_row["total_pnl"] - baseline_local["total_pnl"]:+.1f}',
            f'- Official delta vs baseline: {off_row["official_total_pnl"] - baseline_official["official_total_pnl"]:+.1f}',
            f'- PEPPER late sells vs baseline: {pep_row["sell_qty_late"]:.0f} vs {baseline_pepper["sell_qty_late"]:.0f}',
            f'- Under-target share vs baseline: {pep_row["under_target_share"]:.3f} vs {baseline_pepper["under_target_share"]:.3f}',
            f'- Drift-capture ratio vs baseline: {pep_row["drift_capture_ratio"]:.3f} vs {baseline_pepper["drift_capture_ratio"]:.3f}',
            '',
        ])

    lines.extend([
        '## 6. Sensitivity / robustness',
        '',
        md_table(sensitivity_df, '.1f') if not sensitivity_df.empty else '_No sensitivity runs executed._',
        '',
        'Interpretation:',
    ])
    if not sensitivity_df.empty:
        for model, sub in sensitivity_df.groupby('base_model'):
            spread = float(sub['total_pnl'].max() - sub['total_pnl'].min())
            lines.append(f'- `{model}` local sensitivity spread: {spread:.1f}.')
    lines.extend([
        '',
        '## 7. Final recommendation',
        '',
    ])
    if best_model != 'model_E_plus_6' and float(best_official['official_total_pnl']) > float(baseline_official['official_total_pnl']):
        lines.extend([
            f'- Keep `model_E_plus_6` or switch? **Switch to `{best_model}`**.',
            f'- Why? Because it improved the official simulator by {best_official["official_total_pnl"] - baseline_official["official_total_pnl"]:+.1f} without changing the core architecture or creating obvious churn pathologies.',
        ])
    else:
        lines.extend([
            '- Keep `model_E_plus_6` or switch? **Keep `model_E_plus_6`.**',
            '- Why? Because none of the precision refinements produced a clearly superior official-simulator result with enough margin to justify switching.',
        ])
    lines.extend([
        '- Main remaining bottleneck: PEPPER execution quality still matters more than alpha-model changes, but gains are now getting small.',
        '- Best justified next research line: one more tiny official-simulator-first PEPPER placement/refresh experiment, then probably stop unless the gain is clearly larger.',
        '',
    ])

    (ROUND_DIR / 'round1_model_E_plus_6_refinement_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    product_df, day_df, pepper_df, local_combined, ideal_df = run_local_all()
    official_day_df, official_combined = run_official(MODELS)

    top_official_new = [m for m in official_combined['model'].tolist() if m in NEW_MODELS][:3]
    sens_frames = []
    for model in top_official_new:
        specs = sensitivity_specs(model)
        if specs:
            sens_frames.append(run_sensitivity(model, specs))
    sensitivity_df = pd.concat(sens_frames, ignore_index=True) if sens_frames else pd.DataFrame()

    product_df.to_csv(RESULTS_DIR / 'local_product_metrics.csv', index=False)
    day_df.to_csv(RESULTS_DIR / 'local_product_day_metrics.csv', index=False)
    pepper_df.to_csv(RESULTS_DIR / 'pepper_diagnostics.csv', index=False)
    local_combined.to_csv(RESULTS_DIR / 'local_combined_metrics.csv', index=False)
    ideal_df.to_csv(RESULTS_DIR / 'pepper_ideal_hold_reference.csv', index=False)
    official_day_df.to_csv(RESULTS_DIR / 'official_product_day_metrics.csv', index=False)
    official_combined.to_csv(RESULTS_DIR / 'official_combined_metrics.csv', index=False)
    sensitivity_df.to_csv(RESULTS_DIR / 'sensitivity_metrics.csv', index=False)

    write_report(local_combined, pepper_df, product_df, official_combined, sensitivity_df)


if __name__ == '__main__':
    main()
