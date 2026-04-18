from __future__ import annotations

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path('/Users/pablo/Desktop/prosperity')
RESULTS = ROOT / 'round_1' / 'results' / 'model_v3'
ASH_MC = ROOT / 'round_1' / 'results' / 'montecarlo' / 'ash_mm_v0' / '20260414_184904' / 'dashboard.json'
PEPPER_MC = ROOT / 'round_1' / 'results' / 'montecarlo' / 'pepper_root_v3' / '20260414_194515' / 'dashboard.json'


def main() -> None:
    ash_bt = pd.read_csv(RESULTS / 'backtest_model_v3_results_-2_-1_0_ash.csv')
    pepper_bt = pd.read_csv(RESULTS / 'backtest_model_v3_results_-2_-1_0_pepper.csv')
    ash_rep = pd.read_csv(RESULTS / 'replay_summary_ash.csv')
    pepper_rep = pd.read_csv(RESULTS / 'replay_summary_pepper.csv')

    ash_bt_total = float(ash_bt['pnl'].iloc[-1])
    pepper_bt_total = float(pepper_bt['pnl'].iloc[-1])
    ash_rep_total = float(ash_rep.loc[ash_rep['day'].astype(str) == 'ALL', 'final_pnl'].iloc[0])
    pepper_rep_total = float(pepper_rep.loc[pepper_rep['day'].astype(str) == 'ALL', 'final_pnl'].iloc[0])

    rows = [
        ['ASH_COATED_OSMIUM', ash_bt_total, ash_rep_total],
        ['INTARIAN_PEPPER_ROOT', pepper_bt_total, pepper_rep_total],
        ['COMBINED', ash_bt_total + pepper_bt_total, ash_rep_total + pepper_rep_total],
    ]
    df = pd.DataFrame(rows, columns=['product', 'backtest_total_pnl', 'replay_total_pnl'])
    df.to_csv(RESULTS / 'model_v3_combined_metrics.csv', index=False)

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(11, 6), facecolor='#0f172a')
    ax.set_facecolor('#111827')
    x = range(len(df))
    ax.bar([i - 0.18 for i in x], df['backtest_total_pnl'], width=0.36, color='#38bdf8', label='Backtest')
    ax.bar([i + 0.18 for i in x], df['replay_total_pnl'], width=0.36, color='#f59e0b', label='Replay')
    ax.set_xticks(list(x))
    ax.set_xticklabels(df['product'])
    ax.set_ylabel('PnL')
    ax.set_title('round_1 model_v3 — Combined scorecard')
    ax.legend(frameon=False)
    ax.grid(True, axis='y', alpha=0.2)
    for i, row in df.iterrows():
        ax.text(i - 0.18, row['backtest_total_pnl'] + 1200, f"{row['backtest_total_pnl']:,.0f}", ha='center', fontsize=9)
        ax.text(i + 0.18, row['replay_total_pnl'] + 1200, f"{row['replay_total_pnl']:,.0f}", ha='center', fontsize=9)
    fig.savefig(RESULTS / 'model_v3_combined_scorecard.png', dpi=180, bbox_inches='tight')
    plt.close(fig)

    md = f"""# model_v3 — Combined round_1 summary

## Composition
- `ASH_COATED_OSMIUM`: logic from `/Users/pablo/Desktop/prosperity/round_1/models/ash_mm_v0.py`
- `INTARIAN_PEPPER_ROOT`: robust logic from `/Users/pablo/Desktop/prosperity/round_1/models/pepper_root_v3.py`

## Replay totals
- Ash: **{ash_rep_total:,.1f}**
- Pepper: **{pepper_rep_total:,.1f}**
- Combined replay total: **{ash_rep_total + pepper_rep_total:,.1f}**

## Backtest totals
- Ash: **{ash_bt_total:,.1f}**
- Pepper: **{pepper_bt_total:,.1f}**
- Combined backtest total: **{ash_bt_total + pepper_bt_total:,.1f}**

## Notes
- Ash was validated with the stationary market-making template.
- Pepper was upgraded to a more robust trend + pullback v3 with regime/inventory guards.
- The combined model dispatches by product in a single trader file: `/Users/pablo/Desktop/prosperity/round_1/models/model_v3.py`.
"""
    (RESULTS / 'model_v3_combined_summary.md').write_text(md)
    print('Combined model summary created in', RESULTS)


if __name__ == '__main__':
    main()
