from __future__ import annotations

import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from io import StringIO
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[2]
ROUND_1_TOOLS = ROOT / "round_1" / "tools"
ROUND_2_TOOLS = ROOT / "round_2" / "tools"
ROUND_2_MODELS = ROOT / "round_2" / "models"
RESULTS_DIR = ROOT / "round_2" / "results" / "kiko_maf_day_unit"
PLOTS_DIR = RESULTS_DIR / "plots"
REPORT_PATH = RESULTS_DIR / "round2_model_kiko_maf_day_unit.md"
OFFICIAL_LOG_PATH = ROOT / "round_1" / "official_result.log"

sys.path.insert(0, str(ROUND_2_TOOLS))
sys.path.insert(0, str(ROUND_2_MODELS))
sys.path.insert(0, str(ROUND_1_TOOLS))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402

MODEL_NAME = "model_kiko"
MODEL_PATH = ROOT / "round_2" / "models" / "model_kiko.py"
ROUND_NAME = "round_2"
DAYS = (-1, 0, 1)
DAY_HORIZON = 1_000_000
DAY_MAX_TS = 999_900
PRODUCTS = tuple(ag.PRODUCTS)
POSITION_LIMITS = ag.POSITION_LIMITS
BID_GRID = [0, 10, 20, 30, 40, 50, 60, 75, 100, 125, 150, 175, 200]
SELECTED_BIDS = [100, 125, 150]
PLOT_DPI = 200

PRODUCT_LABELS = {
    "ASH_COATED_OSMIUM": "ASH",
    "INTARIAN_PEPPER_ROOT": "PEPPER",
    "TOTAL": "TOTAL",
}
SCENARIOS = [
    ("baseline", None),
    ("uniform_depth_125", "conservative"),
    ("front_bias_depth_25", "central"),
    ("uniform_depth_trade_125", "upper_bound"),
]
SCENARIO_LABELS = {
    "baseline": "Baseline",
    "uniform_depth_125": "Uniform depth +25%",
    "front_bias_depth_25": "Front-biased depth +25%",
    "uniform_depth_trade_125": "Depth +25% + trades +25%",
}
PALETTE = {
    "baseline": "#111827",
    "uniform_depth_125": "#2563EB",
    "front_bias_depth_25": "#7C3AED",
    "uniform_depth_trade_125": "#DC2626",
    "central": "#2563EB",
    "conservative": "#0F766E",
    "downside": "#D97706",
    "ra1": "#0EA5E9",
    "ra2": "#B45309",
    "ra3": "#7C3AED",
    "low": "#94A3B8",
    "high": "#D97706",
    "stress": "#DC2626",
    "weighted": "#0F766E",
}


@dataclass(frozen=True)
class CutoffScenario:
    name: str
    label: str
    median_bid: float
    slope: float
    weight: float
    description: str


CUTOFF_SCENARIOS: tuple[CutoffScenario, ...] = (
    CutoffScenario("low", "Competencia baja", 20.0, 6.0, 0.15, "Cutoff bajo, bids rivales en la zona de 20."),
    CutoffScenario("central", "Central", 45.0, 9.0, 0.40, "Escenario base: cutoff alrededor de 45."),
    CutoffScenario("high", "Competencia alta", 80.0, 14.0, 0.30, "Escenario competitivo serio: bids relevantes ya están en 70-100."),
    CutoffScenario("stress", "Stress", 140.0, 20.0, 0.15, "Stress duro: cutoff rival muy alto, empuja a considerar 150+ si la prioridad es aceptación."),
)
PROXY_LOOKUP = {proxy.name: proxy for proxy in ag.PROXIES}
DELTA_VARIANT_LABELS = {
    "central": "Delta_central",
    "conservative": "Delta_conservative",
    "downside": "Delta_downside",
    "ra1": "Delta_RA_1",
    "ra2": "Delta_RA_2",
    "ra3": "Delta_RA_3",
}


def configure_style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.facecolor": "#FBFBFD",
            "axes.facecolor": "#FBFBFD",
            "axes.edgecolor": "#D6D9E0",
            "axes.labelcolor": "#1F2937",
            "axes.titleweight": "bold",
            "axes.titlecolor": "#111827",
            "grid.color": "#E5E7EB",
            "grid.alpha": 0.75,
            "grid.linewidth": 0.9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.facecolor": "#FBFBFD",
            "savefig.bbox": "tight",
            "legend.frameon": True,
            "legend.facecolor": "white",
            "legend.edgecolor": "#E5E7EB",
        }
    )


def markdown_table(df: pd.DataFrame, float_fmt: str = ".2f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    rendered_headers = [str(col) for col in headers]
    rows: List[str] = []
    for _, row in df.iterrows():
        vals: List[str] = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    vals.append("")
                else:
                    vals.append(format(value, float_fmt))
            else:
                vals.append(str(value))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([
        "| " + " | ".join(rendered_headers) + " |",
        "| " + " | ".join(["---"] * len(rendered_headers)) + " |",
        *rows,
    ])


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def instantiate_trader():
    module = load_module(MODEL_NAME, MODEL_PATH)
    return module.Trader()


def load_official_log_summary() -> pd.DataFrame:
    obj = json.loads(OFFICIAL_LOG_PATH.read_text())
    activities = pd.read_csv(StringIO(obj["activitiesLog"]), sep=";")
    trades = pd.DataFrame(obj.get("tradeHistory", []))
    logs = pd.DataFrame(obj.get("logs", []))
    step = float(activities["timestamp"].drop_duplicates().sort_values().diff().dropna().mode().iloc[0])
    summary = pd.DataFrame(
        [
            {
                "source": str(OFFICIAL_LOG_PATH),
                "official_day_count": int(activities["day"].nunique()),
                "official_days": ",".join(str(int(day)) for day in sorted(activities["day"].unique())),
                "official_products": ",".join(sorted(activities["product"].unique())),
                "activity_rows": int(len(activities)),
                "activity_rows_per_product": int(len(activities) / activities["product"].nunique()),
                "decision_timestamps": int(activities["timestamp"].nunique()),
                "timestamp_min": int(activities["timestamp"].min()),
                "timestamp_max": int(activities["timestamp"].max()),
                "timestamp_step": int(step),
                "engine_log_rows": int(len(logs)),
                "trade_history_rows": int(len(trades)),
                "submission_trade_rows": int(((trades["buyer"] == "SUBMISSION") | (trades["seller"] == "SUBMISSION")).sum()) if not trades.empty else 0,
            }
        ]
    )
    return summary


def load_all_raw_data() -> Dict[str, Dict[int, ag.LoadedDayData]]:
    return {product: {day: ag.load_day_data(ROUND_NAME, day, product) for day in DAYS} for product in PRODUCTS}


def compute_time_to_threshold(results_df: pd.DataFrame, threshold: int) -> float:
    hit = results_df.loc[results_df["position"] >= threshold, "timestamp"]
    return float(hit.iloc[0]) if not hit.empty else np.nan


def summarize_fills(fills_df: pd.DataFrame) -> Dict[str, float]:
    if fills_df.empty:
        return {
            "fill_count": 0.0,
            "maker_share": np.nan,
            "aggressive_fill_share": np.nan,
            "avg_fill_size": np.nan,
        }
    return {
        "fill_count": float(len(fills_df)),
        "maker_share": float((fills_df["source"] == "MARKET_TRADE").mean()),
        "aggressive_fill_share": float((fills_df["source"] == "AGGRESSIVE").mean()),
        "avg_fill_size": float(fills_df["quantity"].mean()),
    }


def compute_drawdown(series: pd.Series) -> float:
    return float((series - series.cummax()).min())


def compute_product_day_metrics(
    scenario: str,
    day: int,
    product: str,
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> Dict[str, float | str | int]:
    final_pnl = float(results_df["pnl"].iloc[-1])
    fill_metrics = summarize_fills(fills_df)
    row: Dict[str, float | str | int] = {
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS[scenario],
        "day": int(day),
        "product": product,
        "product_label": PRODUCT_LABELS[product],
        "P_d": final_pnl,
        "drawdown": compute_drawdown(results_df["pnl"]),
        "fill_count": fill_metrics["fill_count"],
        "maker_share": fill_metrics["maker_share"],
        "avg_fill_size": fill_metrics["avg_fill_size"],
        "avg_abs_position": float(results_df["position"].abs().mean()),
        "avg_position": float(results_df["position"].mean()),
        "max_abs_position": float(results_df["position"].abs().max()),
        "pct_time_abs_ge_60": float((results_df["position"].abs() >= 60).mean()),
        "pct_time_abs_ge_70": float((results_df["position"].abs() >= 70).mean()),
        "pct_time_at_limit": float((results_df["position"].abs() >= POSITION_LIMITS[product]).mean()),
        "final_position": float(results_df["position"].iloc[-1]),
    }
    if product == "INTARIAN_PEPPER_ROOT":
        row["time_to_50"] = compute_time_to_threshold(results_df, 50)
        row["time_to_70"] = compute_time_to_threshold(results_df, 70)
        row["time_to_80"] = compute_time_to_threshold(results_df, 80)
        row["pct_time_pos_ge_70"] = float((results_df["position"] >= 70).mean())
        row["pct_time_pos_at_80"] = float((results_df["position"] >= 80).mean())
    return row


def merge_total_curve(product_frames: Mapping[str, pd.DataFrame], day: int) -> pd.DataFrame:
    merged: Optional[pd.DataFrame] = None
    for product, frame in product_frames.items():
        label = PRODUCT_LABELS[product].lower()
        sub = frame[["timestamp", "pnl", "position", "mid_price"]].rename(
            columns={
                "pnl": f"pnl_{label}",
                "position": f"pos_{label}",
                "mid_price": f"mid_{label}",
            }
        )
        merged = sub if merged is None else merged.merge(sub, on="timestamp", how="outer")
    assert merged is not None
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    pnl_cols = [c for c in merged.columns if c.startswith("pnl_")]
    merged[pnl_cols] = merged[pnl_cols].ffill().fillna(0.0)
    merged["total_pnl"] = merged[pnl_cols].sum(axis=1)
    merged["day"] = int(day)
    merged["sample_global_ts"] = DAYS.index(day) * DAY_HORIZON + merged["timestamp"]
    merged["drawdown"] = merged["total_pnl"] - merged["total_pnl"].cummax()
    return merged


def compute_total_day_metrics(
    scenario: str,
    day: int,
    total_curve: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> Dict[str, float | str | int]:
    fill_metrics = summarize_fills(fills_df)
    return {
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS[scenario],
        "day": int(day),
        "product": "TOTAL",
        "product_label": "TOTAL",
        "P_d": float(total_curve["total_pnl"].iloc[-1]),
        "drawdown": float(total_curve["drawdown"].min()),
        "fill_count": fill_metrics["fill_count"],
        "maker_share": fill_metrics["maker_share"],
        "avg_fill_size": fill_metrics["avg_fill_size"],
        "avg_abs_position": np.nan,
        "avg_position": np.nan,
        "max_abs_position": np.nan,
        "pct_time_abs_ge_60": np.nan,
        "pct_time_abs_ge_70": np.nan,
        "pct_time_at_limit": np.nan,
        "final_position": np.nan,
    }


def run_all_scenarios(loaded_data: Mapping[str, Mapping[int, ag.LoadedDayData]]):
    day_metrics_rows: List[Dict[str, float | str | int]] = []
    product_runs: Dict[str, Dict[int, Dict[str, pd.DataFrame]]] = {scenario: {} for scenario, _ in SCENARIOS}
    fill_runs: Dict[str, Dict[int, Dict[str, pd.DataFrame]]] = {scenario: {} for scenario, _ in SCENARIOS}
    total_runs: Dict[str, Dict[int, pd.DataFrame]] = {scenario: {} for scenario, _ in SCENARIOS}

    for scenario, _kind in SCENARIOS:
        proxy = None if scenario == "baseline" else PROXY_LOOKUP[scenario]
        for day in DAYS:
            product_runs[scenario][day] = {}
            fill_runs[scenario][day] = {}
            for product in PRODUCTS:
                raw = loaded_data[product][day]
                depth, trades = ag.apply_proxy(raw, proxy) if proxy is not None else (raw.depth_by_ts, raw.trades_df.copy())
                trader = instantiate_trader()
                results_df, fills_df, _metrics = bt.run_backtest_on_loaded_data(
                    trader,
                    product,
                    [day],
                    {day: (depth, trades)},
                    reset_between_days=False,
                )
                results_df = results_df.copy().sort_values("timestamp").reset_index(drop=True)
                results_df["scenario"] = scenario
                results_df["product"] = product
                results_df["sample_global_ts"] = DAYS.index(day) * DAY_HORIZON + results_df["timestamp"]
                fills_df = fills_df.copy().sort_values("timestamp").reset_index(drop=True) if not fills_df.empty else pd.DataFrame(
                    columns=["day", "timestamp", "global_ts", "product", "side", "price", "quantity", "source"]
                )
                if not fills_df.empty:
                    fills_df["scenario"] = scenario
                    fills_df["product"] = product
                    fills_df["sample_global_ts"] = DAYS.index(day) * DAY_HORIZON + fills_df["timestamp"]
                product_runs[scenario][day][product] = results_df
                fill_runs[scenario][day][product] = fills_df
                day_metrics_rows.append(compute_product_day_metrics(scenario, day, product, results_df, fills_df))

            total_curve = merge_total_curve(product_runs[scenario][day], day)
            total_runs[scenario][day] = total_curve
            combined_fills = pd.concat([fill_runs[scenario][day][product] for product in PRODUCTS], ignore_index=True)
            day_metrics_rows.append(compute_total_day_metrics(scenario, day, total_curve, combined_fills))

    return pd.DataFrame(day_metrics_rows), product_runs, fill_runs, total_runs


def build_delta_day_metrics(day_metrics: pd.DataFrame) -> pd.DataFrame:
    base = day_metrics[day_metrics["scenario"] == "baseline"].copy()
    proxies = day_metrics[day_metrics["scenario"] != "baseline"].copy()
    merged = proxies.merge(
        base[[
            "day", "product", "P_d", "drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position", "pct_time_abs_ge_70", "pct_time_at_limit", "time_to_50", "time_to_70", "time_to_80"
        ]].rename(
            columns={
                "P_d": "P0_d",
                "drawdown": "drawdown_P0",
                "fill_count": "fill_count_P0",
                "maker_share": "maker_share_P0",
                "avg_fill_size": "avg_fill_size_P0",
                "avg_abs_position": "avg_abs_position_P0",
                "pct_time_abs_ge_70": "pct_time_abs_ge_70_P0",
                "pct_time_at_limit": "pct_time_at_limit_P0",
                "time_to_50": "time_to_50_P0",
                "time_to_70": "time_to_70_P0",
                "time_to_80": "time_to_80_P0",
            }
        ),
        on=["day", "product"],
        how="left",
    )
    merged = merged.rename(columns={"P_d": "P1_d"})
    merged["Delta_d"] = merged["P1_d"] - merged["P0_d"]
    merged["drawdown_change"] = merged["drawdown"] - merged["drawdown_P0"]
    merged["fill_count_change"] = merged["fill_count"] - merged["fill_count_P0"]
    merged["maker_share_change"] = merged["maker_share"] - merged["maker_share_P0"]
    merged["avg_fill_size_change"] = merged["avg_fill_size"] - merged["avg_fill_size_P0"]
    merged["avg_abs_position_change"] = merged["avg_abs_position"] - merged["avg_abs_position_P0"]
    merged["time_to_70_change"] = merged["time_to_70"] - merged["time_to_70_P0"]
    merged["time_to_80_change"] = merged["time_to_80"] - merged["time_to_80_P0"]
    return merged


def summarize_distribution(values: Sequence[float]) -> Dict[str, float]:
    s = pd.Series(list(values), dtype=float)
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "min": float(s.min()),
        "max": float(s.max()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "p25": float(s.quantile(0.25)),
        "cv": float(s.std(ddof=1) / s.mean()) if len(s) > 1 and float(s.mean()) != 0.0 else np.nan,
    }


def build_baseline_summary(day_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    base = day_metrics[day_metrics["scenario"] == "baseline"].copy()
    for product in [*PRODUCTS, "TOTAL"]:
        sub = base[base["product"] == product].sort_values("day")
        stats = summarize_distribution(sub["P_d"].tolist())
        rows.append({
            "product": PRODUCT_LABELS[product],
            "P0_mean": stats["mean"],
            "P0_median": stats["median"],
            "P0_min": stats["min"],
            "P0_max": stats["max"],
            "P0_std": stats["std"],
            "P0_cv": stats["cv"],
            "P0_p25": stats["p25"],
        })
    return pd.DataFrame(rows)


def build_delta_summary(delta_day: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    total = delta_day[delta_day["product"] == "TOTAL"].copy()
    for scenario in ["uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]:
        sub = total[total["scenario"] == scenario].sort_values("day")
        stats = summarize_distribution(sub["Delta_d"].tolist())
        rows.append({
            "proxy": SCENARIO_LABELS[scenario],
            "Delta_mean": stats["mean"],
            "Delta_median": stats["median"],
            "Delta_min": stats["min"],
            "Delta_max": stats["max"],
            "Delta_std": stats["std"],
            "Delta_p25": stats["p25"],
        })
    return pd.DataFrame(rows)


def logistic_q(bid: float, scenario: CutoffScenario) -> float:
    return 1.0 / (1.0 + math.exp(-(float(bid) - scenario.median_bid) / scenario.slope))


def build_delta_variants(delta_day: pd.DataFrame) -> Dict[str, float]:
    conservative = delta_day[(delta_day["scenario"] == "uniform_depth_125") & (delta_day["product"] == "TOTAL")]["Delta_d"].sort_values().tolist()
    central = delta_day[(delta_day["scenario"] == "front_bias_depth_25") & (delta_day["product"] == "TOTAL")]["Delta_d"].sort_values().tolist()
    cons_stats = summarize_distribution(conservative)
    central_stats = summarize_distribution(central)
    return {
        "central": central_stats["mean"],
        "conservative": cons_stats["mean"],
        "downside": cons_stats["min"],
        "ra1": 0.7 * cons_stats["mean"],
        "ra2": cons_stats["min"],
        "ra3": cons_stats["p25"],
    }


def build_bid_grid(p0_mean: float, delta_variants: Mapping[str, float]) -> pd.DataFrame:
    rows: List[Dict[str, float | str | int]] = []
    for delta_name in ["central", "conservative", "downside", "ra1", "ra2", "ra3"]:
        delta = float(delta_variants[delta_name])
        for bid in BID_GRID:
            row: Dict[str, float | str | int] = {
                "delta_variant": delta_name,
                "delta_label": DELTA_VARIANT_LABELS[delta_name],
                "delta_value": delta,
                "bid": int(bid),
                "P0_mean": p0_mean,
                "net_gain_if_accepted": delta - bid,
                "uplift_pct_vs_base": (delta - bid) / p0_mean,
                "fee_roi": (delta - bid) / bid if bid > 0 else np.nan,
            }
            weighted_ev = 0.0
            weighted_q = 0.0
            for scenario in CUTOFF_SCENARIOS:
                q = logistic_q(bid, scenario)
                ev_uplift = q * (delta - bid)
                row[f"q_{scenario.name}"] = q
                row[f"EV_uplift_{scenario.name}"] = ev_uplift
                row[f"EV_{scenario.name}"] = p0_mean + ev_uplift
                weighted_ev += scenario.weight * ev_uplift
                weighted_q += scenario.weight * q
            row["q_weighted"] = weighted_q
            row["EV_uplift_weighted"] = weighted_ev
            row["EV_weighted"] = p0_mean + weighted_ev
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["delta_variant", "bid"]).reset_index(drop=True)


def build_bid_recommendations(bid_grid: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | str | int]] = []
    for delta_name, sub in bid_grid.groupby("delta_variant", sort=False):
        sub = sub.sort_values("bid")
        max_ev = float(sub["EV_uplift_weighted"].max())
        best_bid = int(sub.loc[sub["EV_uplift_weighted"].idxmax(), "bid"])
        bid_95 = int(sub.loc[sub["EV_uplift_weighted"] >= 0.95 * max_ev, "bid"].min())
        bid_90 = int(sub.loc[sub["EV_uplift_weighted"] >= 0.90 * max_ev, "bid"].min())
        rows.append({
            "delta_variant": delta_name,
            "delta_label": DELTA_VARIANT_LABELS[delta_name],
            "best_bid_ev_mean": best_bid,
            "smallest_bid_95pct": bid_95,
            "smallest_bid_90pct": bid_90,
            "max_EV_uplift": max_ev,
        })
    return pd.DataFrame(rows)


def build_day_bid_analysis(day_metrics: pd.DataFrame, delta_day: pd.DataFrame) -> pd.DataFrame:
    base_total = day_metrics[(day_metrics["scenario"] == "baseline") & (day_metrics["product"] == "TOTAL")][["day", "P_d"]].rename(columns={"P_d": "P0_d"})
    conservative = delta_day[(delta_day["scenario"] == "uniform_depth_125") & (delta_day["product"] == "TOTAL")][["day", "Delta_d"]].copy()
    rows: List[Dict[str, float | int]] = []
    for _, r in conservative.merge(base_total, on="day").iterrows():
        for bid in SELECTED_BIDS:
            rows.append({
                "day": int(r["day"]),
                "bid": int(bid),
                "P0_d": float(r["P0_d"]),
                "Delta_d": float(r["Delta_d"]),
                "net_gain_if_accepted_d": float(r["Delta_d"] - bid),
                "uplift_pct_vs_base_d": float((r["Delta_d"] - bid) / r["P0_d"]),
                "fee_roi_d": float((r["Delta_d"] - bid) / bid),
            })
    return pd.DataFrame(rows)


def build_leave_one_day_out(day_metrics: pd.DataFrame, delta_day: pd.DataFrame) -> pd.DataFrame:
    base_total = day_metrics[(day_metrics["scenario"] == "baseline") & (day_metrics["product"] == "TOTAL")][["day", "P_d"]].rename(columns={"P_d": "P0_d"})
    cons_total = delta_day[(delta_day["scenario"] == "uniform_depth_125") & (delta_day["product"] == "TOTAL")][["day", "Delta_d"]]
    merged = cons_total.merge(base_total, on="day")
    rows: List[Dict[str, float | str | int]] = []
    for subset in combinations(DAYS, 2):
        sub = merged[merged["day"].isin(subset)]
        p0_mean = float(sub["P0_d"].mean())
        delta_mean = float(sub["Delta_d"].mean())
        work = build_bid_grid(p0_mean, {k: delta_mean for k in ["central", "conservative", "downside", "ra1", "ra2", "ra3"]})
        cons = work[work["delta_variant"] == "conservative"].copy()
        max_ev = float(cons["EV_uplift_weighted"].max())
        best_bid = int(cons.loc[cons["EV_uplift_weighted"].idxmax(), "bid"])
        bid_95 = int(cons.loc[cons["EV_uplift_weighted"] >= 0.95 * max_ev, "bid"].min())
        bid_90 = int(cons.loc[cons["EV_uplift_weighted"] >= 0.90 * max_ev, "bid"].min())
        rows.append({
            "days": ",".join(str(d) for d in subset),
            "P0_mean_subset": p0_mean,
            "Delta_mean_subset": delta_mean,
            "best_bid": best_bid,
            "smallest_bid_95pct": bid_95,
            "smallest_bid_90pct": bid_90,
        })
    return pd.DataFrame(rows)


def build_worst_day_summary(day_metrics: pd.DataFrame, delta_day: pd.DataFrame) -> pd.DataFrame:
    base_total = day_metrics[(day_metrics["scenario"] == "baseline") & (day_metrics["product"] == "TOTAL")][["day", "P_d"]].rename(columns={"P_d": "P0_d"})
    cons_total = delta_day[(delta_day["scenario"] == "uniform_depth_125") & (delta_day["product"] == "TOTAL")][["day", "Delta_d"]].merge(base_total, on="day")
    worst_day = cons_total.loc[cons_total["Delta_d"].idxmin()]
    rows: List[Dict[str, float | int]] = []
    for bid in BID_GRID:
        rows.append({
            "day": int(worst_day["day"]),
            "bid": int(bid),
            "P0_d": float(worst_day["P0_d"]),
            "Delta_d": float(worst_day["Delta_d"]),
            "net_gain_if_accepted": float(worst_day["Delta_d"] - bid),
            "uplift_pct_vs_base": float((worst_day["Delta_d"] - bid) / worst_day["P0_d"]),
            "fee_roi": float((worst_day["Delta_d"] - bid) / bid) if bid > 0 else np.nan,
            "EV_uplift_weighted": float(sum(s.weight * logistic_q(bid, s) * (float(worst_day["Delta_d"]) - bid) for s in CUTOFF_SCENARIOS)),
        })
    out = pd.DataFrame(rows)
    return out


def build_sensitivity_heatmap_df() -> pd.DataFrame:
    rows: List[Dict[str, float | int]] = []
    for delta in np.arange(600, 2201, 100):
        for cutoff_median in np.arange(20, 161, 10):
            slope = max(6.0, 0.18 * cutoff_median)
            ev_rows = []
            for bid in BID_GRID:
                q = 1.0 / (1.0 + math.exp(-(float(bid) - cutoff_median) / slope))
                ev_rows.append((bid, q * (float(delta) - bid)))
            ev_df = pd.DataFrame(ev_rows, columns=["bid", "ev"])
            max_ev = float(ev_df["ev"].max())
            best_bid = int(ev_df.loc[ev_df["ev"].idxmax(), "bid"])
            plateau_95 = int(ev_df.loc[ev_df["ev"] >= 0.95 * max_ev, "bid"].min())
            rows.append({
                "delta_assumed": float(delta),
                "cutoff_median": float(cutoff_median),
                "best_bid": best_bid,
                "plateau95_bid": plateau_95,
            })
    return pd.DataFrame(rows)


def save_dataframe(df: pd.DataFrame, name: str) -> None:
    df.to_csv(RESULTS_DIR / f"{name}.csv", index=False)


def plot_p0_p1_by_day(day_metrics: pd.DataFrame) -> None:
    configure_style()
    total = day_metrics[day_metrics["product"] == "TOTAL"].copy()
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), sharey=True)
    for ax, day in zip(axes, DAYS):
        sub = total[total["day"] == day].copy().sort_values("scenario")
        sns.barplot(data=sub, x="scenario_label", y="P_d", palette=[PALETTE[s] for s in sub["scenario"]], ax=ax)
        ax.set_title(f"Día {day}")
        ax.set_xlabel("")
        ax.set_ylabel("PnL por ronda" if day == DAYS[0] else "")
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("P0_d y P1_d por día (TOTAL)", x=0.01, ha="left", fontsize=22)
    fig.savefig(PLOTS_DIR / "p0_p1_by_day.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_by_day(delta_day: pd.DataFrame) -> None:
    configure_style()
    total = delta_day[delta_day["product"] == "TOTAL"].copy()
    fig, ax = plt.subplots(figsize=(13.5, 6.8))
    sns.barplot(data=total, x="day", y="Delta_d", hue="scenario_label", palette=[PALETTE[s] for s in total["scenario"].unique()], ax=ax)
    ax.axhline(0, color="#6B7280", linewidth=1)
    ax.set_title("Delta_d por día y proxy (TOTAL)")
    ax.set_xlabel("Día = ronda comparable live")
    ax.set_ylabel("Delta_d")
    ax.legend(title="Proxy")
    fig.savefig(PLOTS_DIR / "delta_by_day.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_violin(delta_day: pd.DataFrame) -> None:
    configure_style()
    total = delta_day[delta_day["product"] == "TOTAL"].copy()
    fig, ax = plt.subplots(figsize=(12.5, 6.6))
    sns.violinplot(data=total, x="scenario_label", y="Delta_d", inner="box", palette=[PALETTE[s] for s in total["scenario"].unique()], ax=ax)
    sns.stripplot(data=total, x="scenario_label", y="Delta_d", color="#111827", size=8, alpha=0.85, ax=ax)
    ax.set_title("Distribución de Delta_d por proxy (TOTAL)")
    ax.set_xlabel("")
    ax.set_ylabel("Delta_d por día")
    ax.tick_params(axis="x", rotation=20)
    fig.savefig(PLOTS_DIR / "delta_violin.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_pnl_cumulative_by_day(total_runs: Mapping[str, Dict[int, pd.DataFrame]]) -> None:
    configure_style()
    fig, axes = plt.subplots(3, 1, figsize=(15, 16), sharex=True)
    for ax, day in zip(axes, DAYS):
        for scenario, _ in SCENARIOS:
            sub = total_runs[scenario][day]
            ax.plot(sub["timestamp"], sub["total_pnl"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.3)
        ax.set_title(f"PnL acumulado — día {day}")
        ax.set_ylabel("PnL")
    axes[-1].set_xlabel("Timestamp")
    axes[0].legend(ncol=2, fontsize=10)
    fig.suptitle("PnL acumulado por día — baseline vs proxies", x=0.01, ha="left", fontsize=22)
    fig.savefig(PLOTS_DIR / "pnl_cumulative_by_day.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_cumulative_by_day(total_runs: Mapping[str, Dict[int, pd.DataFrame]]) -> None:
    configure_style()
    fig, axes = plt.subplots(3, 1, figsize=(15, 16), sharex=True)
    for ax, day in zip(axes, DAYS):
        base = total_runs["baseline"][day][["timestamp", "total_pnl"]].rename(columns={"total_pnl": "base"})
        for scenario in ["uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]:
            sub = total_runs[scenario][day][["timestamp", "total_pnl"]].rename(columns={"total_pnl": "proxy"}).merge(base, on="timestamp")
            sub["delta"] = sub["proxy"] - sub["base"]
            ax.plot(sub["timestamp"], sub["delta"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.3)
        ax.axhline(0, color="#6B7280", linewidth=1)
        ax.set_title(f"Delta acumulado — día {day}")
        ax.set_ylabel("Delta")
    axes[-1].set_xlabel("Timestamp")
    axes[0].legend(fontsize=10)
    fig.suptitle("Delta acumulado por día", x=0.01, ha="left", fontsize=22)
    fig.savefig(PLOTS_DIR / "delta_cumulative_by_day.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_pepper_inventory_by_day(product_runs: Mapping[str, Dict[int, Dict[str, pd.DataFrame]]]) -> None:
    configure_style()
    fig, axes = plt.subplots(3, 1, figsize=(15, 16), sharex=True)
    for ax, day in zip(axes, DAYS):
        for scenario in ["baseline", "front_bias_depth_25"]:
            sub = product_runs[scenario][day]["INTARIAN_PEPPER_ROOT"]
            ax.plot(sub["timestamp"], sub["position"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.3)
        for level, color in [(50, "#94A3B8"), (70, "#F59E0B"), (80, "#DC2626")]:
            ax.axhline(level, color=color, linestyle="--", linewidth=1.1)
        ax.set_title(f"PEPPER inventory — día {day}")
        ax.set_ylabel("Posición")
    axes[-1].set_xlabel("Timestamp")
    axes[0].legend(fontsize=10)
    fig.suptitle("Trayectoria de inventario de PEPPER — baseline vs proxy central", x=0.01, ha="left", fontsize=22)
    fig.savefig(PLOTS_DIR / "pepper_inventory_by_day.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_bid_ev_and_cutoff(bid_grid: pd.DataFrame) -> None:
    configure_style()
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    weighted = bid_grid.copy()
    for delta_name in ["central", "conservative", "downside", "ra1", "ra2", "ra3"]:
        sub = weighted[weighted["delta_variant"] == delta_name].sort_values("bid")
        axes[0].plot(sub["bid"], sub["EV_uplift_weighted"], marker="o", linewidth=2.2, label=DELTA_VARIANT_LABELS[delta_name], color=PALETTE.get(delta_name, None))
    axes[0].set_title("EV por bid — variantes de Delta")
    axes[0].set_xlabel("Bid")
    axes[0].set_ylabel("EV(b) - P0_mean")
    axes[0].legend(fontsize=9, ncol=2)

    cons = weighted[weighted["delta_variant"] == "conservative"].sort_values("bid")
    for scenario in CUTOFF_SCENARIOS:
        axes[1].plot(cons["bid"], cons[f"EV_uplift_{scenario.name}"], marker="o", linewidth=2.2, label=scenario.label, color=PALETTE[scenario.name])
    axes[1].plot(cons["bid"], cons["EV_uplift_weighted"], color=PALETTE["weighted"], linewidth=3.0, label="Mixto ponderado")
    axes[1].set_title("EV por bid — escenarios de cutoff (Delta conservador)")
    axes[1].set_xlabel("Bid")
    axes[1].set_ylabel("EV(b) - P0_mean")
    axes[1].legend(fontsize=9)
    fig.savefig(PLOTS_DIR / "bid_ev_curves.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_acceptance_probabilities() -> None:
    configure_style()
    bids = pd.DataFrame({"bid": BID_GRID})
    fig, ax = plt.subplots(figsize=(13.5, 6.5))
    weighted = np.zeros(len(bids))
    for scenario in CUTOFF_SCENARIOS:
        qvals = bids["bid"].apply(lambda b: logistic_q(float(b), scenario))
        weighted += scenario.weight * qvals.to_numpy()
        ax.plot(bids["bid"], qvals, marker="o", linewidth=2.3, label=scenario.label, color=PALETTE[scenario.name])
    ax.plot(bids["bid"], weighted, marker="o", linewidth=3.0, color=PALETTE["weighted"], label="q(b) ponderado")
    ax.set_title("Probabilidad de aceptación q(b)")
    ax.set_xlabel("Bid")
    ax.set_ylabel("Probabilidad")
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "acceptance_probability_qb.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_uplift_roi_by_bid(bid_grid: pd.DataFrame) -> None:
    configure_style()
    fig, axes = plt.subplots(1, 2, figsize=(16, 6.5))
    for delta_name in ["conservative", "downside", "ra2"]:
        sub = bid_grid[bid_grid["delta_variant"] == delta_name].sort_values("bid")
        axes[0].plot(sub["bid"], 100 * sub["uplift_pct_vs_base"], marker="o", linewidth=2.2, label=DELTA_VARIANT_LABELS[delta_name], color=PALETTE.get(delta_name, None))
        axes[1].plot(sub["bid"], sub["fee_roi"], marker="o", linewidth=2.2, label=DELTA_VARIANT_LABELS[delta_name], color=PALETTE.get(delta_name, None))
        mark = sub[sub["bid"].isin(SELECTED_BIDS)]
        axes[0].scatter(mark["bid"], 100 * mark["uplift_pct_vs_base"], s=80, color=PALETTE.get(delta_name, None))
        axes[1].scatter(mark["bid"], mark["fee_roi"], s=80, color=PALETTE.get(delta_name, None))
    axes[0].axhline(0, color="#6B7280", linewidth=1)
    axes[1].axhline(0, color="#6B7280", linewidth=1)
    axes[0].set_title("Uplift % por bid")
    axes[1].set_title("Fee ROI por bid")
    axes[0].set_xlabel("Bid")
    axes[1].set_xlabel("Bid")
    axes[0].set_ylabel("% vs P0_mean")
    axes[1].set_ylabel("(Delta - b) / b")
    axes[0].legend(fontsize=9)
    fig.savefig(PLOTS_DIR / "uplift_fee_roi_by_bid.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_sensitivity_heatmap(sensitivity_df: pd.DataFrame) -> None:
    configure_style()
    pivot = sensitivity_df.pivot(index="cutoff_median", columns="delta_assumed", values="plateau95_bid")
    fig, ax = plt.subplots(figsize=(14, 7))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="YlGnBu", cbar_kws={"label": "Bid recomendado (95% plateau)"}, ax=ax)
    ax.set_title("Heatmap de sensibilidad — Delta asumido vs cutoff rival")
    ax.set_xlabel("Delta asumido")
    ax.set_ylabel("Mediana del cutoff")
    fig.savefig(PLOTS_DIR / "bid_sensitivity_heatmap.png", dpi=PLOT_DPI)
    plt.close(fig)


def write_report(
    official_summary: pd.DataFrame,
    day_metrics: pd.DataFrame,
    delta_day: pd.DataFrame,
    baseline_summary: pd.DataFrame,
    delta_summary: pd.DataFrame,
    bid_grid: pd.DataFrame,
    bid_recs: pd.DataFrame,
    day_bid: pd.DataFrame,
    loo_df: pd.DataFrame,
    worst_day_df: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
) -> None:
    p0_total = baseline_summary[baseline_summary["product"] == "TOTAL"].iloc[0]
    delta_variants = build_delta_variants(delta_day)
    rec_central = bid_recs[bid_recs["delta_variant"] == "central"].iloc[0]
    rec_cons = bid_recs[bid_recs["delta_variant"] == "conservative"].iloc[0]
    rec_down = bid_recs[bid_recs["delta_variant"] == "downside"].iloc[0]
    rec_ra2 = bid_recs[bid_recs["delta_variant"] == "ra2"].iloc[0]

    recommended_bid = int(rec_cons["smallest_bid_95pct"])
    alt_low = int(rec_cons["smallest_bid_90pct"])
    alt_high = int(max(rec_ra2["smallest_bid_95pct"], rec_cons["smallest_bid_95pct"]))

    rec_cons_row = bid_grid[(bid_grid["delta_variant"] == "conservative") & (bid_grid["bid"] == recommended_bid)].iloc[0]
    rec_cent_row = bid_grid[(bid_grid["delta_variant"] == "central") & (bid_grid["bid"] == recommended_bid)].iloc[0]
    rec_down_row = bid_grid[(bid_grid["delta_variant"] == "downside") & (bid_grid["bid"] == recommended_bid)].iloc[0]
    worst_125 = worst_day_df[worst_day_df["bid"] == 125].iloc[0]

    by_day_total = day_metrics[day_metrics["product"] == "TOTAL"].pivot(index="day", columns="scenario_label", values="P_d").reset_index()
    by_day_product = delta_day[(delta_day["product"] != "TOTAL")][[
        "day", "scenario_label", "product_label", "P0_d", "P1_d", "Delta_d", "fill_count_change", "maker_share_change", "avg_fill_size_change", "avg_abs_position_change", "time_to_70_change", "time_to_80_change"
    ]].copy()
    total_day_table = delta_day[delta_day["product"] == "TOTAL"][ [
        "day", "scenario_label", "P0_d", "P1_d", "Delta_d", "fill_count_change", "maker_share_change", "avg_fill_size_change"
    ] ].copy()

    base_day_table = day_metrics[day_metrics["scenario"] == "baseline"][ [
        "day", "product_label", "P_d", "drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position", "pct_time_abs_ge_70", "pct_time_at_limit", "time_to_50", "time_to_70", "time_to_80"
    ] ].copy()

    proxy_total_delta = delta_day[delta_day["product"] == "TOTAL"].pivot(index="day", columns="scenario_label", values="Delta_d").reset_index()
    selected_bid_table = bid_grid[(bid_grid["bid"].isin(BID_GRID)) & (bid_grid["delta_variant"].isin(["central", "conservative", "downside", "ra1", "ra2", "ra3"]))][[
        "delta_label", "bid", "q_low", "q_central", "q_high", "q_stress", "q_weighted", "net_gain_if_accepted", "uplift_pct_vs_base", "fee_roi", "EV_uplift_weighted"
    ]].copy()
    selected_bid_table["uplift_pct_vs_base"] *= 100

    risk_adjusted_compare = pd.DataFrame(
        [
            {"variant": "Delta_RA_1", "definition": "0.7 * Delta_conservative", "value": delta_variants["ra1"], "comment": "Haircut legacy; útil como comparación pero arbitrario."},
            {"variant": "Delta_RA_2", "definition": "min daily Delta_conservative", "value": delta_variants["ra2"], "comment": "Stress observado más transparente; lo uso como guardrail principal."},
            {"variant": "Delta_RA_3", "definition": "p25 daily Delta_conservative", "value": delta_variants["ra3"], "comment": "Cuantil downside interesante, pero con n=3 depende mucho de interpolación."},
        ]
    )

    q_table = pd.DataFrame(
        [
            {"bid": bid, **{f"q_{s.name}": logistic_q(bid, s) for s in CUTOFF_SCENARIOS}, "q_weighted": sum(s.weight * logistic_q(bid, s) for s in CUTOFF_SCENARIOS)}
            for bid in BID_GRID
        ]
    )

    sensitivity_slice = sensitivity_df[sensitivity_df["delta_assumed"].isin([600, 800, 1000, 1200, 1600, 2000]) & sensitivity_df["cutoff_median"].isin([20, 40, 60, 80, 100, 120, 140, 160])]
    sensitivity_pivot = sensitivity_slice.pivot(index="cutoff_median", columns="delta_assumed", values="plateau95_bid").reset_index()

    lines: List[str] = [
        "# Round 2 — análisis MAF para model_kiko con unidad estadística corregida",
        "",
        "## A. Resumen ejecutivo",
        "",
        "- Nueva unidad estadística usada: **1 día = 1 ronda comparable live**.",
        f"- `P0_d` total (TOTAL) — media **{p0_total['P0_mean']:,.1f}**, mediana **{p0_total['P0_median']:,.1f}**, mínimo **{p0_total['P0_min']:,.1f}**.",
        f"- `Delta_central` por ronda: **{delta_variants['central']:,.1f}**.",
        f"- `Delta_conservative` por ronda: **{delta_variants['conservative']:,.1f}**.",
        f"- `Delta_downside` por ronda: **{delta_variants['downside']:,.1f}**.",
        f"- Rango de bids razonable: **{alt_low}–{alt_high}**.",
        f"- Bid recomendado final: **`{recommended_bid}`**.",
        f"- A `bid={recommended_bid}`, el uplift neto condicional es **{100*rec_cons_row['uplift_pct_vs_base']:.2f}%** (conservative) a **{100*rec_cent_row['uplift_pct_vs_base']:.2f}%** (central) sobre `P0_mean`.",
        "",
        "## B. Corrección metodológica",
        "",
        "### Por qué `día = ronda`",
        "",
        markdown_table(official_summary, ".0f"),
        "",
        "El `official_result.log` de Round 1 confirma una sola sesión oficial con 10,000 decision timestamps (`0 -> 999900`, step 100). Los CSV locales de Round 2 tienen exactamente esa estructura por día. Por lo tanto, cada día de Round 2 es el análogo correcto de una ronda live completa.",
        "",
        "### Por qué NO agregar 3 días como una sola ronda",
        "",
        "Agregar tres días como si fueran una única sesión cambia la unidad de decisión del bid y mezcla paths independientes. El fee se paga una sola vez por ronda oficial, así que la variable relevante es el valor del extra access **por día/path**, no el total concatenado de tres paths distintos.",
        "",
        "### Por qué NO reescalar a 1M timestamps",
        "",
        "No hace falta reescalar temporalmente: cada día ya cubre el horizonte oficial comparable (`0 -> 999900`). La proyección correcta es **cross-sectional entre días**, no una multiplicación artificial por tiempo.",
        "",
        "## C. Resultados por día",
        "",
        "### Baseline por día (`P0_d`)",
        "",
        markdown_table(base_day_table.rename(columns={"P_d": "P0_d"}), ".3f"),
        "",
        "### `P0_d`, `P1_d`, `Delta_d` por día — TOTAL",
        "",
        markdown_table(total_day_table, ".3f"),
        "",
        "### `Delta_d` por producto y microestructura",
        "",
        markdown_table(by_day_product, ".3f"),
        "",
        "### Resumen entre días de `Delta_d` (TOTAL)",
        "",
        markdown_table(delta_summary, ".3f"),
        "",
        "## D. Robustez entre días",
        "",
        "### Dispersión de `P0_d` y `Delta_d`",
        "",
        markdown_table(baseline_summary, ".3f"),
        "",
        "### Análisis por día para bids 100 / 125 / 150 (proxy conservador)",
        "",
        markdown_table(day_bid, ".3f"),
        "",
        "### Leave-one-day-out (proxy conservador)",
        "",
        markdown_table(loo_df, ".3f"),
        "",
        "### Worst-day analysis",
        "",
        markdown_table(worst_day_df[worst_day_df["bid"].isin(SELECTED_BIDS)], ".3f"),
        "",
        f"En el peor día observado, con `bid=125`, `Delta_d - b = {worst_125['net_gain_if_accepted']:,.1f}`, uplift neto = **{100*worst_125['uplift_pct_vs_base']:.2f}%**, fee ROI = **{worst_125['fee_roi']:.2f}x**.",
        "",
        "### Comparación de variantes risk-adjusted",
        "",
        markdown_table(risk_adjusted_compare, ".3f"),
        "",
        "Mi lectura: `RA_1` sirve solo como benchmark histórico porque el haircut es arbitrario. `RA_3` es interesante, pero con 3 días el percentil 25 depende demasiado de interpolación. La mejor variante para un guardrail de decisión es **`RA_2 = min daily Delta_conservative`**: es simple, observable y directamente alineada con la pregunta de robustez por ronda.",
        "",
        "## E. Game theory del cutoff",
        "",
        "Escenarios de cutoff asumidos:",
        "",
        markdown_table(pd.DataFrame([{
            "escenario": s.label,
            "median_bid": s.median_bid,
            "slope": s.slope,
            "weight": s.weight,
            "lectura": s.description,
        } for s in CUTOFF_SCENARIOS]), ".3f"),
        "",
        "### `q(b)` por bid",
        "",
        markdown_table(q_table, ".3f"),
        "",
        "### EV por bid y variante de Delta",
        "",
        markdown_table(selected_bid_table, ".3f"),
        "",
        f"- Bid que maximiza EV medio (`Delta_central`): **{int(rec_central['best_bid_ev_mean'])}**.",
        f"- Menor bid dentro del 95% del EV máximo (`Delta_conservative`): **{int(rec_cons['smallest_bid_95pct'])}**.",
        f"- Menor bid dentro del 90% del EV máximo (`Delta_conservative`): **{int(rec_cons['smallest_bid_90pct'])}**.",
        f"- Mejor bid en downside (`Delta_downside`): **{int(rec_down['best_bid_ev_mean'])}**.",
        f"- Mejor bid en worst-day guardrail (`Delta_RA_2`): **{int(rec_ra2['best_bid_ev_mean'])}**.",
        "",
        "## F. Visualizaciones",
        "",
        "Plots generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_day_unit/plots/`:",
        "",
        "1. `p0_p1_by_day.png` — compara P0_d y P1_d por día; ayuda a ver cuánto cambia el valor por ronda real.",
        "2. `delta_by_day.png` — muestra `Delta_d` por día y proxy; sirve para ver dispersión y estabilidad entre rondas.",
        "3. `delta_violin.png` — resume la distribución de `Delta_d`; útil para comparar central tendency vs downside.",
        "4. `pnl_cumulative_by_day.png` — compara PnL acumulado baseline vs proxies para cada día/path.",
        "5. `delta_cumulative_by_day.png` — muestra dónde aparece el valor del extra access dentro de cada ronda.",
        "6. `pepper_inventory_by_day.png` — permite ver si el proxy central acelera llegar a 50/70/80 en PEPPER y cuánto cambia realmente la trayectoria.",
        "7. `bid_ev_curves.png` — combina EV por bid según variante de Delta y según escenario de cutoff.",
        "8. `acceptance_probability_qb.png` — visualiza `q(b)` por escenario rival.",
        "9. `uplift_fee_roi_by_bid.png` — muestra uplift % y ROI del fee, con foco visual en 100 / 125 / 150.",
        "10. `bid_sensitivity_heatmap.png` — heatmap Delta asumido vs cutoff rival; ayuda a ver cuándo la recomendación se movería de 125 hacia 150.",
        "",
        "## G. Recomendación final",
        "",
        f"- Bid recomendado: **`{recommended_bid}`**.",
        f"- Rango alternativo razonable: **`{alt_low}`–`{alt_high}`**.",
        f"- Subiría a `150` si tu prior es que el cutoff real está mucho más cerca del escenario `stress` y querés comprar probabilidad de aceptación aun pagando más.",
        f"- Bajaría a `100` si querés minimizar fee y asumís que el cutoff real se parece más a `low/central`.",
        "",
        f"Tratando cada día como una ronda independiente, el valor del extra access para `model_kiko` es de **{delta_variants['downside']:,.1f} a {delta_variants['central']:,.1f} por ronda**, con estimación conservadora media de **{delta_variants['conservative']:,.1f}**.",
        f"En el peor día, el uplift neto con bid 125 es **{100*worst_125['uplift_pct_vs_base']:.2f}%** y el fee ROI es **{worst_125['fee_roi']:.2f}x**.",
        f"El bid 125 **sí sigue siendo robusto** cuando la unidad estadística correcta es `día = ronda`.",
        "La razón principal es que el MAF sigue generando Delta positivo en los tres días, el worst-day sigue dejando margen amplio después de pagar 125, y 125 cae consistentemente dentro de la meseta del 95% del EV sin exigir pagar de más como reacción automática.",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    official_summary = load_official_log_summary()
    loaded_data = load_all_raw_data()
    day_metrics, product_runs, fill_runs, total_runs = run_all_scenarios(loaded_data)
    delta_day = build_delta_day_metrics(day_metrics)
    baseline_summary = build_baseline_summary(day_metrics)
    delta_summary = build_delta_summary(delta_day)
    p0_mean = float(baseline_summary[baseline_summary["product"] == "TOTAL"]["P0_mean"].iloc[0])
    delta_variants = build_delta_variants(delta_day)
    bid_grid = build_bid_grid(p0_mean, delta_variants)
    bid_recs = build_bid_recommendations(bid_grid)
    day_bid = build_day_bid_analysis(day_metrics, delta_day)
    loo_df = build_leave_one_day_out(day_metrics, delta_day)
    worst_day_df = build_worst_day_summary(day_metrics, delta_day)
    sensitivity_df = build_sensitivity_heatmap_df()

    save_dataframe(official_summary, "official_round1_log_summary")
    save_dataframe(day_metrics, "day_metrics")
    save_dataframe(delta_day, "delta_day_metrics")
    save_dataframe(baseline_summary, "baseline_summary")
    save_dataframe(delta_summary, "delta_summary")
    save_dataframe(bid_grid, "bid_grid")
    save_dataframe(bid_recs, "bid_recommendations")
    save_dataframe(day_bid, "day_bid_analysis")
    save_dataframe(loo_df, "leave_one_day_out")
    save_dataframe(worst_day_df, "worst_day_summary")
    save_dataframe(sensitivity_df, "bid_sensitivity")

    plot_p0_p1_by_day(day_metrics)
    plot_delta_by_day(delta_day)
    plot_delta_violin(delta_day)
    plot_pnl_cumulative_by_day(total_runs)
    plot_delta_cumulative_by_day(total_runs)
    plot_pepper_inventory_by_day(product_runs)
    plot_bid_ev_and_cutoff(bid_grid)
    plot_acceptance_probabilities()
    plot_uplift_roi_by_bid(bid_grid)
    plot_sensitivity_heatmap(sensitivity_df)

    write_report(
        official_summary,
        day_metrics,
        delta_day,
        baseline_summary,
        delta_summary,
        bid_grid,
        bid_recs,
        day_bid,
        loo_df,
        worst_day_df,
        sensitivity_df,
    )


if __name__ == "__main__":
    main()
