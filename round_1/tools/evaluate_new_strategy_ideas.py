from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / 'models'
RESULTS_DIR = ROUND_DIR / 'results' / 'new_strategy_ideas'

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(MODELS_DIR))

import backtest as bt  # noqa: E402
from replay import ROUND1_LIMITS, Round1Reader  # noqa: E402

import prosperity3bt.data as p3data  # type: ignore  # noqa: E402
from prosperity3bt.models import TradeMatchingMode  # type: ignore  # noqa: E402
from prosperity3bt.runner import run_backtest as run_official_backtest  # type: ignore  # noqa: E402

MODELS = ['model_E_plus_11', 'model_F1', 'model_F2', 'model_F3', 'model_F4', 'model_F5']
NEW_MODELS = [m for m in MODELS if m != 'model_E_plus_11']
PRODUCTS = ['ASH_COATED_OSMIUM', 'INTARIAN_PEPPER_ROOT']
DAYS = [-2, -1, 0]
MAX_LEVELS = 3
RESET_BETWEEN_DAYS = True
EARLY_CUTOFF = 3333
MID_CUTOFF = 6666


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
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for _, row in df.iterrows():
        vals = []
        for v in row.tolist():
            if isinstance(v, float):
                vals.append('' if math.isnan(v) else format(v, float_fmt))
            else:
                vals.append(str(v))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def ideal_hold_reference() -> tuple[pd.DataFrame, float]:
    rows = []
    total = 0.0
    for day in DAYS:
        depth_by_ts, _ = bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS)
        start_mid = float(depth_by_ts[min(depth_by_ts)].mid_price)
        end_mid = float(depth_by_ts[max(depth_by_ts)].mid_price)
        pnl = 80.0 * (end_mid - start_mid)
        total += pnl
        rows.append({'day': day, 'start_mid': start_mid, 'end_mid': end_mid, 'mid_drift': end_mid - start_mid, 'ideal_hold_pnl_80': pnl})
    return pd.DataFrame(rows), total


def instrument_pepper(model: str) -> pd.DataFrame:
    mod = load_module(model)
    tracker_rows = []
    pepper_day_data = {day: bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS) for day in DAYS}
    for day in DAYS:
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
            tracker_rows.append({
                'model': model,
                'day': day,
                'timestamp': int(timestamp),
                'desired_inventory': int(getattr(__pep, '_last_desired_inventory', 0)),
                'core_target': int(getattr(__pep, '_last_core_target', 0)),
                'tactical_target': int(getattr(__pep, '_last_tactical_target', 0)),
                'schedule_target': int(getattr(__pep, '_last_schedule_target', 0)),
                'hold_target': int(getattr(__pep, '_hold_target_snapshot', 0)),
                'state_target': int(getattr(__pep, '_last_state_target', 0)),
                'policy_state': str(getattr(__pep, '_policy_state', 'NA')),
            })
            return out

        pepper.desired_inventory = desired_wrapper
        pepper.trade_pepper = trade_wrapper
        bt.run_backtest_on_loaded_data(trader, 'INTARIAN_PEPPER_ROOT', [day], {day: pepper_day_data[day]}, reset_between_days=True)
    return pd.DataFrame(tracker_rows)


def run_local() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ideal_df, total_ideal = ideal_hold_reference()
    product_rows = []
    combined_rows = []
    pepper_rows = []
    structure_rows = []

    for model in MODELS:
        product_data = {}
        by_day_rows = []
        for product in PRODUCTS:
            results_df, fills_df, metrics = bt.run_backtest(model, product, DAYS, MAX_LEVELS, reset_between_days=RESET_BETWEEN_DAYS)
            product_data[product] = (results_df, fills_df, metrics)
            by_day_cum = results_df.groupby('day', sort=True)['pnl'].last()
            by_day = by_day_cum.diff().fillna(by_day_cum)
            for day, pnl in by_day.items():
                by_day_rows.append({'day': int(day), 'product': product, 'pnl': float(pnl)})
            product_rows.append({
                'model': model,
                'product': product,
                'total_pnl': float(metrics['total_pnl']),
                'turnover': float(fills_df['quantity'].sum()) if not fills_df.empty else 0.0,
                'avg_inventory': float(results_df['position'].mean()) if not results_df.empty else 0.0,
                'maker_share': float(metrics.get('maker_share', math.nan)),
                'aggressive_fill_share': float((fills_df['source'] == 'AGGRESSIVE').mean()) if not fills_df.empty else math.nan,
            })

        day_df = pd.DataFrame(by_day_rows).groupby('day', as_index=False)['pnl'].sum()
        day_map = {int(r['day']): float(r['pnl']) for _, r in day_df.iterrows()}
        combined_rows.append({
            'model': model,
            'ash_pnl': float(product_data['ASH_COATED_OSMIUM'][2]['total_pnl']),
            'pepper_pnl': float(product_data['INTARIAN_PEPPER_ROOT'][2]['total_pnl']),
            'total_pnl': float(product_data['ASH_COATED_OSMIUM'][2]['total_pnl'] + product_data['INTARIAN_PEPPER_ROOT'][2]['total_pnl']),
            'day_-2_total': day_map.get(-2, math.nan),
            'day_-1_total': day_map.get(-1, math.nan),
            'day_0_total': day_map.get(0, math.nan),
            'ash_turnover': float(product_data['ASH_COATED_OSMIUM'][1]['quantity'].sum()) if not product_data['ASH_COATED_OSMIUM'][1].empty else 0.0,
            'pepper_turnover': float(product_data['INTARIAN_PEPPER_ROOT'][1]['quantity'].sum()) if not product_data['INTARIAN_PEPPER_ROOT'][1].empty else 0.0,
        })

        results_df, fills_df, metrics = product_data['INTARIAN_PEPPER_ROOT']
        tracker = instrument_pepper(model)
        results_with_model = results_df.copy()
        results_with_model['model'] = model
        merged = results_with_model.merge(tracker, on=['model', 'day', 'timestamp'], how='left')
        merged['session_bucket'] = merged['timestamp'].map(session_bucket)
        merged['under_target'] = merged['position'] < merged['desired_inventory']
        fills = fills_df.copy()
        fills['session_bucket'] = fills['timestamp'].map(session_bucket) if not fills.empty else pd.Series(dtype=object)
        buys = fills.loc[fills['side'] == 'BUY'].copy()
        sells = fills.loc[fills['side'] == 'SELL'].copy()
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
            'drift_capture_ratio': float(metrics['total_pnl']) / total_ideal if total_ideal else math.nan,
            'avg_inventory': float(merged['position'].mean()),
            'avg_inventory_early': float(merged.loc[merged['session_bucket'] == 'early', 'position'].mean()),
            'avg_inventory_mid': float(merged.loc[merged['session_bucket'] == 'mid', 'position'].mean()),
            'avg_inventory_late': float(merged.loc[merged['session_bucket'] == 'late', 'position'].mean()),
            'frac_above_20': float((merged['position'] >= 20).mean()),
            'frac_above_40': float((merged['position'] >= 40).mean()),
            'frac_above_60': float((merged['position'] >= 60).mean()),
            'frac_above_80': float((merged['position'] >= 80).mean()),
            'buy_qty_total': float(buys['quantity'].sum()) if not buys.empty else 0.0,
            'sell_qty_total': float(sells['quantity'].sum()) if not sells.empty else 0.0,
            'sell_qty_late': float(sells.loc[sells['session_bucket'] == 'late', 'quantity'].sum()) if not sells.empty else 0.0,
            'turnover': float(fills['quantity'].sum()) if not fills.empty else 0.0,
            'under_target_share': float(merged['under_target'].mean()) if not merged.empty else math.nan,
            'estimated_upside_lost_after_sells': float(sells['estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'estimated_upside_lost_after_late_sells': float(sells.loc[sells['session_bucket'] == 'late', 'estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'passive_fill_share': float((fills['source'] != 'AGGRESSIVE').mean()) if not fills.empty else math.nan,
        })

        # structure metrics
        row = {'model': model}
        if model in {'model_F1', 'model_F5'}:
            row.update({
                'family': 'core_tactical',
                'avg_core_target': float(merged['core_target'].mean()),
                'avg_tactical_target': float(merged['tactical_target'].mean()),
                'tactical_usage_share': float((merged['tactical_target'] > 0).mean()),
            })
        elif model == 'model_F2':
            row.update({
                'family': 'schedule',
                'avg_schedule_target_early': float(merged.loc[merged['session_bucket']=='early','schedule_target'].mean()),
                'avg_schedule_target_mid': float(merged.loc[merged['session_bucket']=='mid','schedule_target'].mean()),
                'avg_schedule_target_late': float(merged.loc[merged['session_bucket']=='late','schedule_target'].mean()),
                'avg_schedule_gap_abs': float((merged['position'] - merged['schedule_target']).abs().mean()),
            })
        elif model == 'model_F3':
            row.update({
                'family': 'aggressive_hold',
                'avg_hold_target': float(merged['hold_target'].mean()),
                'hold_adherence_gap_abs': float((merged['position'] - merged['hold_target']).abs().mean()),
            })
        elif model == 'model_F4':
            policy = merged['policy_state'].fillna('NA')
            transitions = int((policy != policy.shift(1)).sum() - 1)
            row.update({
                'family': 'state_machine',
                'accumulate_share': float((policy == 'ACCUMULATE').mean()),
                'carry_share': float((policy == 'CARRY').mean()),
                'defend_share': float((policy == 'DEFEND').mean()),
                'reduce_share': float((policy == 'REDUCE').mean()),
                'transition_count': transitions,
            })
        else:
            row.update({'family': 'baseline'})
        structure_rows.append(row)

    combined = pd.DataFrame(combined_rows).sort_values('total_pnl', ascending=False).reset_index(drop=True)
    combined['daily_std'] = combined[['day_-2_total','day_-1_total','day_0_total']].std(axis=1)
    product_df = pd.DataFrame(product_rows)
    pepper_df = pd.DataFrame(pepper_rows).sort_values('pepper_pnl', ascending=False).reset_index(drop=True)
    structure_df = pd.DataFrame(structure_rows)
    return product_df, combined, pepper_df, structure_df, ideal_df


def run_official(models: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    reader = Round1Reader((PROJECT_ROOT / 'data').resolve())
    p3data.LIMITS.update(ROUND1_LIMITS)
    rows = []
    for model in models:
        mod = load_module(model)
        for day in DAYS:
            result = run_official_backtest(mod.Trader(), reader, 1, day, print_output=False, trade_matching_mode=TradeMatchingMode.all, no_names=True, show_progress_bar=False)
            last_ts = result.activity_logs[-1].timestamp
            for product in PRODUCTS:
                final_rows = [row for row in result.activity_logs if row.timestamp == last_ts and row.columns[2] == product]
                pnl = float(final_rows[-1].columns[-1]) if final_rows else 0.0
                rows.append({'model': model, 'product': product, 'day': day, 'official_pnl': pnl})
    by_day = pd.DataFrame(rows)
    prod = by_day.groupby(['model', 'product'], as_index=False)['official_pnl'].sum()
    combined = prod.pivot(index='model', columns='product', values='official_pnl').reset_index().rename(columns={'ASH_COATED_OSMIUM':'official_ash_pnl','INTARIAN_PEPPER_ROOT':'official_pepper_pnl'})
    combined['official_total_pnl'] = combined['official_ash_pnl'] + combined['official_pepper_pnl']
    daily = by_day.groupby(['model','day'], as_index=False)['official_pnl'].sum().pivot(index='model', columns='day', values='official_pnl').reset_index().rename(columns={-2:'official_day_-2_total', -1:'official_day_-1_total', 0:'official_day_0_total'})
    combined = combined.merge(daily, on='model', how='left')
    combined['official_min_day_pnl'] = combined[['official_day_-2_total','official_day_-1_total','official_day_0_total']].min(axis=1)
    return by_day, combined.sort_values('official_total_pnl', ascending=False).reset_index(drop=True)


def sensitivity_specs(model: str):
    return {
        'model_F2': [
            ('lower_schedule', {'EARLY_TARGET = 78': 'EARLY_TARGET = 74', 'MID_TARGET = 74': 'MID_TARGET = 70', 'LATE_TARGET = 68': 'LATE_TARGET = 62'}),
            ('higher_schedule', {'EARLY_TARGET = 78': 'EARLY_TARGET = 80', 'MID_TARGET = 74': 'MID_TARGET = 76', 'LATE_TARGET = 68': 'LATE_TARGET = 70'}),
        ],
        'model_F3': [
            ('less_hold', {'HOLD_TARGET_MID = 78': 'HOLD_TARGET_MID = 74', 'HOLD_TARGET_LATE = 72': 'HOLD_TARGET_LATE = 66'}),
            ('more_hold', {'HOLD_TARGET_MID = 78': 'HOLD_TARGET_MID = 80', 'HOLD_TARGET_LATE = 72': 'HOLD_TARGET_LATE = 74'}),
        ],
        'model_F4': [
            ('stricter_reduce', {'position > 64 and l2_imbalance < -0.10': 'position > 68 and l2_imbalance < -0.14'}),
            ('easier_accumulate', {'position < 56 and (l2_imbalance > -0.04 or continuation_adj > -0.08)': 'position < 60 and (l2_imbalance > -0.08 or continuation_adj > -0.12)'}),
        ],
    }.get(model, [])


def run_sensitivity(model: str, specs) -> pd.DataFrame:
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
        pep_results, pep_fills, pep_metrics = bt.run_backtest_on_loaded_data(mod.Trader(), 'INTARIAN_PEPPER_ROOT', DAYS, pepper_data, reset_between_days=RESET_BETWEEN_DAYS)
        rows.append({
            'base_model': model,
            'variant': label,
            'ash_pnl': float(ash_metrics['total_pnl']),
            'pepper_pnl': float(pep_metrics['total_pnl']),
            'total_pnl': float(ash_metrics['total_pnl'] + pep_metrics['total_pnl']),
            'pepper_turnover': float(pep_fills['quantity'].sum()) if not pep_fills.empty else 0.0,
            'pepper_avg_inventory': float(pep_results['position'].mean()) if not pep_results.empty else 0.0,
        })
    return pd.DataFrame(rows)


def write_report(local_combined: pd.DataFrame, product_df: pd.DataFrame, pepper_df: pd.DataFrame, structure_df: pd.DataFrame, official_combined: pd.DataFrame, sensitivity_df: pd.DataFrame) -> None:
    baseline_off = official_combined.loc[official_combined['model']=='model_E_plus_11'].iloc[0]
    baseline_local = local_combined.loc[local_combined['model']=='model_E_plus_11'].iloc[0]
    best_off = official_combined.iloc[0]
    best_model = str(best_off['model'])
    desc = {
        'model_F1': ('Core + tactical sleeve', 'Separates strategic drift exposure from tactical PEPPER activity.', 'Risk: tactical sleeve can add churn without enough incremental edge.'),
        'model_F2': ('Time-scheduled target inventory', 'Encodes PEPPER’s repeatable session drift directly into a simple schedule.', 'Risk: schedule can be too rigid under adverse book conditions.'),
        'model_F3': ('Simple aggressive hold benchmark', 'Tests whether a simpler and much more aggressive hold-style PEPPER policy captures most of the edge.', 'Risk: may be too blunt and leak on weaker local conditions.'),
        'model_F4': ('State machine / regime controller', 'Uses explicit policy states instead of continuous modulation everywhere.', 'Risk: state transitions can become a brittle rule tree.'),
        'model_F5': ('Hybrid of new idea + robust execution', 'Combines sleeves with the stronger size-shaping / execution lessons.', 'Risk: can become a monster if the hybrid does not buy enough extra edge.'),
    }
    lines = [
        '# Round 1 — new strategy ideas report',
        '',
        '## 1. Executive summary',
        '',
        f'- Best new strategy idea by official simulator: `{best_model}`',
        f'- Official simulator result vs baseline: {best_off["official_total_pnl"]:.1f} vs {baseline_off["official_total_pnl"]:.1f} ({best_off["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f})',
        f'- Does any new family materially beat `model_E_plus_11`? {"Yes" if best_off["official_total_pnl"] - baseline_off["official_total_pnl"] > 1000 else "Probably not materially"}',
        f'- Confidence level: {"medium" if best_off["official_total_pnl"] - baseline_off["official_total_pnl"] > 1000 else "low-to-medium"}',
        '',
        '## 2. Baseline recap',
        '',
        '- `model_E_plus_11` was frozen because the PEPPER carry + execution-refinement family had reached diminishing returns.',
        '- This round looked for new policy structures rather than another micro-tweak around the same execution layer.',
        '',
        '## 3. Model-by-model description',
        '',
    ]
    for m in NEW_MODELS:
        idea, why, risk = desc[m]
        lines.extend([f'### {m}', '', f'- Idea: {idea}', f'- Why test it: {why}', f'- Main risk: {risk}', ''])
    lines.extend([
        '## 4. Backtest and official simulator tables',
        '',
        '### Local combined results',
        '',
        md_table(local_combined[['model','total_pnl','ash_pnl','pepper_pnl','day_-2_total','day_-1_total','day_0_total','ash_turnover','pepper_turnover']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '### Official simulator results',
        '',
        md_table(official_combined[['model','official_total_pnl','official_ash_pnl','official_pepper_pnl','official_day_-2_total','official_day_-1_total','official_day_0_total','official_min_day_pnl']].sort_values('official_total_pnl', ascending=False), '.1f'),
        '',
        '### PEPPER diagnostics',
        '',
        md_table(pepper_df[['model','pepper_pnl','drift_capture_ratio','avg_inventory','avg_inventory_early','avg_inventory_mid','avg_inventory_late','frac_above_20','frac_above_40','frac_above_60','frac_above_80','buy_qty_total','sell_qty_total','sell_qty_late','turnover','under_target_share','estimated_upside_lost_after_late_sells','passive_fill_share']].sort_values('pepper_pnl', ascending=False), '.3f'),
        '',
        '### Structure-specific diagnostics',
        '',
        md_table(structure_df.sort_values('model'), '.3f'),
        '',
        '### ASH sanity check',
        '',
        md_table(product_df.loc[product_df['product']=='ASH_COATED_OSMIUM', ['model','total_pnl','turnover','avg_inventory','maker_share']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '## 5. Interpretation of results',
        '',
    ])
    for m in NEW_MODELS:
        lrow = local_combined.loc[local_combined['model']==m].iloc[0]
        orow = official_combined.loc[official_combined['model']==m].iloc[0]
        prow = pepper_df.loc[pepper_df['model']==m].iloc[0]
        lines.extend([
            f'### {m}',
            '',
            f'- Local delta vs baseline: {lrow["total_pnl"] - baseline_local["total_pnl"]:+.1f}',
            f'- Official delta vs baseline: {orow["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f}',
            f'- PEPPER mechanism snapshot: drift capture {prow["drift_capture_ratio"]:.3f}, avg inventory {prow["avg_inventory"]:.1f}, late sells {prow["sell_qty_late"]:.0f}',
            '',
        ])
    lines.extend([
        '## 6. Robustness section',
        '',
        md_table(sensitivity_df, '.1f') if not sensitivity_df.empty else '_No sensitivity runs._',
        '',
        'Interpretation:',
    ])
    if not sensitivity_df.empty:
        for model, sub in sensitivity_df.groupby('base_model'):
            spread = float(sub['total_pnl'].max() - sub['total_pnl'].min())
            lines.append(f'- `{model}` local robustness spread: {spread:.1f}.')
    lines.extend(['', '## 7. Final recommendation', ''])
    if best_model != 'model_E_plus_11' and best_off['official_total_pnl'] - baseline_off['official_total_pnl'] > 1000:
        lines.extend([
            f'- Keep `model_E_plus_11` or switch? **Switch to `{best_model}`**.',
            f'- Why? Because it beat the frozen baseline by {best_off["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f} in the official simulator with a clear structural mechanism.',
        ])
    else:
        promising = best_model if best_model != 'model_E_plus_11' else official_combined.loc[official_combined['model']!='model_E_plus_11'].iloc[0]['model']
        lines.extend([
            '- Keep `model_E_plus_11` or switch? **Keep `model_E_plus_11` for now.**',
            f'- Most promising new research branch: `{promising}`.',
            '- Why? Because the new families are informative and some look promising, but none clearly earned baseline promotion under the simulator-first standard once complexity and robustness are considered.',
            '- Next research round should focus on the most promising structural family rather than more micro-tweaks.',
        ])
    (ROUND_DIR / 'round1_new_strategy_ideas_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    product_df, local_combined, pepper_df, structure_df, ideal_df = run_local()
    official_by_day, official_combined = run_official(MODELS)
    # choose top 3 new official ideas for sensitivity
    top_new = [m for m in official_combined['model'].tolist() if m in NEW_MODELS][:3]
    sens_frames = []
    for model in top_new:
        specs = sensitivity_specs(model)
        if specs:
            sens_frames.append(run_sensitivity(model, specs))
    sensitivity_df = pd.concat(sens_frames, ignore_index=True) if sens_frames else pd.DataFrame()
    product_df.to_csv(RESULTS_DIR / 'local_product_metrics.csv', index=False)
    local_combined.to_csv(RESULTS_DIR / 'local_combined_metrics.csv', index=False)
    pepper_df.to_csv(RESULTS_DIR / 'pepper_diagnostics.csv', index=False)
    structure_df.to_csv(RESULTS_DIR / 'structure_diagnostics.csv', index=False)
    ideal_df.to_csv(RESULTS_DIR / 'pepper_ideal_hold_reference.csv', index=False)
    official_by_day.to_csv(RESULTS_DIR / 'official_product_day_metrics.csv', index=False)
    official_combined.to_csv(RESULTS_DIR / 'official_combined_metrics.csv', index=False)
    sensitivity_df.to_csv(RESULTS_DIR / 'sensitivity_metrics.csv', index=False)
    write_report(local_combined, product_df, pepper_df, structure_df, official_combined, sensitivity_df)


if __name__ == '__main__':
    main()
