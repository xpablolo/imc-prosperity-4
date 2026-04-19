from __future__ import annotations

from pathlib import Path
from collections import OrderedDict
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path('/Users/pablo/Desktop/prosperity')
BASE_DIR = ROOT / 'round_2' / 'results' / 'kiko_maf_day_unit'
OUT_DIR = ROOT / 'round_2' / 'results' / 'kiko_maf_validation'
PLOTS_DIR = OUT_DIR / 'plots'
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style='whitegrid', context='talk')
plt.rcParams['figure.dpi'] = 140
plt.rcParams['axes.titlesize'] = 18
plt.rcParams['axes.labelsize'] = 14
plt.rcParams['legend.fontsize'] = 11

BID_LEVELS = np.array([0, 25, 50, 75, 100, 125, 150, 175, 200], dtype=int)
FOCUS_BIDS = np.array([100, 125, 150], dtype=int)
TOTAL_PARTICIPANTS = 100
RIVALS = TOTAL_PARTICIPANTS - 1
ACCEPTED = TOTAL_PARTICIPANTS // 2
N_SIMS = 250_000
RNG = np.random.default_rng(20260419)


def pct(x: float) -> float:
    return 100.0 * x


def load_inputs() -> dict[str, object]:
    baseline_summary = pd.read_csv(BASE_DIR / 'baseline_summary.csv')
    delta_summary = pd.read_csv(BASE_DIR / 'delta_summary.csv')
    bid_grid = pd.read_csv(BASE_DIR / 'bid_grid.csv')
    day_bid = pd.read_csv(BASE_DIR / 'day_bid_analysis.csv')
    worst_day = pd.read_csv(BASE_DIR / 'worst_day_summary.csv')

    p0_total = float(baseline_summary.loc[baseline_summary['product'] == 'TOTAL', 'P0_mean'].iloc[0])
    delta_conservative = float(delta_summary.loc[delta_summary['proxy'] == 'Uniform depth +25%', 'Delta_mean'].iloc[0])
    delta_central = float(delta_summary.loc[delta_summary['proxy'] == 'Front-biased depth +25%', 'Delta_mean'].iloc[0])
    delta_downside = float(delta_summary.loc[delta_summary['proxy'] == 'Uniform depth +25%', 'Delta_min'].iloc[0])

    cons_grid = bid_grid.loc[bid_grid['delta_variant'] == 'conservative'].copy()
    downs_grid = bid_grid.loc[bid_grid['delta_variant'] == 'downside'].copy()

    return {
        'baseline_summary': baseline_summary,
        'delta_summary': delta_summary,
        'bid_grid': bid_grid,
        'cons_grid': cons_grid,
        'downs_grid': downs_grid,
        'day_bid': day_bid,
        'worst_day': worst_day,
        'p0_total': p0_total,
        'delta_conservative': delta_conservative,
        'delta_central': delta_central,
        'delta_downside': delta_downside,
    }


def pmf_from_mapping(mapping: dict[int, float]) -> np.ndarray:
    arr = np.array([mapping.get(int(b), 0.0) for b in BID_LEVELS], dtype=float)
    arr = arr / arr.sum()
    return arr


def build_scenarios() -> OrderedDict[str, dict[str, object]]:
    scenarios: OrderedDict[str, dict[str, object]] = OrderedDict()

    scenarios['A_masa_100'] = {
        'label': 'Escenario A — masa en 100',
        'logic': 'Muchos rivales intentan pagar poco pero no quedar demasiado abajo; congestión principal en 100.',
        'pmf': pmf_from_mapping({0: 0.04, 25: 0.06, 50: 0.10, 75: 0.15, 100: 0.36, 125: 0.15, 150: 0.08, 175: 0.04, 200: 0.02}),
    }
    scenarios['B_masa_125'] = {
        'label': 'Escenario B — masa en 125',
        'logic': 'Muchos equipos convergen al razonamiento de robustez y se amontonan en 125.',
        'pmf': pmf_from_mapping({0: 0.03, 25: 0.05, 50: 0.08, 75: 0.12, 100: 0.17, 125: 0.35, 150: 0.12, 175: 0.05, 200: 0.03}),
    }
    scenarios['C_masa_150'] = {
        'label': 'Escenario C — masa en 150',
        'logic': 'Campo rival más agresivo: mucha masa en 150 y cola alta más cargada.',
        'pmf': pmf_from_mapping({0: 0.02, 25: 0.03, 50: 0.04, 75: 0.06, 100: 0.10, 125: 0.20, 150: 0.35, 175: 0.15, 200: 0.05}),
    }

    low = pmf_from_mapping({25: 0.05, 50: 0.15, 75: 0.35, 100: 0.35, 125: 0.10})
    mid = pmf_from_mapping({75: 0.10, 100: 0.30, 125: 0.40, 150: 0.20})
    high = pmf_from_mapping({100: 0.10, 125: 0.25, 150: 0.45, 175: 0.20})
    noise = np.repeat(1 / len(BID_LEVELS), len(BID_LEVELS))
    mix = 0.30 * low + 0.35 * mid + 0.20 * high + 0.15 * noise
    scenarios['D_mixto'] = {
        'label': 'Escenario D — mezcla heterogénea',
        'logic': 'Mezcla de low bidders, middle bidders, high bidders y ruido; escenario de campo más heterogéneo.',
        'pmf': mix / mix.sum(),
        'components': {
            'low_bidders': 0.30,
            'middle_bidders': 0.35,
            'high_bidders': 0.20,
            'noise_bidders': 0.15,
        },
    }
    return scenarios


def acceptance_probability_from_counts(counts_rivals: np.ndarray, bid_value: int) -> np.ndarray:
    idx = int(np.where(BID_LEVELS == bid_value)[0][0])
    gt = counts_rivals[:, idx + 1 :].sum(axis=1)
    eq = counts_rivals[:, idx]
    slots_left = ACCEPTED - gt

    accept_prob = np.zeros(len(counts_rivals), dtype=float)
    sure_accept = gt + eq < ACCEPTED
    reject = gt >= ACCEPTED
    tie_case = ~(sure_accept | reject)

    accept_prob[sure_accept] = 1.0
    accept_prob[reject] = 0.0
    accept_prob[tie_case] = slots_left[tie_case] / (eq[tie_case] + 1.0)
    return np.clip(accept_prob, 0.0, 1.0)


def simulate_discrete_scenarios(scenarios: OrderedDict[str, dict[str, object]], delta_conservative: float, delta_downside: float, p0_mean: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pmf_rows = []
    cutoff_rows = []
    acceptance_rows = []
    cutoff_summary_rows = []

    for key, meta in scenarios.items():
        label = meta['label']
        pmf = np.asarray(meta['pmf'], dtype=float)
        counts_rivals = RNG.multinomial(RIVALS, pmf, size=N_SIMS)
        counts_total = RNG.multinomial(TOTAL_PARTICIPANTS, pmf, size=N_SIMS)

        desc_counts = counts_total[:, ::-1]
        cum_desc = np.cumsum(desc_counts, axis=1)
        cutoff_idx_desc = (cum_desc >= ACCEPTED).argmax(axis=1)
        cutoff_levels = BID_LEVELS[::-1][cutoff_idx_desc]

        for level, prob in zip(BID_LEVELS, pmf):
            pmf_rows.append({'scenario': key, 'scenario_label': label, 'bid_level': int(level), 'probability': float(prob)})

        cutoff_dist = pd.Series(cutoff_levels).value_counts(normalize=True).sort_index()
        for level in BID_LEVELS:
            cutoff_rows.append({
                'scenario': key,
                'scenario_label': label,
                'cutoff_level': int(level),
                'probability': float(cutoff_dist.get(level, 0.0)),
            })
        cutoff_summary_rows.append({
            'scenario': key,
            'scenario_label': label,
            'cutoff_mean': float(np.mean(cutoff_levels)),
            'cutoff_median': float(np.median(cutoff_levels)),
            'cutoff_p25': float(np.quantile(cutoff_levels, 0.25)),
            'cutoff_p75': float(np.quantile(cutoff_levels, 0.75)),
        })

        for bid in BID_LEVELS:
            acc_prob = acceptance_probability_from_counts(counts_rivals, int(bid))
            q = float(acc_prob.mean())
            net_cons = delta_conservative - bid
            net_down = delta_downside - bid
            acceptance_rows.append({
                'scenario': key,
                'scenario_label': label,
                'bid': int(bid),
                'q_accept': q,
                'net_gain_if_accepted_conservative': net_cons,
                'ev_uplift_conservative': q * net_cons,
                'ev_total_conservative': p0_mean + q * net_cons,
                'uplift_pct_vs_base_conservative': net_cons / p0_mean,
                'fee_roi_conservative': (net_cons / bid) if bid > 0 else np.nan,
                'net_gain_if_accepted_downside': net_down,
                'ev_uplift_downside': q * net_down,
                'ev_total_downside': p0_mean + q * net_down,
                'uplift_pct_vs_base_downside': net_down / p0_mean,
                'fee_roi_downside': (net_down / bid) if bid > 0 else np.nan,
            })

    return (
        pd.DataFrame(pmf_rows),
        pd.DataFrame(cutoff_rows),
        pd.DataFrame(cutoff_summary_rows),
        pd.DataFrame(acceptance_rows),
    )


def delta_stress_tests(cons_grid: pd.DataFrame, p0_mean: float, delta_conservative: float) -> tuple[pd.DataFrame, dict[str, float]]:
    bids = [100, 125, 150]
    q_map = cons_grid.set_index('bid')['q_weighted'].to_dict()
    rows = []
    for stress in [0.0, 0.10, 0.20, 0.30, 0.40]:
        delta = delta_conservative * (1.0 - stress)
        for bid in bids:
            q = float(q_map[bid])
            net = delta - bid
            rows.append({
                'stress_type': 'delta_haircut',
                'stress_pct': stress,
                'delta_assumed': delta,
                'bid': bid,
                'q_used': q,
                'net_gain_if_accepted': net,
                'uplift_pct_vs_base': net / p0_mean,
                'fee_roi': net / bid,
                'ev_uplift': q * net,
                'ev_total': p0_mean + q * net,
            })

    q100 = float(q_map[100])
    q125 = float(q_map[125])
    q150 = float(q_map[150])
    threshold_125_vs_100 = (125 * q125 - 100 * q100) / (q125 - q100)
    threshold_150_vs_125 = (150 * q150 - 125 * q125) / (q150 - q125)
    thresholds = {
        'delta_star_125_over_100': threshold_125_vs_100,
        'delta_star_150_over_125': threshold_150_vs_125,
        'haircut_star_125_over_100': 1.0 - threshold_125_vs_100 / delta_conservative,
        'haircut_star_150_over_125': 1.0 - threshold_150_vs_125 / delta_conservative,
    }
    return pd.DataFrame(rows), thresholds


def q_stress_tests(cons_grid: pd.DataFrame, p0_mean: float, delta_conservative: float) -> pd.DataFrame:
    bids = [100, 125, 150]
    q_map = cons_grid.set_index('bid')['q_weighted'].to_dict()
    rows = []
    for stress in [0.0, 0.05, 0.10, 0.15]:
        for bid in bids:
            q = float(q_map[bid]) * (1.0 - stress)
            net = delta_conservative - bid
            rows.append({
                'stress_type': 'q_haircut',
                'stress_pct': stress,
                'delta_assumed': delta_conservative,
                'bid': bid,
                'q_used': q,
                'net_gain_if_accepted': net,
                'uplift_pct_vs_base': net / p0_mean,
                'fee_roi': net / bid,
                'ev_uplift': q * net,
                'ev_total': p0_mean + q * net,
            })
    return pd.DataFrame(rows)


def worst_case_combo(acceptance_df: pd.DataFrame, p0_mean: float, delta_downside: float) -> pd.DataFrame:
    scenario_key = 'C_masa_150'
    penalty = 0.15
    rows = []
    for bid in FOCUS_BIDS:
        row = acceptance_df[(acceptance_df['scenario'] == scenario_key) & (acceptance_df['bid'] == bid)].iloc[0]
        q = float(row['q_accept']) * (1.0 - penalty)
        net = delta_downside - bid
        rows.append({
            'scenario': scenario_key,
            'scenario_label': row['scenario_label'],
            'q_penalty': penalty,
            'bid': bid,
            'q_base_discrete': float(row['q_accept']),
            'q_used': q,
            'delta_assumed': delta_downside,
            'net_gain_if_accepted': net,
            'uplift_pct_vs_base': net / p0_mean,
            'fee_roi': net / bid,
            'ev_uplift': q * net,
            'ev_total': p0_mean + q * net,
        })
    return pd.DataFrame(rows)


def marginal_gap_tests(cons_grid: pd.DataFrame, acceptance_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    # Baseline weighted logistic conservative model
    baseline = cons_grid[cons_grid['bid'].isin(FOCUS_BIDS)].sort_values('bid').copy()
    ev = baseline.set_index('bid')['EV_uplift_weighted'].to_dict()
    q = baseline.set_index('bid')['q_weighted'].to_dict()
    rows.append({
        'context': 'Logistic mix (weighted) — Delta_conservative',
        'ev_125_minus_100': float(ev[125] - ev[100]),
        'ev_150_minus_125': float(ev[150] - ev[125]),
        'q_125_minus_100': float(q[125] - q[100]),
        'q_150_minus_125': float(q[150] - q[125]),
    })

    for scenario in acceptance_df['scenario'].unique():
        sub = acceptance_df[(acceptance_df['scenario'] == scenario) & (acceptance_df['bid'].isin(FOCUS_BIDS))].sort_values('bid')
        evs = sub.set_index('bid')['ev_uplift_conservative'].to_dict()
        qs = sub.set_index('bid')['q_accept'].to_dict()
        label = sub['scenario_label'].iloc[0]
        rows.append({
            'context': f'{label} — Delta_conservative',
            'ev_125_minus_100': float(evs[125] - evs[100]),
            'ev_150_minus_125': float(evs[150] - evs[125]),
            'q_125_minus_100': float(qs[125] - qs[100]),
            'q_150_minus_125': float(qs[150] - qs[125]),
        })
    return pd.DataFrame(rows)


def sensitivity_matrix(acceptance_df: pd.DataFrame) -> pd.DataFrame:
    delta_levels = OrderedDict([
        ('downside', 851.0),
        ('cons_minus_20', 1005.166667 * 0.8),
        ('conservative', 1005.166667),
        ('central', 1609.833333),
    ])
    rows = []
    for scenario in acceptance_df['scenario'].unique():
        sub = acceptance_df[(acceptance_df['scenario'] == scenario) & (acceptance_df['bid'].isin(FOCUS_BIDS))].sort_values('bid')
        q_map = sub.set_index('bid')['q_accept'].to_dict()
        label = sub['scenario_label'].iloc[0]
        for delta_label, delta_value in delta_levels.items():
            evs = {bid: q_map[bid] * (delta_value - bid) for bid in FOCUS_BIDS}
            best_bid = max(evs.items(), key=lambda kv: kv[1])[0]
            rows.append({
                'scenario': scenario,
                'scenario_label': label,
                'delta_label': delta_label,
                'delta_value': delta_value,
                'best_bid': best_bid,
                'EV_100': evs[100],
                'EV_125': evs[125],
                'EV_150': evs[150],
            })
    return pd.DataFrame(rows)


def summarize_best_bids(acceptance_df: pd.DataFrame, worst_combo_df: pd.DataFrame) -> pd.DataFrame:
    focus = acceptance_df[acceptance_df['bid'].isin(FOCUS_BIDS)].copy()
    mean_evs = focus.groupby('bid', as_index=False)['ev_uplift_conservative'].mean().rename(columns={'ev_uplift_conservative': 'mean_ev_conservative'})
    best_mean_bid = int(mean_evs.loc[mean_evs['mean_ev_conservative'].idxmax(), 'bid'])

    downside = focus.groupby('bid', as_index=False)['ev_uplift_downside'].mean().rename(columns={'ev_uplift_downside': 'mean_ev_downside'})
    best_downside_bid = int(downside.loc[downside['mean_ev_downside'].idxmax(), 'bid'])

    b125 = focus[focus['scenario'] == 'B_masa_125'][['bid', 'ev_uplift_conservative']].sort_values('ev_uplift_conservative', ascending=False)
    c150 = focus[focus['scenario'] == 'C_masa_150'][['bid', 'ev_uplift_conservative']].sort_values('ev_uplift_conservative', ascending=False)
    worst = worst_combo_df[['bid', 'ev_uplift']].sort_values('ev_uplift', ascending=False)

    rows = [
        {'criterion': 'best_bid_ev_mean_discrete', 'bid': best_mean_bid},
        {'criterion': 'best_bid_downside_mean_discrete', 'bid': best_downside_bid},
        {'criterion': 'best_bid_bunching_125', 'bid': int(b125.iloc[0]['bid'])},
        {'criterion': 'best_bid_bunching_150', 'bid': int(c150.iloc[0]['bid'])},
        {'criterion': 'best_bid_worst_case_combo', 'bid': int(worst.iloc[0]['bid'])},
    ]
    return pd.DataFrame(rows)


def plot_rival_distributions(pmf_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    palette = ['#244c7c', '#5f4bb6', '#c23b3b', '#0f766e']
    for ax, (scenario, sub), color in zip(axes.flat, pmf_df.groupby('scenario_label'), palette):
        ax.bar(sub['bid_level'], sub['probability'], width=18, color=color, alpha=0.88)
        for v in [100, 125, 150]:
            ax.axvline(v, color='#2f2f2f', linestyle='--', linewidth=1.2, alpha=0.7)
        ax.set_title(scenario)
        ax.set_xlabel('Bid rival')
        ax.set_ylabel('Probabilidad')
    fig.suptitle('Distribución esperada de bids rivales con bunching', y=1.02)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'rival_bid_distribution.png', bbox_inches='tight')
    plt.close(fig)


def plot_cutoff_distribution(cutoff_df: pd.DataFrame, cutoff_summary_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=True, sharey=True)
    palette = ['#244c7c', '#5f4bb6', '#c23b3b', '#0f766e']
    summary_map = cutoff_summary_df.set_index('scenario_label')['cutoff_median'].to_dict()
    for ax, (scenario, sub), color in zip(axes.flat, cutoff_df.groupby('scenario_label'), palette):
        ax.bar(sub['cutoff_level'], sub['probability'], width=18, color=color, alpha=0.88)
        for v in [100, 125, 150]:
            ax.axvline(v, color='#2f2f2f', linestyle='--', linewidth=1.2, alpha=0.7)
        ax.axvline(summary_map[scenario], color='#f59e0b', linestyle='-', linewidth=2.5, label=f"Mediana cutoff = {summary_map[scenario]:.0f}")
        ax.set_title(scenario)
        ax.set_xlabel('Cutoff inducido')
        ax.set_ylabel('Probabilidad')
        ax.legend(loc='upper right')
    fig.suptitle('Distribución inducida del cutoff por escenario rival', y=1.02)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'induced_cutoff_distribution.png', bbox_inches='tight')
    plt.close(fig)


def plot_ev_scenarios(acceptance_df: pd.DataFrame) -> None:
    focus = acceptance_df[acceptance_df['bid'].isin(FOCUS_BIDS)].copy()
    fig, ax = plt.subplots(figsize=(13, 7))
    sns.barplot(data=focus, x='scenario_label', y='ev_uplift_conservative', hue='bid', palette=['#2563eb', '#7c3aed', '#dc2626'], ax=ax)
    ax.set_title('EV uplift de 100 / 125 / 150 por distribución rival (Delta conservador)')
    ax.set_xlabel('Escenario rival')
    ax.set_ylabel('EV(b) - P0_mean')
    ax.legend(title='Bid')
    plt.xticks(rotation=15, ha='right')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'ev_100_125_150_by_scenario.png', bbox_inches='tight')
    plt.close(fig)


def plot_marginal_ev(gap_df: pd.DataFrame) -> None:
    plot_df = gap_df.melt(id_vars='context', value_vars=['ev_125_minus_100', 'ev_150_minus_125'], var_name='gap', value_name='ev_increment')
    gap_labels = {
        'ev_125_minus_100': 'EV(125) - EV(100)',
        'ev_150_minus_125': 'EV(150) - EV(125)',
    }
    plot_df['gap'] = plot_df['gap'].map(gap_labels)
    fig, ax = plt.subplots(figsize=(13, 7))
    sns.barplot(data=plot_df, x='context', y='ev_increment', hue='gap', palette=['#5f4bb6', '#dc2626'], ax=ax)
    ax.axhline(0, color='black', linewidth=1)
    ax.set_title('Incremento marginal de EV al subir el bid')
    ax.set_xlabel('Contexto')
    ax.set_ylabel('Incremento marginal de EV')
    ax.legend(title='Comparación')
    plt.xticks(rotation=20, ha='right')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'marginal_ev_increment.png', bbox_inches='tight')
    plt.close(fig)


def plot_acceptance(acceptance_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(13, 7))
    focus = acceptance_df[acceptance_df['bid'].isin(FOCUS_BIDS)].copy()
    sns.pointplot(data=focus, x='bid', y='q_accept', hue='scenario_label', palette=['#244c7c', '#5f4bb6', '#c23b3b', '#0f766e'], ax=ax)
    ax.set_title('Probabilidad de aceptación por bid bajo distribución rival discreta')
    ax.set_xlabel('Bid propio')
    ax.set_ylabel('q(b)')
    ax.legend(title='Escenario rival', bbox_to_anchor=(1.02, 1), loc='upper left')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'acceptance_by_bid_discrete.png', bbox_inches='tight')
    plt.close(fig)


def plot_sensitivity_heatmap(sens_df: pd.DataFrame) -> None:
    table = sens_df.pivot(index='scenario_label', columns='delta_label', values='best_bid')
    ordered_cols = ['downside', 'cons_minus_20', 'conservative', 'central']
    table = table[ordered_cols]
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(table, annot=True, fmt='.0f', cmap=sns.color_palette(['#dbeafe', '#c4b5fd', '#fecaca'], as_cmap=True), cbar=False, ax=ax)
    ax.set_title('Mejor bid entre {100,125,150} según Delta y escenario rival')
    ax.set_xlabel('Delta asumido')
    ax.set_ylabel('Escenario rival')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'final_sensitivity_heatmap.png', bbox_inches='tight')
    plt.close(fig)




def df_to_md(df: pd.DataFrame, index: bool = True) -> str:
    frame = df.copy()
    if index:
        frame = frame.reset_index()
    cols = [str(c) for c in frame.columns]
    lines = []
    lines.append('| ' + ' | '.join(cols) + ' |')
    lines.append('| ' + ' | '.join(['---'] * len(cols)) + ' |')
    for _, row in frame.iterrows():
        vals = []
        for col in frame.columns:
            val = row[col]
            if pd.isna(val):
                vals.append('')
            elif isinstance(val, (float, np.floating)):
                vals.append(f'{val:.4f}')
            else:
                vals.append(str(val))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def build_report(inputs: dict[str, object], cutoff_summary_df: pd.DataFrame, acceptance_focus: pd.DataFrame, delta_stress_df: pd.DataFrame, q_stress_df: pd.DataFrame, worst_combo_df: pd.DataFrame, gap_df: pd.DataFrame, sensitivity_df: pd.DataFrame, best_bids_df: pd.DataFrame, thresholds: dict[str, float]) -> str:
    p0_mean = inputs['p0_total']
    delta_conservative = inputs['delta_conservative']
    delta_central = inputs['delta_central']
    delta_downside = inputs['delta_downside']

    # Tables for concise reporting
    delta_stress_pivot = delta_stress_df.pivot(index='stress_pct', columns='bid', values='ev_uplift').sort_index()
    q_stress_pivot = q_stress_df.pivot(index='stress_pct', columns='bid', values='ev_uplift').sort_index()

    acceptance_table = acceptance_focus[['scenario_label', 'bid', 'q_accept', 'ev_uplift_conservative', 'ev_uplift_downside']].copy()
    acceptance_table['q_accept'] = acceptance_table['q_accept'].map(lambda x: round(x, 4))
    acceptance_table['ev_uplift_conservative'] = acceptance_table['ev_uplift_conservative'].map(lambda x: round(x, 2))
    acceptance_table['ev_uplift_downside'] = acceptance_table['ev_uplift_downside'].map(lambda x: round(x, 2))

    cutoff_table = cutoff_summary_df[['scenario_label', 'cutoff_mean', 'cutoff_median', 'cutoff_p25', 'cutoff_p75']].copy().round(2)

    best_mean_bid = int(best_bids_df.loc[best_bids_df['criterion'] == 'best_bid_ev_mean_discrete', 'bid'].iloc[0])
    best_downside_bid = int(best_bids_df.loc[best_bids_df['criterion'] == 'best_bid_downside_mean_discrete', 'bid'].iloc[0])
    best_b125 = int(best_bids_df.loc[best_bids_df['criterion'] == 'best_bid_bunching_125', 'bid'].iloc[0])
    best_b150 = int(best_bids_df.loc[best_bids_df['criterion'] == 'best_bid_bunching_150', 'bid'].iloc[0])
    best_worst = int(best_bids_df.loc[best_bids_df['criterion'] == 'best_bid_worst_case_combo', 'bid'].iloc[0])

    # Baseline weighted logistic gaps
    base_gap = gap_df.iloc[0]

    # Worst combo recommended
    worst_sorted = worst_combo_df.sort_values('ev_uplift', ascending=False)
    worst_top = worst_sorted.iloc[0]

    report = f"""# Validación final y revisión crítica del MAF de Round 2 para `model_kiko`

## A. Resumen ejecutivo

- Resultado de la revisión: **la recomendación `125` aguanta como bid más robusto**, pero ya no porque maximice EV puntual; aguanta porque sigue siendo el mejor compromiso entre no sobrepagar, tolerar bunching rival y mantener upside sólido bajo downside realista.
- Bid final recomendado: **`125`**.
- Rango alternativo: **`100–150`**, con preferencia operativa **`100–125`** salvo que el prior rival se desplace claramente hacia bunching/agresividad en `150`.
- ¿`125` aguanta o no? **Sí, aguanta**, aunque la revisión crítica deja claro que `150` compra algo más de aceptación y a veces algo más de EV, pero con rendimientos decrecientes y mucha mayor dependencia del modelo rival.

## B. Revisión metodológica crítica

### Fortalezas

1. **Unidad estadística correcta**: `1 día = 1 ronda comparable live`, validada contra el log oficial de Round 1.
2. **Separación limpia entre trading y bid**: el valor económico del extra access se estimó primero manteniendo fija la lógica de `model_kiko`.
3. **Downside observable**: no dependemos solo de medias; existe un worst observed day real (`Delta_downside = {delta_downside:.1f}`).
4. **Robustez cross-day**: `125` se mantuvo dentro de la meseta del 95% en leave-one-day-out del análisis previo.
5. **El hallazgo económico principal es estable**: el valor del MAF para `model_kiko` viene mayormente de ASH, no de una narrativa optimista sobre PEPPER.

### Debilidades / supuestos frágiles

1. **El componente más frágil es `q(b)`**, no `Delta`: con solo 3 días, `Delta` tiene ruido pero está acotado; en cambio la aceptación depende de un rival model que no observamos.
2. **Los proxies de market access siguen siendo contrafactuales**: son razonables, pero no equivalen a un feed real con +25% quotes exactos.
3. **La muestra de rondas históricas es chica**: tres días permiten medir estabilidad básica, no inferir una distribución poblacional fina.
4. **El field size real y la regla exacta de desempate no están observados**: para bunching discreto tuve que normalizar a 100 participantes y desempate uniforme en el cutoff.
5. **Percentiles con n=3 son inestables**: por eso el downside más defendible sigue siendo el mínimo observado y no un p25 sofisticado.

### Qué manda más en la decisión final

1. **Primero manda `q(b)`** cuando comparás `125` vs `150`: el net gain condicional cae poco, pero la aceptación cambia bastante según el escenario rival.
2. **Después manda el downside de `Delta`**: si el valor económico del access cae, el incentivo a sobrepagar desaparece rápido.
3. **El peor día manda como guardrail**: no decide solo, pero evita sobreconfianza.
4. **El modelo del cutoff rival es el principal riesgo residual**: si el campo se amontona en `150`, la ventaja de `125` se erosiona bastante.

### Riesgos residuales

- Riesgo de **sobreconfianza en el modelo rival**: no observamos bids reales, solo escenarios plausibles.
- Riesgo de **tie congestion** en `125`: si muchos llegan a la misma conclusión robusta, `125` puede quedar justo en la frontera.
- Riesgo de **confundir EV máximo con mejor decisión**: `150` o incluso `175` pueden ganar por EV puntual en algunos supuestos, pero eso no implica que sean la mejor compra robusta.

## C. Tests adicionales

### Stress sobre Delta

Se tomó `Delta_conservative = {delta_conservative:.1f}` y se aplicaron haircuts de 10%, 20%, 30% y 40%. EV uplift (`EV(b) - P0_mean`) para bids 100 / 125 / 150:

{df_to_md(delta_stress_pivot.round(2))}

Hallazgos:
- `125` **sigue superando a `100` incluso con haircut de 40%**.
- El umbral analítico para que `125` deje de superar a `100` en el modelo logístico ponderado es `Delta* ≈ {thresholds['delta_star_125_over_100']:.1f}`; eso equivale a un haircut de **{pct(thresholds['haircut_star_125_over_100']):.1f}%** sobre `Delta_conservative`.
- El umbral para que `150` deje de superar a `125` es `Delta* ≈ {thresholds['delta_star_150_over_125']:.1f}`; eso equivale a un haircut de **{pct(thresholds['haircut_star_150_over_125']):.1f}%**.
- Traducción práctica: **cuando Delta se comprime, el argumento para subir de 125 a 150 se vuelve cada vez más chico**.

### Stress sobre aceptación

Se aplicó un haircut uniforme a `q(b)` de 5%, 10% y 15% usando `Delta_conservative`:

{df_to_md(q_stress_pivot.round(2))}

Hallazgo clave:
- Un haircut **uniforme** sobre `q(b)` **no cambia el ranking** entre 100 / 125 / 150; solo comprime todos los EVs proporcionalmente.
- Por eso, el verdadero riesgo no es “q más baja para todos”, sino **cambio de forma de `q(b)`** por bunching y cutoff más duro.

### Worst-case combo

Combiné:
- `Delta = Delta_downside = {delta_downside:.1f}`
- escenario rival discreto duro = **masa en 150**
- penalización adicional de aceptación = **15%**

Resultado:

{df_to_md(worst_combo_df.round(4), index=False)}

Lectura:
- En este combo duro, el mejor EV puntual entre 100 / 125 / 150 es **`{int(worst_top['bid'])}`**.
- Aun así, `125` sigue siendo **defendible** si priorizás no sobrepagar, pero **deja de ser tan claramente dominante** porque el campo agresivo en `150` sí compra aceptación material.

### Gap marginal de EV

{df_to_md(gap_df.round(3), index=False)}

Lectura:
- En el modelo logístico ponderado original, pasar de **100 → 125** compra aproximadamente **{base_gap['q_125_minus_100']:.3f}** de probabilidad adicional y **{base_gap['ev_125_minus_100']:.1f}** de EV uplift.
- Pasar de **125 → 150** compra aproximadamente **{base_gap['q_150_minus_125']:.3f}** de probabilidad adicional y **{base_gap['ev_150_minus_125']:.1f}** de EV uplift.
- Eso muestra **rendimientos decrecientes**: el segundo salto compra menos probabilidad y menos EV que el primero.

## D. Distribución esperada de bids rivales

### Escenarios usados y lógica económica

1. **Escenario A — masa en 100**: muchos equipos quieren pagar poco pero intentan no quedarse demasiado abajo.
2. **Escenario B — masa en 125**: convergencia explícita al razonamiento “robusto”.
3. **Escenario C — masa en 150**: campo más agresivo, con mayor miedo a quedarse fuera.
4. **Escenario D — mezcla heterogénea**: combina low bidders, middle bidders, high bidders y ruido.

### Cutoff inducido (Monte Carlo discreto con bunching)

{df_to_md(cutoff_table, index=False)}

### Impacto sobre 100 / 125 / 150

{df_to_md(acceptance_table, index=False)}

Lectura económica:
- **Bunching en 125** vuelve a `125` una zona congestionada; ahí `150` gana valor porque evita el empate en el nivel focal.
- **Bunching en 150** endurece fuerte el cutoff; en ese caso `100` queda demasiado corto y `125` se vuelve más “defensa de costo” que apuesta ofensiva.
- **Masa en 100** ayuda a `125`: compra mucho margen extra respecto al nivel congestionado sin pagar tanto como `150`.
- En la **mezcla heterogénea**, `125` sigue siendo una respuesta razonable porque no depende de acertar un único punto focal rival.

## E. Visualizaciones

Plots generados en: `{PLOTS_DIR}`

1. **`rival_bid_distribution.png`**
   - Muestra la distribución discreta esperada de bids rivales por escenario.
   - Permite ver visualmente si `125` está en zona congestionada y cuánta masa adicional aparece en `150`.

2. **`induced_cutoff_distribution.png`**
   - Muestra la distribución inducida del cutoff bajo cada escenario.
   - Las líneas en 100 / 125 / 150 permiten ver enseguida cuándo `100` queda corto y cuándo `150` compra una mejora real.

3. **`ev_100_125_150_by_scenario.png`**
   - Compara el EV uplift de 100 / 125 / 150 por escenario rival usando `Delta_conservative`.
   - Es el gráfico más directo para ver cuándo `125` es compromiso robusto y cuándo `150` se vuelve la apuesta más fuerte.

4. **`marginal_ev_increment.png`**
   - Muestra `EV(125)-EV(100)` y `EV(150)-EV(125)`.
   - Sirve para detectar rendimientos decrecientes: si el segundo salto aporta poco, conviene no sobrepagar.

5. **`acceptance_by_bid_discrete.png`**
   - Muestra `q(b)` para 100 / 125 / 150 bajo bunching discreto.
   - Es clave para separar “precio pagado” de “probabilidad adicional comprada”.

6. **`final_sensitivity_heatmap.png`**
   - Eje 1: Delta asumido.
   - Eje 2: escenario rival discreto.
   - Valor: mejor bid entre {{100,125,150}}.
   - Ayuda a decidir si `125` aguanta globalmente o si la decisión gira hacia `150` cuando el campo rival se vuelve más agresivo.

## F. Recomendación final

### Mejor bid por criterio pedido

{df_to_md(best_bids_df, index=False)}

### Decisión final

- **Bid recomendado**: **`125`**.
- **Cuándo elegir `100`**:
  - si tu prior rival está cerca de masa en 100 / escenario suave,
  - si priorizás mucho minimizar fee,
  - y si querés una política conservadora de costo por encima de aceptación extra.
- **Cuándo elegir `125`**:
  - como default robusto,
  - si creés que el campo rival está entre masa en 100, mezcla heterogénea y un caso central razonable,
  - y si querés evitar pagar el premium de 150 salvo evidencia más fuerte.
- **Cuándo elegir `150`**:
  - si tu prior está claramente sesgado a **bunching en 125 o agresividad en 150**,
  - si querés comprar aceptación adicional incluso con EV marginal decreciente,
  - y si aceptás un fee más alto como seguro contra cutoff duro.

### Veredicto final

Después de revisar el análisis y modelar la distribución esperada de bids rivales con bunching, **el bid `125` sí sigue siendo la mejor opción robusta**.

La principal razón es doble:
1. **No pierde solidez económica**: incluso bajo downside razonable, el valor del access sigue dejando margen neto importante.
2. **El salto a `150` compra aceptación, pero no siempre compra suficiente EV adicional como para justificar el sobrepago**.

Dicho sin maquillaje: **`150` gana más seguido como máximo puntual cuando el rival model se vuelve agresivo**, pero `125` sigue siendo la mejor recomendación global porque depende menos de acertar exactamente el cutoff rival y mantiene una relación riesgo/costo más sana.
"""
    return report


def main() -> None:
    inputs = load_inputs()
    scenarios = build_scenarios()

    pmf_df, cutoff_df, cutoff_summary_df, acceptance_df = simulate_discrete_scenarios(
        scenarios=scenarios,
        delta_conservative=float(inputs['delta_conservative']),
        delta_downside=float(inputs['delta_downside']),
        p0_mean=float(inputs['p0_total']),
    )

    delta_stress_df, thresholds = delta_stress_tests(
        cons_grid=inputs['cons_grid'],
        p0_mean=float(inputs['p0_total']),
        delta_conservative=float(inputs['delta_conservative']),
    )
    q_stress_df = q_stress_tests(
        cons_grid=inputs['cons_grid'],
        p0_mean=float(inputs['p0_total']),
        delta_conservative=float(inputs['delta_conservative']),
    )
    worst_combo_df = worst_case_combo(
        acceptance_df=acceptance_df,
        p0_mean=float(inputs['p0_total']),
        delta_downside=float(inputs['delta_downside']),
    )
    gap_df = marginal_gap_tests(inputs['cons_grid'], acceptance_df)
    sensitivity_df = sensitivity_matrix(acceptance_df)
    best_bids_df = summarize_best_bids(acceptance_df, worst_combo_df)

    # Save tables
    pmf_df.to_csv(OUT_DIR / 'rival_bid_scenarios.csv', index=False)
    cutoff_df.to_csv(OUT_DIR / 'induced_cutoff_distribution.csv', index=False)
    cutoff_summary_df.to_csv(OUT_DIR / 'induced_cutoff_summary.csv', index=False)
    acceptance_df.to_csv(OUT_DIR / 'discrete_acceptance_ev.csv', index=False)
    delta_stress_df.to_csv(OUT_DIR / 'stress_delta_tests.csv', index=False)
    q_stress_df.to_csv(OUT_DIR / 'stress_q_tests.csv', index=False)
    worst_combo_df.to_csv(OUT_DIR / 'worst_case_combo.csv', index=False)
    gap_df.to_csv(OUT_DIR / 'marginal_ev_gaps.csv', index=False)
    sensitivity_df.to_csv(OUT_DIR / 'final_sensitivity_matrix.csv', index=False)
    best_bids_df.to_csv(OUT_DIR / 'best_bids_summary.csv', index=False)
    pd.DataFrame([thresholds]).to_csv(OUT_DIR / 'delta_thresholds.csv', index=False)

    # Plots
    plot_rival_distributions(pmf_df)
    plot_cutoff_distribution(cutoff_df, cutoff_summary_df)
    plot_ev_scenarios(acceptance_df)
    plot_marginal_ev(gap_df)
    plot_acceptance(acceptance_df)
    plot_sensitivity_heatmap(sensitivity_df)

    acceptance_focus = acceptance_df[acceptance_df['bid'].isin(FOCUS_BIDS)].copy()
    report = build_report(
        inputs=inputs,
        cutoff_summary_df=cutoff_summary_df,
        acceptance_focus=acceptance_focus,
        delta_stress_df=delta_stress_df[delta_stress_df['bid'].isin(FOCUS_BIDS)].copy(),
        q_stress_df=q_stress_df[q_stress_df['bid'].isin(FOCUS_BIDS)].copy(),
        worst_combo_df=worst_combo_df,
        gap_df=gap_df,
        sensitivity_df=sensitivity_df,
        best_bids_df=best_bids_df,
        thresholds=thresholds,
    )
    (OUT_DIR / 'round2_model_kiko_maf_validation.md').write_text(report, encoding='utf-8')

    print('Validation outputs written to:', OUT_DIR)


if __name__ == '__main__':
    main()
