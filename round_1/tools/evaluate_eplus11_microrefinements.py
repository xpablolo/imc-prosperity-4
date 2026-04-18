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
RESULTS_DIR = ROUND_DIR / 'results' / 'eplus11_microrefinements'

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(MODELS_DIR))

import backtest as bt  # noqa: E402
from replay import ROUND1_LIMITS, Round1Reader  # noqa: E402

import prosperity3bt.data as p3data  # type: ignore  # noqa: E402
from prosperity3bt.models import TradeMatchingMode  # type: ignore  # noqa: E402
from prosperity3bt.runner import run_backtest as run_official_backtest  # type: ignore  # noqa: E402

MODELS = ['model_E_plus_11', 'model_E_plus_14', 'model_E_plus_15', 'model_E_plus_16']
NEW_MODELS = ['model_E_plus_14', 'model_E_plus_15', 'model_E_plus_16']
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


def run_local() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ideal_df, total_ideal = ideal_hold_reference()
    product_rows = []
    combined_rows = []
    pepper_rows = []
    day_rows = []

    pepper_day_data = {day: bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS) for day in DAYS}

    for model in MODELS:
        local_product = {}
        for product in PRODUCTS:
            results_df, fills_df, metrics = bt.run_backtest(model, product, DAYS, MAX_LEVELS, reset_between_days=RESET_BETWEEN_DAYS)
            local_product[product] = (results_df, fills_df, metrics)
            by_day_cum = results_df.groupby('day', sort=True)['pnl'].last()
            by_day = by_day_cum.diff().fillna(by_day_cum)
            for day, pnl in by_day.items():
                day_rows.append({'model': model, 'product': product, 'day': int(day), 'pnl': float(pnl)})
            product_rows.append({
                'model': model,
                'product': product,
                'total_pnl': float(metrics['total_pnl']),
                'turnover': float(fills_df['quantity'].sum()) if not fills_df.empty else 0.0,
                'avg_inventory': float(results_df['position'].mean()) if not results_df.empty else 0.0,
                'fill_count': float(metrics.get('fill_count', 0.0)),
                'aggressive_fill_share': float((fills_df['source'] == 'AGGRESSIVE').mean()) if not fills_df.empty else math.nan,
                'maker_share': float(metrics.get('maker_share', math.nan)),
            })

        # combined
        ddf = pd.DataFrame([r for r in day_rows if r['model'] == model]).groupby('day', as_index=False)['pnl'].sum()
        day_map = {int(r['day']): float(r['pnl']) for _, r in ddf.iterrows()}
        combined_rows.append({
            'model': model,
            'ash_pnl': float(local_product['ASH_COATED_OSMIUM'][2]['total_pnl']),
            'pepper_pnl': float(local_product['INTARIAN_PEPPER_ROOT'][2]['total_pnl']),
            'total_pnl': float(local_product['ASH_COATED_OSMIUM'][2]['total_pnl'] + local_product['INTARIAN_PEPPER_ROOT'][2]['total_pnl']),
            'day_-2_total': day_map.get(-2, math.nan),
            'day_-1_total': day_map.get(-1, math.nan),
            'day_0_total': day_map.get(0, math.nan),
        })

        # pepper diagnostics + desired inventory proxy
        tracker_rows = []
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
            bt.run_backtest_on_loaded_data(trader, 'INTARIAN_PEPPER_ROOT', [day], {day: pepper_day_data[day]}, reset_between_days=True)

        results_df, fills_df, metrics = local_product['INTARIAN_PEPPER_ROOT']
        tracker_df = pd.DataFrame(tracker_rows)
        merged = results_df.merge(tracker_df, on=['day', 'timestamp'], how='left')
        merged['desired_inventory'] = merged['desired_inventory'].fillna(0)
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
            'buy_qty_total': float(buys['quantity'].sum()) if not buys.empty else 0.0,
            'buy_qty_early': float(buys.loc[buys['session_bucket'] == 'early', 'quantity'].sum()) if not buys.empty else 0.0,
            'sell_qty_total': float(sells['quantity'].sum()) if not sells.empty else 0.0,
            'sell_qty_late': float(sells.loc[sells['session_bucket'] == 'late', 'quantity'].sum()) if not sells.empty else 0.0,
            'turnover': float(fills['quantity'].sum()) if not fills.empty else 0.0,
            'under_target_share': float(merged['under_target'].mean()) if not merged.empty else math.nan,
            'estimated_upside_lost_after_sells': float(sells['estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'estimated_upside_lost_after_late_sells': float(sells.loc[sells['session_bucket'] == 'late', 'estimated_upside_lost'].sum()) if not sells.empty else 0.0,
            'avg_buy_fill_size': float(buys['quantity'].mean()) if not buys.empty else 0.0,
            'avg_sell_fill_size': float(sells['quantity'].mean()) if not sells.empty else 0.0,
            'aggressive_fill_share': float((fills['source'] == 'AGGRESSIVE').mean()) if not fills.empty else math.nan,
        })

    return pd.DataFrame(product_rows), pd.DataFrame(combined_rows), pd.DataFrame(pepper_rows), ideal_df


def run_official(models: Iterable[str]) -> pd.DataFrame:
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
    dtot = by_day.groupby(['model','day'], as_index=False)['official_pnl'].sum().pivot(index='model', columns='day', values='official_pnl').reset_index().rename(columns={-2:'official_day_-2_total', -1:'official_day_-1_total', 0:'official_day_0_total'})
    combined = combined.merge(dtot, on='model', how='left')
    combined['official_min_day_pnl'] = combined[['official_day_-2_total','official_day_-1_total','official_day_0_total']].min(axis=1)
    return combined.sort_values('official_total_pnl', ascending=False).reset_index(drop=True)


def sensitivity_specs(model: str):
    return {
        'model_E_plus_14': [
            ('weaker_offset_size', {'MICRO_PLACEMENT_GAP = 12': 'MICRO_PLACEMENT_GAP = 14', '(1.3 + 6.2 * gap_ratio)': '(1.1 + 5.8 * gap_ratio)'}),
            ('stronger_offset_size', {'MICRO_PLACEMENT_GAP = 12': 'MICRO_PLACEMENT_GAP = 10', '(1.3 + 6.2 * gap_ratio)': '(1.5 + 6.6 * gap_ratio)'}),
        ],
        'model_E_plus_16': [
            ('weaker_book_support', {'BOOK_SUPPORT_SOFT = 2': 'BOOK_SUPPORT_SOFT = 3'}),
            ('stronger_book_support', {'BOOK_SUPPORT_STRONG = 4': 'BOOK_SUPPORT_STRONG = 3'}),
        ],
    }.get(model, [])


def run_sensitivity(model: str, specs) -> pd.DataFrame:
    base_path = MODELS_DIR / f'{model}.py'
    base_text = base_path.read_text(encoding='utf-8')
    pepper_data = {day: bt.load_day_prices_and_trades(day, 'INTARIAN_PEPPER_ROOT', max_levels=MAX_LEVELS) for day in DAYS}
    ash_data = {day: bt.load_day_prices_and_trades(day, 'ASH_COATED_OSMIUM', max_levels=MAX_LEVELS) for day in DAYS}
    temp_dir = RESULTS_DIR / '_temp_models'
    temp_dir.mkdir(parents=True, exist_ok=True)
    rows = []
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
        rows.append({'base_model': model, 'variant': label, 'ash_pnl': float(ash_metrics['total_pnl']), 'pepper_pnl': float(pep_metrics['total_pnl']), 'total_pnl': float(ash_metrics['total_pnl'] + pep_metrics['total_pnl']), 'pepper_turnover': float(pep_fills['quantity'].sum()) if not pep_fills.empty else 0.0, 'pepper_avg_inventory': float(pep_results['position'].mean()) if not pep_results.empty else 0.0})
    return pd.DataFrame(rows)


def write_report(local_combined: pd.DataFrame, product_df: pd.DataFrame, pepper_df: pd.DataFrame, official_df: pd.DataFrame, sensitivity_df: pd.DataFrame) -> None:
    baseline_off = official_df.loc[official_df['model']=='model_E_plus_11'].iloc[0]
    baseline_local = local_combined.loc[local_combined['model']=='model_E_plus_11'].iloc[0]
    best_off = official_df.iloc[0]
    best_model = str(best_off['model'])
    desc = {
        'model_E_plus_14': 'Placement + size micro-refinement: slightly calmer offset shaping and slightly smoother buy/sell size scaling.',
        'model_E_plus_15': 'Refresh / hysteresis micro-refinement: add a tiny no-change zone before repricing under weak state changes.',
        'model_E_plus_16': 'Book-conditioned buy execution refinement: require supportive book state before stepping in harder on buys.',
    }
    lines = [
        '# Round 1 — model_E_plus_11 micro-refinement report',
        '',
        '## 1. Executive summary',
        '',
        f'- Baseline: `model_E_plus_11`',
        f'- Best official candidate: `{best_model}` with {best_off["official_total_pnl"]:.1f}',
        f'- Official delta vs `model_E_plus_11`: {best_off["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f}',
        f'- Gain classification: {"noise-like" if abs(best_off["official_total_pnl"] - baseline_off["official_total_pnl"]) < 25 else "marginal" if abs(best_off["official_total_pnl"] - baseline_off["official_total_pnl"]) < 100 else "meaningful"}',
        f'- Recommendation confidence: {"low" if abs(best_off["official_total_pnl"] - baseline_off["official_total_pnl"]) < 100 else "medium"}',
        '',
        '## 2. Baseline recap',
        '',
        '- `model_E_plus_11` was the practical baseline because it improved official results across all three days while staying simpler than `model_E_plus_13`.',
        '- What remained to test was only very fine PEPPER execution quality: placement, size smoothing, refresh behavior, and book-conditioned buy aggression.',
        '',
        '## 3. Variant descriptions',
        '',
    ]
    for m in NEW_MODELS:
        lines.extend([f'### {m}', '', f'- {desc[m]}', ''])
    lines.extend([
        '## 4. Backtest and simulator tables',
        '',
        '### Local results',
        '',
        md_table(local_combined[['model','total_pnl','ash_pnl','pepper_pnl','day_-2_total','day_-1_total','day_0_total']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '### Official results',
        '',
        md_table(official_df[['model','official_total_pnl','official_ash_pnl','official_pepper_pnl','official_day_-2_total','official_day_-1_total','official_day_0_total']].sort_values('official_total_pnl', ascending=False), '.1f'),
        '',
        '### PEPPER diagnostics',
        '',
        md_table(pepper_df[['model','pepper_pnl','drift_capture_ratio','avg_inventory','avg_inventory_early','avg_inventory_mid','avg_inventory_late','buy_qty_total','sell_qty_total','sell_qty_late','turnover','under_target_share','estimated_upside_lost_after_late_sells','avg_buy_fill_size','avg_sell_fill_size','aggressive_fill_share']].sort_values('pepper_pnl', ascending=False), '.3f'),
        '',
        '### ASH sanity check',
        '',
        md_table(product_df.loc[product_df['product']=='ASH_COATED_OSMIUM', ['model','total_pnl','turnover','avg_inventory']].sort_values('total_pnl', ascending=False), '.1f'),
        '',
        '> Note: repricing frequency and exact placement distance are not directly observable from the available simulator/backtester outputs, so this round uses fill mix, fill sizes, turnover, and under-target share as execution proxies.',
        '',
        '## 5. Interpretation',
        '',
    ])
    baseline_pepper = pepper_df.loc[pepper_df['model']=='model_E_plus_11'].iloc[0]
    for m in NEW_MODELS:
        lrow = local_combined.loc[local_combined['model']==m].iloc[0]
        orow = official_df.loc[official_df['model']==m].iloc[0]
        prow = pepper_df.loc[pepper_df['model']==m].iloc[0]
        lines.extend([
            f'### {m}',
            '',
            f'- Local delta vs baseline: {lrow["total_pnl"] - baseline_local["total_pnl"]:+.1f}',
            f'- Official delta vs baseline: {orow["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f}',
            f'- PEPPER late sell qty vs baseline: {prow["sell_qty_late"]:.0f} vs {baseline_pepper["sell_qty_late"]:.0f}',
            f'- Under-target share vs baseline: {prow["under_target_share"]:.3f} vs {baseline_pepper["under_target_share"]:.3f}',
            f'- Added complexity justified? {"No" if abs(orow["official_total_pnl"] - baseline_off["official_total_pnl"]) < 25 else "Possibly"}',
            '',
        ])
    lines.extend(['## 6. Sensitivity / robustness', '', md_table(sensitivity_df, '.1f') if not sensitivity_df.empty else '_No sensitivity run._', '', 'Interpretation:'])
    if not sensitivity_df.empty:
        for base_model, sub in sensitivity_df.groupby('base_model'):
            spread = float(sub['total_pnl'].max() - sub['total_pnl'].min())
            lines.append(f'- `{base_model}` local sensitivity spread: {spread:.1f}.')
    lines.extend(['', '## 7. Final recommendation', ''])
    if best_model != 'model_E_plus_11' and float(best_off['official_total_pnl']) - float(baseline_off['official_total_pnl']) >= 25:
        lines.extend([
            f'- Keep `model_E_plus_11` or switch? **Switch to `{best_model}`**.',
            f'- Why? Because it improved the official simulator by {best_off["official_total_pnl"] - baseline_off["official_total_pnl"]:+.1f} with understandable execution changes and without obvious churn damage.',
            '- The remaining edge is still tiny, so this should only be one last practical switch, not a reason to keep grinding many more variants.',
        ])
    else:
        lines.extend([
            '- Keep `model_E_plus_11` or switch? **Keep `model_E_plus_11`.**',
            '- Why? Because none of the micro-refinements produced an official improvement that is clearly worth the extra complexity. At this point the differences are too small and too noise-like to justify continuing this family aggressively.',
            '- Recommendation: freeze `model_E_plus_11.py` as the final baseline for this architecture.',
            '- Next justified direction: stop micro-iterating this family and shift effort to a different edge source such as auction optimization, packaging/deployment robustness, or future-round preparation.',
        ])
    (ROUND_DIR / 'round1_model_E_plus_11_microrefinement_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    product_df, local_combined, pepper_df, ideal_df = run_local()
    official_df = run_official(MODELS)
    # sensitivity only on best local promising variants 14 and 16
    sens_frames = []
    for model in ['model_E_plus_14', 'model_E_plus_16']:
        specs = sensitivity_specs(model)
        if specs:
            sens_frames.append(run_sensitivity(model, specs))
    sensitivity_df = pd.concat(sens_frames, ignore_index=True) if sens_frames else pd.DataFrame()
    product_df.to_csv(RESULTS_DIR / 'local_product_metrics.csv', index=False)
    local_combined.to_csv(RESULTS_DIR / 'local_combined_metrics.csv', index=False)
    pepper_df.to_csv(RESULTS_DIR / 'pepper_diagnostics.csv', index=False)
    ideal_df.to_csv(RESULTS_DIR / 'pepper_ideal_hold_reference.csv', index=False)
    official_df.to_csv(RESULTS_DIR / 'official_combined_metrics.csv', index=False)
    sensitivity_df.to_csv(RESULTS_DIR / 'sensitivity_metrics.csv', index=False)
    write_report(local_combined, product_df, pepper_df, official_df, sensitivity_df)


if __name__ == '__main__':
    main()
