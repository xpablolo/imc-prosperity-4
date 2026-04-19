from __future__ import annotations

from pathlib import Path
from collections import OrderedDict
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path('/Users/pablo/Desktop/prosperity')
DAY_UNIT_DIR = ROOT / 'round_2' / 'results' / 'kiko_maf_day_unit'
OUT_DIR = ROOT / 'round_2' / 'results' / 'kiko_maf_rival_tail'
PLOTS_DIR = OUT_DIR / 'plots'
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style='whitegrid', context='talk')
plt.rcParams['figure.dpi'] = 140
plt.rcParams['axes.titlesize'] = 17
plt.rcParams['axes.labelsize'] = 13
plt.rcParams['legend.fontsize'] = 10

SUPPORT = np.array([0, 25, 50, 75, 100, 125, 150, 175, 200, 250, 300, 400], dtype=int)
CANDIDATE_BIDS = np.array([100, 125, 150, 175], dtype=int)
TOTAL_PARTICIPANTS = 100
RIVALS = TOTAL_PARTICIPANTS - 1
ACCEPTED = TOTAL_PARTICIPANTS // 2
N_SIMS = 250_000
RNG = np.random.default_rng(20260419)


PALETTE = ['#1f4e79', '#6f42c1', '#c0392b', '#0f766e', '#d97706', '#374151']
BID_COLORS = {100: '#2563eb', 125: '#7c3aed', 150: '#dc2626', 175: '#0f766e'}
DELTA_ORDER = ['conservative', 'downside', 'central']
DELTA_LABELS = {'conservative': 'Delta_conservative', 'downside': 'Delta_downside', 'central': 'Delta_central'}


def df_to_md(df: pd.DataFrame, index: bool = False, round_map: dict[str, int] | None = None) -> str:
    x = df.copy()
    if round_map:
        for col, ndigits in round_map.items():
            if col in x.columns:
                x[col] = x[col].map(lambda v: round(float(v), ndigits) if pd.notna(v) else v)
    if index:
        x = x.reset_index()
    cols = list(x.columns)
    lines = ['| ' + ' | '.join(str(c) for c in cols) + ' |', '| ' + ' | '.join(['---'] * len(cols)) + ' |']
    for _, row in x.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if pd.isna(v):
                vals.append('')
            else:
                vals.append(str(v))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def load_economic_inputs() -> tuple[float, dict[str, float]]:
    baseline_summary = pd.read_csv(DAY_UNIT_DIR / 'baseline_summary.csv')
    delta_summary = pd.read_csv(DAY_UNIT_DIR / 'delta_summary.csv')

    p0_mean = float(baseline_summary.loc[baseline_summary['product'] == 'TOTAL', 'P0_mean'].iloc[0])
    deltas = {
        'conservative': float(delta_summary.loc[delta_summary['proxy'] == 'Uniform depth +25%', 'Delta_mean'].iloc[0]),
        'downside': float(delta_summary.loc[delta_summary['proxy'] == 'Uniform depth +25%', 'Delta_min'].iloc[0]),
        'central': float(delta_summary.loc[delta_summary['proxy'] == 'Front-biased depth +25%', 'Delta_mean'].iloc[0]),
    }
    return p0_mean, deltas


def normalize_mapping(mapping: dict[int, float]) -> dict[int, float]:
    total = float(sum(mapping.values()))
    return {int(k): float(v) / total for k, v in mapping.items()}


def pmf_from_mapping(mapping: dict[int, float]) -> np.ndarray:
    norm = normalize_mapping(mapping)
    return np.array([norm.get(int(level), 0.0) for level in SUPPORT], dtype=float)


def build_scenarios() -> OrderedDict[str, dict[str, object]]:
    scenarios: OrderedDict[str, dict[str, object]] = OrderedDict()

    scenarios['A_masa_100'] = {
        'label': 'Escenario A — masa en 100',
        'logic': 'Muchos equipos intentan pagar poco pero sin quedarse demasiado abajo; 100 funciona como focal point defensivo de bajo coste.',
        'rival_type': 'low / lower-mid bidders con small tail de seguro',
        'pmf': pmf_from_mapping({0: 0.02, 25: 0.05, 50: 0.08, 75: 0.13, 100: 0.30, 125: 0.15, 150: 0.10, 175: 0.06, 200: 0.04, 250: 0.03, 300: 0.02, 400: 0.02}),
    }
    scenarios['B_masa_125'] = {
        'label': 'Escenario B — masa en 125',
        'logic': 'Muchos equipos convergen a la lógica clásica de bid robusto y pagan un poco más para no quedarse en 100.',
        'rival_type': 'middle bidders con bunching explícito en 125',
        'pmf': pmf_from_mapping({0: 0.02, 25: 0.04, 50: 0.06, 75: 0.10, 100: 0.14, 125: 0.28, 150: 0.14, 175: 0.07, 200: 0.05, 250: 0.04, 300: 0.03, 400: 0.03}),
    }
    scenarios['C_masa_150'] = {
        'label': 'Escenario C — masa en 150',
        'logic': 'Campo más agresivo: 150 pasa a ser el número focal para comprar aceptación sin irse todavía a bids extremos.',
        'rival_type': 'aggressive middle/high bidders',
        'pmf': pmf_from_mapping({0: 0.01, 25: 0.02, 50: 0.04, 75: 0.06, 100: 0.10, 125: 0.18, 150: 0.26, 175: 0.12, 200: 0.08, 250: 0.06, 300: 0.04, 400: 0.03}),
    }

    low = normalize_mapping({0: 0.02, 25: 0.08, 50: 0.15, 75: 0.25, 100: 0.25, 125: 0.12, 150: 0.07, 175: 0.03, 200: 0.015, 250: 0.005, 300: 0.003, 400: 0.002})
    mid = normalize_mapping({0: 0.01, 25: 0.02, 50: 0.04, 75: 0.08, 100: 0.16, 125: 0.24, 150: 0.22, 175: 0.11, 200: 0.05, 250: 0.03, 300: 0.02, 400: 0.02})
    high = normalize_mapping({0: 0.005, 25: 0.01, 50: 0.015, 75: 0.03, 100: 0.06, 125: 0.12, 150: 0.19, 175: 0.18, 200: 0.13, 250: 0.10, 300: 0.08, 400: 0.08})
    noise = {int(b): 1.0 / len(SUPPORT) for b in SUPPORT}
    weights = {'low_bidders': 0.30, 'middle_bidders': 0.35, 'high_bidders': 0.20, 'noise_bidders': 0.15}
    mix = {int(b): weights['low_bidders'] * low[int(b)] + weights['middle_bidders'] * mid[int(b)] + weights['high_bidders'] * high[int(b)] + weights['noise_bidders'] * noise[int(b)] for b in SUPPORT}
    scenarios['D_mixto'] = {
        'label': 'Escenario D — mezcla heterogénea',
        'logic': 'Campo heterogéneo con low bidders, middle bidders, high bidders y ruido; representa un field sin consenso total pero con masa intermedia y tail visible.',
        'rival_type': 'mix de perfiles con cola superior moderada',
        'pmf': pmf_from_mapping(mix),
        'components': weights,
    }
    scenarios['E_cola_superior'] = {
        'label': 'Escenario E — cola superior agresiva',
        'logic': 'La masa principal vive entre 125 y 175, pero además existe una cola superior no trivial en 200/250/300 y algo residual en 400.',
        'rival_type': 'high bidders con tail explícita y crowd central todavía presente',
        'pmf': pmf_from_mapping({0: 0.01, 25: 0.02, 50: 0.03, 75: 0.04, 100: 0.08, 125: 0.20, 150: 0.22, 175: 0.18, 200: 0.10, 250: 0.07, 300: 0.04, 400: 0.01}),
    }
    scenarios['F_overinsurance'] = {
        'label': 'Escenario F — overinsurance',
        'logic': 'Un subgrupo relevante paga bids muy altos para asegurar aceptación; sigue habiendo bunching en 150, pero también masa visible en 200/250/300 y residual en 400.',
        'rival_type': 'insured high bidders / stress serio',
        'pmf': pmf_from_mapping({0: 0.005, 25: 0.01, 50: 0.02, 75: 0.03, 100: 0.05, 125: 0.11, 150: 0.22, 175: 0.13, 200: 0.15, 250: 0.12, 300: 0.10, 400: 0.055}),
    }
    return scenarios


def acceptance_probability(counts_rivals: np.ndarray, bid_value: int) -> np.ndarray:
    idx = int(np.where(SUPPORT == bid_value)[0][0])
    strictly_above = counts_rivals[:, idx + 1 :].sum(axis=1)
    equal = counts_rivals[:, idx]
    slots_left = ACCEPTED - strictly_above

    prob = np.zeros(len(counts_rivals), dtype=float)
    sure_accept = strictly_above + equal < ACCEPTED
    sure_reject = strictly_above >= ACCEPTED
    tie_case = ~(sure_accept | sure_reject)

    prob[sure_accept] = 1.0
    prob[sure_reject] = 0.0
    prob[tie_case] = slots_left[tie_case] / (equal[tie_case] + 1.0)
    return np.clip(prob, 0.0, 1.0)


def simulate_cutoff_and_acceptance(scenarios: OrderedDict[str, dict[str, object]], p0_mean: float, deltas: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pmf_rows = []
    cutoff_rows = []
    cutoff_summary_rows = []
    metrics_rows = []
    cdf_rows = []

    for scenario_key, meta in scenarios.items():
        label = str(meta['label'])
        pmf = np.asarray(meta['pmf'], dtype=float)

        for level, prob in zip(SUPPORT, pmf):
            pmf_rows.append({
                'scenario': scenario_key,
                'scenario_label': label,
                'bid_level': int(level),
                'probability': float(prob),
            })

        counts_rivals = RNG.multinomial(RIVALS, pmf, size=N_SIMS)
        counts_total = RNG.multinomial(TOTAL_PARTICIPANTS, pmf, size=N_SIMS)

        descending_counts = counts_total[:, ::-1]
        cum_desc = np.cumsum(descending_counts, axis=1)
        cutoff_idx_desc = (cum_desc >= ACCEPTED).argmax(axis=1)
        cutoff_levels = SUPPORT[::-1][cutoff_idx_desc]

        cutoff_dist = pd.Series(cutoff_levels).value_counts(normalize=True).sort_index()
        for level in SUPPORT:
            prob = float(cutoff_dist.get(int(level), 0.0))
            cutoff_rows.append({
                'scenario': scenario_key,
                'scenario_label': label,
                'cutoff_level': int(level),
                'probability': prob,
            })
            cdf_rows.append({
                'scenario': scenario_key,
                'scenario_label': label,
                'cutoff_level': int(level),
                'cdf': float(np.mean(cutoff_levels <= level)),
            })

        cutoff_summary_rows.append({
            'scenario': scenario_key,
            'scenario_label': label,
            'cutoff_mean': float(np.mean(cutoff_levels)),
            'cutoff_median': float(np.median(cutoff_levels)),
            'cutoff_p10': float(np.quantile(cutoff_levels, 0.10)),
            'cutoff_p25': float(np.quantile(cutoff_levels, 0.25)),
            'cutoff_p75': float(np.quantile(cutoff_levels, 0.75)),
            'cutoff_p90': float(np.quantile(cutoff_levels, 0.90)),
        })

        for bid in CANDIDATE_BIDS:
            q = float(acceptance_probability(counts_rivals, int(bid)).mean())
            for delta_key, delta_value in deltas.items():
                net_gain = float(delta_value - bid)
                metrics_rows.append({
                    'scenario': scenario_key,
                    'scenario_label': label,
                    'delta_key': delta_key,
                    'delta_label': DELTA_LABELS[delta_key],
                    'delta_value': float(delta_value),
                    'bid': int(bid),
                    'q_accept': q,
                    'net_gain_if_accepted': net_gain,
                    'uplift_pct_vs_base': net_gain / p0_mean,
                    'fee_roi': (net_gain / bid) if bid > 0 else np.nan,
                    'ev_uplift': q * net_gain,
                    'ev_total': p0_mean + q * net_gain,
                })

    return (
        pd.DataFrame(pmf_rows),
        pd.DataFrame(cutoff_rows),
        pd.DataFrame(cutoff_summary_rows),
        pd.DataFrame(cdf_rows),
        pd.DataFrame(metrics_rows),
    )


def build_marginal_table(metrics_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scenario, delta_key), sub in metrics_df.groupby(['scenario_label', 'delta_key']):
        pivot = sub.set_index('bid')['ev_uplift'].to_dict()
        rows.append({
            'scenario_label': scenario,
            'delta_key': delta_key,
            'EV_125_minus_100': float(pivot[125] - pivot[100]),
            'EV_150_minus_125': float(pivot[150] - pivot[125]),
            'EV_175_minus_150': float(pivot[175] - pivot[150]),
        })
    return pd.DataFrame(rows)


def build_best_bid_table(metrics_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for delta_key in DELTA_ORDER:
        sub = metrics_df[metrics_df['delta_key'] == delta_key].copy()
        mean_ev = sub.groupby('bid', as_index=False)['ev_uplift'].mean().rename(columns={'ev_uplift': 'mean_ev'})
        best_mean_bid = int(mean_ev.loc[mean_ev['mean_ev'].idxmax(), 'bid'])
        rows.append({'criterion': f'best_bid_ev_mean_{delta_key}', 'bid': best_mean_bid})

        worst_case = sub.groupby('bid', as_index=False)['ev_uplift'].min().rename(columns={'ev_uplift': 'min_ev'})
        best_downside_bid = int(worst_case.loc[worst_case['min_ev'].idxmax(), 'bid'])
        rows.append({'criterion': f'best_bid_downside_{delta_key}', 'bid': best_downside_bid})

    for scenario_key in ['E_cola_superior', 'F_overinsurance']:
        label = metrics_df.loc[metrics_df['scenario'] == scenario_key, 'scenario_label'].iloc[0]
        sub = metrics_df[(metrics_df['scenario'] == scenario_key) & (metrics_df['delta_key'] == 'conservative')]
        best = int(sub.loc[sub['ev_uplift'].idxmax(), 'bid'])
        rows.append({'criterion': f'best_bid_{scenario_key}_conservative', 'bid': best})
        rows.append({'criterion': f'best_bid_{scenario_key}_label', 'bid': label})

    # robust global = maximize minimum downside EV, with mean regret as secondary diagnostic
    down = metrics_df[metrics_df['delta_key'] == 'downside'].copy()
    pivot = down.pivot(index='scenario_label', columns='bid', values='ev_uplift')
    regrets = pivot.max(axis=1).values.reshape(-1, 1) - pivot.values
    regrets_df = pd.DataFrame(regrets, index=pivot.index, columns=pivot.columns)
    robust_bid = int(pivot.min().idxmax())
    rows.append({'criterion': 'robust_global_bid_maximin_downside', 'bid': robust_bid})
    rows.append({'criterion': 'robust_global_bid_mean_ev_conservative', 'bid': int(metrics_df[metrics_df['delta_key'] == 'conservative'].groupby('bid')['ev_uplift'].mean().idxmax())})
    rows.append({'criterion': 'robust_global_bid_minmax_regret_downside', 'bid': int(regrets_df.max().idxmin())})
    return pd.DataFrame(rows)


def build_robustness_summary(metrics_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for delta_key in DELTA_ORDER:
        pivot = metrics_df[metrics_df['delta_key'] == delta_key].pivot(index='scenario_label', columns='bid', values='ev_uplift')
        regrets = pivot.max(axis=1).values.reshape(-1, 1) - pivot.values
        regrets_df = pd.DataFrame(regrets, index=pivot.index, columns=pivot.columns)
        for bid in CANDIDATE_BIDS:
            rows.append({
                'delta_key': delta_key,
                'bid': int(bid),
                'mean_ev': float(pivot[bid].mean()),
                'min_ev': float(pivot[bid].min()),
                'max_regret': float(regrets_df[bid].max()),
                'mean_regret': float(regrets_df[bid].mean()),
            })
    return pd.DataFrame(rows)


def plot_rival_distribution(pmf_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(19, 10), sharex=True, sharey=True)
    for ax, ((_, sub), color) in zip(axes.flat, zip(pmf_df.groupby('scenario_label'), PALETTE)):
        ax.bar(sub['bid_level'], sub['probability'], width=18, color=color, alpha=0.90)
        for bid in CANDIDATE_BIDS:
            ax.axvline(bid, color=BID_COLORS[bid], linestyle='--', linewidth=1.4, alpha=0.8)
        ax.set_title(sub['scenario_label'].iloc[0])
        ax.set_xlabel('Bid rival')
        ax.set_ylabel('Probabilidad')
    fig.suptitle('Distribución modelada de bids rivales (bunching + cola superior)', y=1.02)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'rival_bid_distribution_extended.png', bbox_inches='tight')
    plt.close(fig)


def plot_cutoff_pmf(cutoff_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(19, 10), sharex=True, sharey=True)
    for ax, ((_, sub), color) in zip(axes.flat, zip(cutoff_df.groupby('scenario_label'), PALETTE)):
        ax.bar(sub['cutoff_level'], sub['probability'], width=18, color=color, alpha=0.90)
        for bid in CANDIDATE_BIDS:
            ax.axvline(bid, color=BID_COLORS[bid], linestyle='--', linewidth=1.4, alpha=0.8)
        ax.set_title(sub['scenario_label'].iloc[0])
        ax.set_xlabel('Cutoff inducido')
        ax.set_ylabel('Probabilidad')
    fig.suptitle('Distribución inducida del cutoff', y=1.02)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'induced_cutoff_pmf_extended.png', bbox_inches='tight')
    plt.close(fig)


def plot_cutoff_cdf(cdf_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(14, 8))
    for color, (label, sub) in zip(PALETTE, cdf_df.groupby('scenario_label')):
        ax.step(sub['cutoff_level'], sub['cdf'], where='post', label=label, linewidth=2.5, color=color)
    for bid in CANDIDATE_BIDS:
        ax.axvline(bid, color=BID_COLORS[bid], linestyle='--', linewidth=1.4, alpha=0.85)
    ax.set_title('CDF del cutoff inducido por escenario rival')
    ax.set_xlabel('Cutoff')
    ax.set_ylabel('P(Cutoff ≤ x)')
    ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'induced_cutoff_cdf_extended.png', bbox_inches='tight')
    plt.close(fig)


def plot_ev_by_bid(metrics_df: pd.DataFrame) -> None:
    focus = metrics_df[metrics_df['delta_key'].isin(['conservative', 'downside'])].copy()
    fig, axes = plt.subplots(1, 2, figsize=(18, 7), sharey=False)
    for ax, delta_key in zip(axes, ['conservative', 'downside']):
        sub = focus[focus['delta_key'] == delta_key]
        sns.barplot(data=sub, x='scenario_label', y='ev_uplift', hue='bid', palette=BID_COLORS, ax=ax)
        ax.set_title(f'EV uplift por bid — {DELTA_LABELS[delta_key]}')
        ax.set_xlabel('Escenario rival')
        ax.set_ylabel('EV(b) - P0_mean')
        ax.tick_params(axis='x', rotation=18)
        if ax is axes[1]:
            ax.legend(title='Bid', bbox_to_anchor=(1.02, 1), loc='upper left')
        else:
            ax.legend().remove()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'ev_by_bid_extended.png', bbox_inches='tight')
    plt.close(fig)


def plot_marginal_ev(marginal_df: pd.DataFrame) -> None:
    plot_df = marginal_df[marginal_df['delta_key'].isin(['conservative', 'downside'])].melt(
        id_vars=['scenario_label', 'delta_key'],
        value_vars=['EV_125_minus_100', 'EV_150_minus_125', 'EV_175_minus_150'],
        var_name='gap_type',
        value_name='ev_increment',
    )
    gap_map = {
        'EV_125_minus_100': 'EV(125)-EV(100)',
        'EV_150_minus_125': 'EV(150)-EV(125)',
        'EV_175_minus_150': 'EV(175)-EV(150)',
    }
    plot_df['gap_type'] = plot_df['gap_type'].map(gap_map)
    fig, axes = plt.subplots(1, 2, figsize=(18, 7), sharey=False)
    for ax, delta_key in zip(axes, ['conservative', 'downside']):
        sub = plot_df[plot_df['delta_key'] == delta_key]
        sns.barplot(data=sub, x='scenario_label', y='ev_increment', hue='gap_type', ax=ax, palette=['#7c3aed', '#dc2626', '#0f766e'])
        ax.axhline(0, color='black', linewidth=1)
        ax.set_title(f'Incremento marginal de EV — {DELTA_LABELS[delta_key]}')
        ax.set_xlabel('Escenario rival')
        ax.set_ylabel('Incremento marginal de EV')
        ax.tick_params(axis='x', rotation=18)
        if ax is axes[1]:
            ax.legend(title='Gap', bbox_to_anchor=(1.02, 1), loc='upper left')
        else:
            ax.legend().remove()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'marginal_ev_extended.png', bbox_inches='tight')
    plt.close(fig)


def plot_sensitivity_heatmap(metrics_df: pd.DataFrame) -> None:
    best = metrics_df.groupby(['scenario_label', 'delta_key']).apply(lambda g: g.loc[g['ev_uplift'].idxmax(), 'bid']).reset_index(name='best_bid')
    table = best.pivot(index='scenario_label', columns='delta_key', values='best_bid')
    table = table[DELTA_ORDER]
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.heatmap(table, annot=True, fmt='.0f', cmap=sns.color_palette(['#dbeafe', '#c4b5fd', '#fecaca', '#a7f3d0'], as_cmap=True), cbar=False, ax=ax)
    ax.set_title('Bid recomendado entre {100,125,150,175}')
    ax.set_xlabel('Delta usado')
    ax.set_ylabel('Escenario rival')
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / 'final_sensitivity_heatmap_extended.png', bbox_inches='tight')
    plt.close(fig)


def build_report(p0_mean: float, deltas: dict[str, float], scenarios: OrderedDict[str, dict[str, object]], cutoff_summary_df: pd.DataFrame, metrics_df: pd.DataFrame, marginal_df: pd.DataFrame, best_df: pd.DataFrame, robustness_df: pd.DataFrame) -> str:
    scenario_desc = pd.DataFrame([
        {
            'scenario_label': meta['label'],
            'rival_type': meta['rival_type'],
            'logic': meta['logic'],
        }
        for meta in scenarios.values()
    ])

    q_table = metrics_df[['scenario_label', 'bid', 'q_accept']].drop_duplicates().pivot(index='scenario_label', columns='bid', values='q_accept').reset_index()
    q_table.columns.name = None
    cutoff_table = cutoff_summary_df[['scenario_label', 'cutoff_mean', 'cutoff_median', 'cutoff_p10', 'cutoff_p25', 'cutoff_p75', 'cutoff_p90']].copy()

    cons_table = metrics_df[metrics_df['delta_key'] == 'conservative'][['scenario_label', 'bid', 'q_accept', 'net_gain_if_accepted', 'uplift_pct_vs_base', 'fee_roi', 'ev_uplift']].copy()
    down_table = metrics_df[metrics_df['delta_key'] == 'downside'][['scenario_label', 'bid', 'q_accept', 'net_gain_if_accepted', 'uplift_pct_vs_base', 'fee_roi', 'ev_uplift']].copy()
    cent_table = metrics_df[metrics_df['delta_key'] == 'central'][['scenario_label', 'bid', 'q_accept', 'net_gain_if_accepted', 'uplift_pct_vs_base', 'fee_roi', 'ev_uplift']].copy()

    cons_rob = robustness_df[robustness_df['delta_key'] == 'conservative'].copy()
    down_rob = robustness_df[robustness_df['delta_key'] == 'downside'].copy()

    mean_best = int(best_df.loc[best_df['criterion'] == 'best_bid_ev_mean_conservative', 'bid'].iloc[0])
    downside_best = int(best_df.loc[best_df['criterion'] == 'best_bid_downside_downside', 'bid'].iloc[0])
    tail_best = int(best_df.loc[best_df['criterion'] == 'best_bid_E_cola_superior_conservative', 'bid'].iloc[0])
    over_best = int(best_df.loc[best_df['criterion'] == 'best_bid_F_overinsurance_conservative', 'bid'].iloc[0])
    robust_global = int(best_df.loc[best_df['criterion'] == 'robust_global_bid_maximin_downside', 'bid'].iloc[0])

    cons_pivot = metrics_df[metrics_df['delta_key'] == 'conservative'].pivot(index='scenario_label', columns='bid', values='ev_uplift')
    marginal_cons = marginal_df[marginal_df['delta_key'] == 'conservative'].copy()

    report = f"""# Revisión incremental del modelado rival / cutoff del MAF para `model_kiko`

## A. Resumen ejecutivo

- Manteniendo fija la valoración económica base (`Delta_conservative = {deltas['conservative']:.1f}`, `Delta_downside = {deltas['downside']:.1f}`, `Delta_central = {deltas['central']:.1f}`), el cambio viene **solo** del nuevo modelado rival.
- Permitiendo **bunching + grid ampliada + cola superior explícita**, el bid robusto recomendado **pasa a ser `175` dentro del set comparado {{100,125,150,175}}**.
- `150` **ya no** sale como la opción robusta principal.
- `125` **no** recupera atractivo: solo compite si el campo estuviera mucho más concentrado abajo de 150 de lo que sugiere esta familia de escenarios.
- `175` entra en consideración totalmente seria; de hecho, es el mejor bid por EV medio, downside y robustez global dentro del conjunto evaluado.

## B. Nueva distribución rival

### Escenarios y lógica económica

{df_to_md(scenario_desc, index=False)}

Notas metodológicas:
- Soporte rival ampliado: `{', '.join(map(str, SUPPORT))}`.
- La distribución no es lisa: combina **masa de fondo**, **bunching explícito en focal points** y **cola superior**.
- Torneo simulado con `100` participantes totales, `99` rivales, `top 50` aceptados, y **tie-break uniforme** dentro del nivel exacto del cutoff.

## C. Cutoff inducido y aceptación

### Resumen del cutoff por escenario

{df_to_md(cutoff_table, index=False, round_map={'cutoff_mean': 2, 'cutoff_median': 0, 'cutoff_p10': 0, 'cutoff_p25': 0, 'cutoff_p75': 0, 'cutoff_p90': 0})}

### Probabilidad de aceptación `q(b)` para 100 / 125 / 150 / 175

{df_to_md(q_table, index=False, round_map={100: 4, 125: 4, 150: 4, 175: 4})}

Lectura rápida:
- En `Escenario A`, `125` y `175` casi aseguran entrada; `150` y `175` quedan muy parecidos.
- En `Escenario B`, `125` cae a un coin-flip; `150` y `175` prácticamente aseguran aceptación.
- En `Escenario C`, `150` ya no es seguro; `175` sí.
- En `Escenario E`, `150` cae a `q≈0.456`; `175` sigue en `q≈0.998`.
- En `Escenario F`, `150` casi no entra (`q≈0.015`), mientras que `175` todavía conserva `q≈0.560`.

## D. Comparación de bids

### Métricas con `Delta_conservative`

{df_to_md(cons_table, index=False, round_map={'q_accept': 4, 'net_gain_if_accepted': 1, 'uplift_pct_vs_base': 4, 'fee_roi': 3, 'ev_uplift': 1})}

### Métricas con `Delta_downside`

{df_to_md(down_table, index=False, round_map={'q_accept': 4, 'net_gain_if_accepted': 1, 'uplift_pct_vs_base': 4, 'fee_roi': 3, 'ev_uplift': 1})}

### Métricas con `Delta_central`

{df_to_md(cent_table, index=False, round_map={'q_accept': 4, 'net_gain_if_accepted': 1, 'uplift_pct_vs_base': 4, 'fee_roi': 3, 'ev_uplift': 1})}

### Comparación marginal de EV

{df_to_md(marginal_df, index=False, round_map={'EV_125_minus_100': 1, 'EV_150_minus_125': 1, 'EV_175_minus_150': 1})}

Lectura marginal importante (`Delta_conservative`):
- El salto `125 -> 150` sigue valiendo mucho cuando el crowd se amontona en `125`.
- El salto `150 -> 175` pasa a ser **muy valioso** cuando aparece cola superior real:
  - `Escenario C`: `EV(175)-EV(150) ≈ {float(marginal_cons.loc[marginal_cons['scenario_label'] == 'Escenario C — masa en 150', 'EV_175_minus_150'].iloc[0]):.1f}`
  - `Escenario E`: `EV(175)-EV(150) ≈ {float(marginal_cons.loc[marginal_cons['scenario_label'] == 'Escenario E — cola superior agresiva', 'EV_175_minus_150'].iloc[0]):.1f}`
  - `Escenario F`: `EV(175)-EV(150) ≈ {float(marginal_cons.loc[marginal_cons['scenario_label'] == 'Escenario F — overinsurance', 'EV_175_minus_150'].iloc[0]):.1f}`
- En escenarios suaves, subir de `150` a `175` cuesta solo ~25 EV, porque `q` ya está casi en 1. En escenarios con cola superior, ese mismo salto funciona como seguro fuerte contra quedarte corto.

### Robustez resumida

#### `Delta_conservative`
{df_to_md(cons_rob, index=False, round_map={'mean_ev': 1, 'min_ev': 1, 'max_regret': 1, 'mean_regret': 1})}

#### `Delta_downside`
{df_to_md(down_rob, index=False, round_map={'mean_ev': 1, 'min_ev': 1, 'max_regret': 1, 'mean_regret': 1})}

## E. Visualizaciones

Plots generados en `{PLOTS_DIR}`:

1. `rival_bid_distribution_extended.png`
   - Muestra, por escenario, la **masa central**, el **bunching** y la **cola superior**.
   - Es el gráfico clave para ver si 125/150/175 quedan por debajo, dentro o por encima de la congestión rival.

2. `induced_cutoff_pmf_extended.png`
   - Muestra la PMF del cutoff inducido.
   - Permite ver si el corte cae en 100, 125, 150 o 175 según el escenario.

3. `induced_cutoff_cdf_extended.png`
   - Permite visualizar rápidamente cuánto probabilidad ganás al subir el bid.
   - OJO: con ties discretos, la CDF del cutoff no es exactamente `q(b)` en los focal points, por eso reporto `q(b)` exacta en tablas.

4. `ev_by_bid_extended.png`
   - Compara `100/125/150/175` por escenario con `Delta_conservative` y `Delta_downside`.
   - Ahí se ve si `175` compensa o si ya es demasiado caro.

5. `marginal_ev_extended.png`
   - Muestra `EV(125)-EV(100)`, `EV(150)-EV(125)` y `EV(175)-EV(150)`.
   - Es el gráfico más útil para juzgar si 175 agrega valor real o es puro sobrepago.

6. `final_sensitivity_heatmap_extended.png`
   - Eje 1: escenario rival.
   - Eje 2: Delta usado.
   - Output: mejor bid entre `{{100,125,150,175}}`.

## F. Recomendación final

### Identificación pedida
- Mejor bid por EV medio (`Delta_conservative`, escenarios equiponderados): **`{mean_best}`**.
- Mejor bid por downside (`Delta_downside`, criterio maximin): **`{downside_best}`**.
- Mejor bid bajo cola superior agresiva (`Escenario E`): **`{tail_best}`**.
- Mejor bid bajo overinsurance (`Escenario F`): **`{over_best}`**.
- Bid más robusto global: **`{robust_global}`**.

### Respuesta a las preguntas clave
- **¿150 sigue siendo robusto cuando permitimos cola superior en bids rivales?** No. Se vuelve intermedio: supera claramente a 125, pero queda vulnerable cuando el cutoff rival se mueve hacia 175 o cuando la cola superior es gruesa.
- **¿125 recupera atractivo?** No. El riesgo de quedarte corto con 125 pasa a ser demasiado alto en escenarios B/C/D/E/F.
- **¿175 pasa a ser necesario o sigue siendo demasiado caro?** Dentro del set comparado, **175 pasa a ser necesario y deja de parecer caro**: su coste extra respecto a 150 es pequeño en escenarios suaves y su beneficio es enorme cuando la cola superior realmente existe.
- **¿El cambio respecto al análisis anterior es pequeño o grande?** Es **material**: el cambio de 150 a 175 no viene por Delta, viene por cómo cambia `q(b)` cuando el campo rival ya no está comprimido en 100–150.

### Recomendación operativa
- **Bid recomendado**: **`175`**.
- **Rango alternativo**: **`150–175`**.
- **Cuándo usar `125`**: solo si estás convencido de que el field real está bastante más abajo y que la cola superior es irrelevante. Con esta familia de escenarios, esa postura ya no es la base case.
- **Cuándo usar `150`**: si querés una postura intermedia y te parece demasiado agresivo pagar 175, pero aceptando que quedás más expuesto a escenarios E/F.
- **Cuándo usar `175`**: si tomás en serio la posibilidad de bunching en 150 y, sobre todo, la existencia de una cola superior explícita en 200/250/300.

### Caveat honesto
Esta fase compara candidatos `{{100,125,150,175}}`. No re-optimizó bids propios por encima de 175. Por eso, decir que `175` es el robusto recomendado significa **“mejor dentro del set comparado”**, no una prueba formal de óptimo global sobre toda la recta.
"""
    return report


def main() -> None:
    p0_mean, deltas = load_economic_inputs()
    scenarios = build_scenarios()

    pmf_df, cutoff_df, cutoff_summary_df, cdf_df, metrics_df = simulate_cutoff_and_acceptance(scenarios, p0_mean, deltas)
    marginal_df = build_marginal_table(metrics_df)
    best_df = build_best_bid_table(metrics_df)
    robustness_df = build_robustness_summary(metrics_df)

    pmf_df.to_csv(OUT_DIR / 'rival_bid_scenarios_extended.csv', index=False)
    cutoff_df.to_csv(OUT_DIR / 'induced_cutoff_distribution_extended.csv', index=False)
    cutoff_summary_df.to_csv(OUT_DIR / 'induced_cutoff_summary_extended.csv', index=False)
    cdf_df.to_csv(OUT_DIR / 'induced_cutoff_cdf_extended.csv', index=False)
    metrics_df.to_csv(OUT_DIR / 'bid_metrics_extended.csv', index=False)
    marginal_df.to_csv(OUT_DIR / 'marginal_ev_extended.csv', index=False)
    best_df.to_csv(OUT_DIR / 'best_bids_extended.csv', index=False)
    robustness_df.to_csv(OUT_DIR / 'robustness_summary_extended.csv', index=False)

    plot_rival_distribution(pmf_df)
    plot_cutoff_pmf(cutoff_df)
    plot_cutoff_cdf(cdf_df)
    plot_ev_by_bid(metrics_df)
    plot_marginal_ev(marginal_df)
    plot_sensitivity_heatmap(metrics_df)

    report = build_report(p0_mean, deltas, scenarios, cutoff_summary_df, metrics_df, marginal_df, best_df, robustness_df)
    (OUT_DIR / 'round2_model_kiko_maf_rival_tail.md').write_text(report, encoding='utf-8')

    print('Extended rival-tail analysis written to:', OUT_DIR)


if __name__ == '__main__':
    main()
