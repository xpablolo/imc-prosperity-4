from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[2]
ROUND_1_TOOLS = ROOT / "round_1" / "tools"
ROUND_2_TOOLS = ROOT / "round_2" / "tools"
ROUND_2_MODELS = ROOT / "round_2" / "models"
RESULTS_DIR = ROOT / "round_2" / "results" / "kiko_maf_rigorous"
PLOTS_DIR = RESULTS_DIR / "plots"
REPORT_PATH = RESULTS_DIR / "round2_model_kiko_maf_rigorous.md"

sys.path.insert(0, str(ROUND_2_TOOLS))
sys.path.insert(0, str(ROUND_2_MODELS))
sys.path.insert(0, str(ROUND_1_TOOLS))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402

MODEL_NAME = "model_kiko"
MODEL_PATH = ROOT / "round_2" / "models" / "model_kiko.py"
ROUND_NAME = "round_2"
DAYS = (-1, 0, 1)
DAY_TO_IDX = {day: idx for idx, day in enumerate(DAYS)}
PRODUCTS = tuple(ag.PRODUCTS)
POSITION_LIMITS = ag.POSITION_LIMITS
DAY_MAX_TS = 999_900
DAY_HORIZON = 1_000_000
PLOT_DPI = 200

BID_GRID = [0, 10, 20, 30, 40, 50, 60, 75, 100, 125, 150, 175, 200, 250, 300]
CORE_BID_GRID = [0, 10, 20, 30, 40, 50, 60, 75, 100, 125, 150, 200]

PRODUCT_LABELS = {
    "ASH_COATED_OSMIUM": "ASH",
    "INTARIAN_PEPPER_ROOT": "PEPPER",
    "TOTAL": "TOTAL",
}

SCENARIO_ORDER = [
    "baseline",
    "uniform_depth_125",
    "front_bias_depth_25",
    "uniform_depth_trade_125",
]
SCENARIO_LABELS = {
    "baseline": "Baseline",
    "uniform_depth_125": "Uniform depth +25%",
    "front_bias_depth_25": "Front-biased depth +25%",
    "uniform_depth_trade_125": "Depth +25% + trades +25%",
}
SCENARIO_DESCRIPTIONS = {
    "baseline": "Mercado observado en el dataset local, sin market access extra.",
    "uniform_depth_125": "Proxy conservador: escala +25% el volumen visible en todos los niveles, sin tocar market trades.",
    "front_bias_depth_25": "Proxy central: concentra la liquidez extra cerca del touch (L1/L2/L3) manteniendo la microestructura de precios.",
    "uniform_depth_trade_125": "Upper bound: escala +25% profundidad visible y +25% market trades. No se usa como estimación central del bid óptimo.",
}

PALETTE = {
    "baseline": "#111827",
    "uniform_depth_125": "#2563EB",
    "front_bias_depth_25": "#7C3AED",
    "uniform_depth_trade_125": "#DC2626",
    "risk_adjusted": "#0F766E",
    "weighted": "#0F766E",
    "low": "#94A3B8",
    "central": "#2563EB",
    "high": "#D97706",
    "stress": "#DC2626",
}

INVENTORY_BIN_ORDER = ["<0", "0-20", "20-40", "40-50", "50-60", "60-70", "70-80", "80"]


@dataclass(frozen=True)
class CutoffScenario:
    name: str
    label: str
    median_bid: float
    slope: float
    weight: float
    description: str


CUTOFF_SCENARIOS: tuple[CutoffScenario, ...] = (
    CutoffScenario(
        name="low",
        label="Competencia baja",
        median_bid=20.0,
        slope=6.0,
        weight=0.15,
        description="Campo poco agresivo: el cutoff efectivo está en la zona de los 20s.",
    ),
    CutoffScenario(
        name="central",
        label="Central",
        median_bid=45.0,
        slope=9.0,
        weight=0.40,
        description="Escenario base: cutoff en torno a 45 con transición relativamente suave.",
    ),
    CutoffScenario(
        name="high",
        label="Competencia alta",
        median_bid=80.0,
        slope=14.0,
        weight=0.30,
        description="Escenario competitivo serio: muchos equipos dispuestos a pagar en la zona 70–100.",
    ),
    CutoffScenario(
        name="stress",
        label="Stress muy alto",
        median_bid=120.0,
        slope=20.0,
        weight=0.15,
        description="Stress test duro: la mediana rival ya se mueve a tres cifras.",
    ),
)

PROXY_LOOKUP = {proxy.name: proxy for proxy in ag.PROXIES}


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


def markdown_table(df: pd.DataFrame, float_fmt: str = ".2f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
    display_headers = [str(col) for col in headers]
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
    return "\n".join(
        [
            "| " + " | ".join(display_headers) + " |",
            "| " + " | ".join(["---"] * len(display_headers)) + " |",
            *rows,
        ]
    )


def load_all_raw_data() -> Dict[str, Dict[int, ag.LoadedDayData]]:
    return {
        product: {day: ag.load_day_data(ROUND_NAME, day, product) for day in DAYS}
        for product in PRODUCTS
    }


def logistic_acceptance_probability(bid: float, scenario: CutoffScenario) -> float:
    return 1.0 / (1.0 + math.exp(-(float(bid) - scenario.median_bid) / scenario.slope))


def q_weighted(bid: float) -> float:
    return sum(s.weight * logistic_acceptance_probability(bid, s) for s in CUTOFF_SCENARIOS)


def pct(value: float) -> float:
    return 100.0 * float(value)


def inventory_bin(position: float) -> str:
    if position < 0:
        return "<0"
    if position < 20:
        return "0-20"
    if position < 40:
        return "20-40"
    if position < 50:
        return "40-50"
    if position < 60:
        return "50-60"
    if position < 70:
        return "60-70"
    if position < 80:
        return "70-80"
    return "80"


def add_day_offsets(df: pd.DataFrame, pnl_col: str) -> pd.DataFrame:
    pieces: List[pd.DataFrame] = []
    offset = 0.0
    for day in DAYS:
        sub = df[df["day"] == day].copy().sort_values("timestamp")
        if sub.empty:
            continue
        sub["sample_global_ts"] = DAY_TO_IDX[day] * DAY_HORIZON + sub["timestamp"]
        sub["sample_pnl"] = sub[pnl_col] + offset
        offset += float(sub[pnl_col].iloc[-1])
        pieces.append(sub)
    out = pd.concat(pieces, ignore_index=True)
    out["sample_drawdown"] = out["sample_pnl"] - out["sample_pnl"].cummax()
    return out


def compute_time_to_threshold(results_df: pd.DataFrame, threshold: int) -> float:
    hit = results_df.loc[results_df["position"] >= threshold, "timestamp"]
    return float(hit.iloc[0]) if not hit.empty else np.nan


def summarize_fill_metrics(fills_df: pd.DataFrame) -> Dict[str, float]:
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


def build_product_summary(
    scenario: str,
    product: str,
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> Dict[str, float | str]:
    sample_path = add_day_offsets(results_df, pnl_col="pnl")
    daily_totals = results_df.groupby("day", sort=True)["pnl"].last().astype(float)
    fill_metrics = summarize_fill_metrics(fills_df)
    row: Dict[str, float | str] = {
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS[scenario],
        "product": product,
        "product_label": PRODUCT_LABELS[product],
        "P0": np.nan,
        "P1": float(daily_totals.sum()),
        "total_pnl": float(daily_totals.sum()),
        "pnl_per_1m": float(daily_totals.mean()),
        "max_drawdown": float(sample_path["sample_drawdown"].min()),
        "avg_abs_position": float(results_df["position"].abs().mean()),
        "avg_position": float(results_df["position"].mean()),
        "max_abs_position": float(results_df["position"].abs().max()),
        "pct_time_abs_ge_60": float((results_df["position"].abs() >= 60).mean()),
        "pct_time_abs_ge_70": float((results_df["position"].abs() >= 70).mean()),
        "pct_time_at_limit": float((results_df["position"].abs() >= POSITION_LIMITS[product]).mean()),
        "daily_mean_pnl": float(daily_totals.mean()),
        "daily_std_pnl": float(daily_totals.std(ddof=1)) if len(daily_totals) > 1 else 0.0,
        "min_day_pnl": float(daily_totals.min()),
        **fill_metrics,
    }
    for day in DAYS:
        row[f"day_{day}_pnl"] = float(daily_totals.loc[day])
    if product == "INTARIAN_PEPPER_ROOT":
        for threshold in (50, 70, 80):
            values = [compute_time_to_threshold(results_df[results_df["day"] == day], threshold) for day in DAYS]
            row[f"time_to_{threshold}_mean"] = float(np.nanmean(values))
            row[f"time_to_{threshold}_median"] = float(np.nanmedian(values))
        row["pct_time_pos_ge_70"] = float((results_df["position"] >= 70).mean())
        row["pct_time_pos_at_80"] = float((results_df["position"] >= 80).mean())
    return row


def merge_combined_day(product_day_results: Mapping[str, pd.DataFrame], day: int) -> pd.DataFrame:
    merged: Optional[pd.DataFrame] = None
    for product, frame in product_day_results.items():
        sub = frame[["timestamp", "pnl", "position", "mid_price"]].copy()
        label = PRODUCT_LABELS[product].lower()
        sub = sub.rename(
            columns={
                "pnl": f"pnl_{label}",
                "position": f"position_{label}",
                "mid_price": f"mid_{label}",
            }
        )
        merged = sub if merged is None else merged.merge(sub, on="timestamp", how="outer")
    assert merged is not None
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    pnl_cols = [col for col in merged.columns if col.startswith("pnl_")]
    merged[pnl_cols] = merged[pnl_cols].ffill().fillna(0.0)
    merged["total_pnl"] = merged[pnl_cols].sum(axis=1)
    merged["day"] = day
    merged["sample_global_ts"] = DAY_TO_IDX[day] * DAY_HORIZON + merged["timestamp"]
    merged["drawdown"] = merged["total_pnl"] - merged["total_pnl"].cummax()
    return merged


def build_total_summary(
    scenario: str,
    combined_df: pd.DataFrame,
    fills_all_df: pd.DataFrame,
) -> Dict[str, float | str]:
    sample_path = add_day_offsets(combined_df, pnl_col="total_pnl")
    daily_totals = combined_df.groupby("day", sort=True)["total_pnl"].last().astype(float)
    fill_metrics = summarize_fill_metrics(fills_all_df)
    row: Dict[str, float | str] = {
        "scenario": scenario,
        "scenario_label": SCENARIO_LABELS[scenario],
        "product": "TOTAL",
        "product_label": "TOTAL",
        "P0": np.nan,
        "P1": float(daily_totals.sum()),
        "total_pnl": float(daily_totals.sum()),
        "pnl_per_1m": float(daily_totals.mean()),
        "max_drawdown": float(sample_path["sample_drawdown"].min()),
        "avg_abs_position": np.nan,
        "avg_position": np.nan,
        "max_abs_position": np.nan,
        "pct_time_abs_ge_60": np.nan,
        "pct_time_abs_ge_70": np.nan,
        "pct_time_at_limit": np.nan,
        "daily_mean_pnl": float(daily_totals.mean()),
        "daily_std_pnl": float(daily_totals.std(ddof=1)) if len(daily_totals) > 1 else 0.0,
        "min_day_pnl": float(daily_totals.min()),
        **fill_metrics,
    }
    for day in DAYS:
        row[f"day_{day}_pnl"] = float(daily_totals.loc[day])
    return row


def run_scenario(
    scenario: str,
    proxy: Optional[ag.ProxySpec],
    loaded_data: Mapping[str, Mapping[int, ag.LoadedDayData]],
) -> tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    product_day_results: Dict[str, List[pd.DataFrame]] = {product: [] for product in PRODUCTS}
    product_day_fills: Dict[str, List[pd.DataFrame]] = {product: [] for product in PRODUCTS}
    day_total_frames: List[pd.DataFrame] = []

    for day in DAYS:
        per_product_day: Dict[str, pd.DataFrame] = {}
        fills_frames: List[pd.DataFrame] = []
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
            results_df = results_df.copy()
            results_df["scenario"] = scenario
            results_df["product"] = product
            results_df["sample_global_ts"] = DAY_TO_IDX[day] * DAY_HORIZON + results_df["timestamp"]
            product_day_results[product].append(results_df)
            per_product_day[product] = results_df
            if not fills_df.empty:
                fills_df = fills_df.copy()
                fills_df["scenario"] = scenario
                fills_df["product"] = product
                fills_df["sample_global_ts"] = DAY_TO_IDX[day] * DAY_HORIZON + fills_df["timestamp"]
            else:
                fills_df = pd.DataFrame(
                    columns=["day", "timestamp", "global_ts", "product", "side", "price", "quantity", "source", "scenario", "sample_global_ts"]
                )
            product_day_fills[product].append(fills_df)
            fills_frames.append(fills_df)

        combined_day = merge_combined_day(per_product_day, day)
        combined_day["scenario"] = scenario
        day_total_frames.append(combined_day)

    product_results = {product: pd.concat(frames, ignore_index=True).sort_values(["day", "timestamp"]).reset_index(drop=True) for product, frames in product_day_results.items()}
    product_fills = {product: pd.concat(frames, ignore_index=True).sort_values(["day", "timestamp"]).reset_index(drop=True) for product, frames in product_day_fills.items()}
    combined_df = pd.concat(day_total_frames, ignore_index=True).sort_values(["day", "timestamp"]).reset_index(drop=True)
    combined_fills = pd.concat([df for frames in product_day_fills.values() for df in frames], ignore_index=True)

    summary_rows = [build_product_summary(scenario, product, product_results[product], product_fills[product]) for product in PRODUCTS]
    summary_rows.append(build_total_summary(scenario, combined_df, combined_fills))
    summary_df = pd.DataFrame(summary_rows)
    return summary_df, product_results, product_fills, combined_df, combined_fills


def build_daily_metrics(
    scenario_runs: Mapping[str, Dict[str, pd.DataFrame]],
    total_runs: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    rows: List[Dict[str, float | str | int]] = []
    for scenario in SCENARIO_ORDER:
        for product in PRODUCTS:
            frame = scenario_runs[scenario][product]
            for day in DAYS:
                sub = frame[frame["day"] == day].copy()
                rows.append(
                    {
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "product": product,
                        "product_label": PRODUCT_LABELS[product],
                        "day": day,
                        "day_pnl": float(sub["pnl"].iloc[-1]),
                        "avg_position": float(sub["position"].mean()),
                        "avg_abs_position": float(sub["position"].abs().mean()),
                        "max_abs_position": float(sub["position"].abs().max()),
                        "pct_time_abs_ge_60": float((sub["position"].abs() >= 60).mean()),
                        "pct_time_abs_ge_70": float((sub["position"].abs() >= 70).mean()),
                        "pct_time_at_limit": float((sub["position"].abs() >= POSITION_LIMITS[product]).mean()),
                        "final_position": float(sub["position"].iloc[-1]),
                        "fill_count": np.nan,
                    }
                )
                if product == "INTARIAN_PEPPER_ROOT":
                    rows[-1]["time_to_50"] = compute_time_to_threshold(sub, 50)
                    rows[-1]["time_to_70"] = compute_time_to_threshold(sub, 70)
                    rows[-1]["time_to_80"] = compute_time_to_threshold(sub, 80)
                    rows[-1]["pct_time_pos_ge_70"] = float((sub["position"] >= 70).mean())
                    rows[-1]["pct_time_pos_at_80"] = float((sub["position"] >= 80).mean())
        total_df = total_runs[scenario]
        for day in DAYS:
            sub = total_df[total_df["day"] == day].copy()
            rows.append(
                {
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "product": "TOTAL",
                    "product_label": "TOTAL",
                    "day": day,
                    "day_pnl": float(sub["total_pnl"].iloc[-1]),
                    "avg_position": np.nan,
                    "avg_abs_position": np.nan,
                    "max_abs_position": np.nan,
                    "pct_time_abs_ge_60": np.nan,
                    "pct_time_abs_ge_70": np.nan,
                    "pct_time_at_limit": np.nan,
                    "final_position": np.nan,
                    "fill_count": np.nan,
                }
            )
    return pd.DataFrame(rows)


def add_buckets(df: pd.DataFrame, timestamp_col: str = "timestamp", n_buckets: int = 10) -> pd.DataFrame:
    out = df.copy()
    bucket_size = DAY_HORIZON / n_buckets
    out["bucket"] = np.minimum(n_buckets, np.floor(out[timestamp_col] / bucket_size).astype(int) + 1)
    return out


def build_bucket_metrics(
    scenario_runs: Mapping[str, Dict[str, pd.DataFrame]],
    total_runs: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    rows: List[Dict[str, float | str | int]] = []
    for scenario in SCENARIO_ORDER:
        for product in PRODUCTS:
            frame = add_buckets(scenario_runs[scenario][product])
            grouped = (
                frame.groupby(["day", "bucket"], as_index=False)
                .agg(last_pnl=("pnl", "last"), avg_position=("position", "mean"), avg_abs_position=("position", lambda s: float(s.abs().mean())))
                .sort_values(["day", "bucket"])
            )
            grouped["bucket_pnl"] = grouped.groupby("day")["last_pnl"].diff().fillna(grouped["last_pnl"])
            for _, row in grouped.iterrows():
                rows.append(
                    {
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "product": product,
                        "product_label": PRODUCT_LABELS[product],
                        "day": int(row["day"]),
                        "bucket": int(row["bucket"]),
                        "bucket_pnl": float(row["bucket_pnl"]),
                        "avg_position": float(row["avg_position"]),
                        "avg_abs_position": float(row["avg_abs_position"]),
                    }
                )
        total = add_buckets(total_runs[scenario])
        grouped = (
            total.groupby(["day", "bucket"], as_index=False)
            .agg(last_pnl=("total_pnl", "last"))
            .sort_values(["day", "bucket"])
        )
        grouped["bucket_pnl"] = grouped.groupby("day")["last_pnl"].diff().fillna(grouped["last_pnl"])
        for _, row in grouped.iterrows():
            rows.append(
                {
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "product": "TOTAL",
                    "product_label": "TOTAL",
                    "day": int(row["day"]),
                    "bucket": int(row["bucket"]),
                    "bucket_pnl": float(row["bucket_pnl"]),
                    "avg_position": np.nan,
                    "avg_abs_position": np.nan,
                }
            )
    return pd.DataFrame(rows)


def build_delta_curves(total_runs: Mapping[str, pd.DataFrame], product_runs: Mapping[str, Dict[str, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    total_rows: List[pd.DataFrame] = []
    product_rows: List[pd.DataFrame] = []
    base_total = total_runs["baseline"]
    for scenario in SCENARIO_ORDER:
        if scenario == "baseline":
            continue
        merged_total = base_total[["day", "timestamp", "total_pnl"]].merge(
            total_runs[scenario][["day", "timestamp", "total_pnl"]],
            on=["day", "timestamp"],
            suffixes=("_base", "_proxy"),
        )
        merged_total["scenario"] = scenario
        merged_total["delta"] = merged_total["total_pnl_proxy"] - merged_total["total_pnl_base"]
        total_rows.append(merged_total)

        for product in PRODUCTS:
            merged_product = product_runs["baseline"][product][["day", "timestamp", "pnl"]].merge(
                product_runs[scenario][product][["day", "timestamp", "pnl"]],
                on=["day", "timestamp"],
                suffixes=("_base", "_proxy"),
            )
            merged_product["scenario"] = scenario
            merged_product["product"] = product
            merged_product["delta"] = merged_product["pnl_proxy"] - merged_product["pnl_base"]
            product_rows.append(merged_product)
    total_df = pd.concat(total_rows, ignore_index=True)
    total_df["delta_increment"] = total_df.groupby(["scenario", "day"])["delta"].diff().fillna(total_df["delta"])
    total_df["rel_progress"] = total_df["timestamp"] / DAY_MAX_TS
    product_df = pd.concat(product_rows, ignore_index=True)
    product_df["delta_increment"] = product_df.groupby(["scenario", "product", "day"])["delta"].diff().fillna(product_df["delta"])
    product_df["rel_progress"] = product_df["timestamp"] / DAY_MAX_TS
    return total_df, product_df


def build_inventory_distribution(product_runs: Mapping[str, Dict[str, pd.DataFrame]]) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    for scenario in SCENARIO_ORDER:
        pepper = product_runs[scenario]["INTARIAN_PEPPER_ROOT"].copy()
        pepper["inventory_bin"] = pepper["position"].apply(inventory_bin)
        dist = pepper["inventory_bin"].value_counts(normalize=True)
        for inv_bin in INVENTORY_BIN_ORDER:
            rows.append(
                {
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "inventory_bin": inv_bin,
                    "pct_time": float(dist.get(inv_bin, 0.0)),
                }
            )
    return pd.DataFrame(rows)


def build_delta_vs_inventory(total_delta_df: pd.DataFrame, product_runs: Mapping[str, Dict[str, pd.DataFrame]]) -> pd.DataFrame:
    base_pepper = product_runs["baseline"]["INTARIAN_PEPPER_ROOT"][["day", "timestamp", "position"]].rename(columns={"position": "baseline_pepper_position"})
    merged = total_delta_df.merge(base_pepper, on=["day", "timestamp"], how="left")
    merged["inventory_bin"] = merged["baseline_pepper_position"].apply(inventory_bin)
    summary = (
        merged.groupby(["scenario", "inventory_bin"], as_index=False)
        .agg(
            mean_delta_increment=("delta_increment", "mean"),
            median_delta_increment=("delta_increment", "median"),
            total_delta=("delta_increment", "sum"),
            observations=("delta_increment", "size"),
        )
    )
    summary["inventory_bin"] = pd.Categorical(summary["inventory_bin"], INVENTORY_BIN_ORDER, ordered=True)
    summary = summary.sort_values(["scenario", "inventory_bin"]).reset_index(drop=True)
    return summary


def fit_shape_models(x: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []

    def rmse(yhat: np.ndarray) -> float:
        return float(np.sqrt(np.mean((y - yhat) ** 2)))

    y_linear = x
    rows.append({"model": "linear", "rmse": rmse(y_linear), "param_1": np.nan, "param_2": np.nan})

    y_sqrt = np.sqrt(x)
    rows.append({"model": "sqrt", "rmse": rmse(y_sqrt), "param_1": np.nan, "param_2": np.nan})

    best_log = {"rmse": float("inf"), "a": np.nan}
    for a in np.logspace(-2, 2, 400):
        yhat = np.log1p(a * x) / np.log1p(a)
        score = rmse(yhat)
        if score < best_log["rmse"]:
            best_log = {"rmse": score, "a": float(a)}
    rows.append({"model": "log", "rmse": best_log["rmse"], "param_1": best_log["a"], "param_2": np.nan})

    best_capped = {"rmse": float("inf"), "c": np.nan}
    for c in np.linspace(0.15, 1.0, 200):
        yhat = np.minimum(x / c, 1.0)
        score = rmse(yhat)
        if score < best_capped["rmse"]:
            best_capped = {"rmse": score, "c": float(c)}
    rows.append({"model": "capped_linear", "rmse": best_capped["rmse"], "param_1": best_capped["c"], "param_2": np.nan})

    best_piecewise = {"rmse": float("inf"), "k": np.nan, "y_k": np.nan}
    for k in np.linspace(0.15, 0.85, 29):
        for y_k in np.linspace(max(k + 0.02, 0.20), 0.98, 200):
            early = (y_k / k) * x
            late = y_k + (1.0 - y_k) * (x - k) / (1.0 - k)
            yhat = np.where(x <= k, early, late)
            score = rmse(yhat)
            if score < best_piecewise["rmse"]:
                best_piecewise = {"rmse": score, "k": float(k), "y_k": float(y_k)}
    rows.append(
        {
            "model": "piecewise_saturation",
            "rmse": best_piecewise["rmse"],
            "param_1": best_piecewise["k"],
            "param_2": best_piecewise["y_k"],
        }
    )

    return pd.DataFrame(rows).sort_values("rmse").reset_index(drop=True)


def best_model_curve(model_row: Mapping[str, float | str], x: np.ndarray) -> np.ndarray:
    model = str(model_row["model"])
    p1 = float(model_row["param_1"]) if not pd.isna(model_row["param_1"]) else np.nan
    p2 = float(model_row["param_2"]) if not pd.isna(model_row["param_2"]) else np.nan
    if model == "linear":
        return x
    if model == "sqrt":
        return np.sqrt(x)
    if model == "log":
        return np.log1p(p1 * x) / np.log1p(p1)
    if model == "capped_linear":
        return np.minimum(x / p1, 1.0)
    if model == "piecewise_saturation":
        early = (p2 / p1) * x
        late = p2 + (1.0 - p2) * (x - p1) / (1.0 - p1)
        return np.where(x <= p1, early, late)
    raise ValueError(model)


def build_curve_fit_table(total_delta_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    fit_rows: List[pd.DataFrame] = []
    normalized_rows: List[pd.DataFrame] = []
    for scenario in ["uniform_depth_125", "front_bias_depth_25"]:
        mean_curve = (
            total_delta_df[total_delta_df["scenario"] == scenario]
            .groupby("timestamp", as_index=False)
            .agg(mean_delta=("delta", "mean"), min_delta=("delta", "min"), max_delta=("delta", "max"))
            .sort_values("timestamp")
        )
        final_delta = float(mean_curve["mean_delta"].iloc[-1])
        mean_curve["x"] = mean_curve["timestamp"] / DAY_MAX_TS
        mean_curve["y_norm"] = mean_curve["mean_delta"] / final_delta if final_delta else 0.0
        fits = fit_shape_models(mean_curve["x"].to_numpy(), mean_curve["y_norm"].to_numpy())
        fits["scenario"] = scenario
        fit_rows.append(fits)
        normalized_rows.append(mean_curve.assign(scenario=scenario, final_delta=final_delta))
    fit_df = pd.concat(fit_rows, ignore_index=True)
    normalized_df = pd.concat(normalized_rows, ignore_index=True)
    fit_summary = (
        fit_df.groupby("model", as_index=False)
        .agg(avg_rmse=("rmse", "mean"), max_rmse=("rmse", "max"))
        .sort_values(["avg_rmse", "max_rmse"])
        .reset_index(drop=True)
    )
    return fit_df, normalized_df.merge(fit_summary, on=None, how="cross") if False else normalized_df


def build_bid_grid(
    p0_1m: float,
    delta_1m: Mapping[str, float],
    risk_adjusted_delta: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    delta_map = {
        "risk_adjusted": risk_adjusted_delta,
        "conservative": delta_1m["conservative"],
        "central": delta_1m["central"],
    }
    rows: List[Dict[str, float | str | int]] = []
    for delta_name, delta_value in delta_map.items():
        for bid in BID_GRID:
            row: Dict[str, float | str | int] = {
                "delta_name": delta_name,
                "delta_value": float(delta_value),
                "bid": int(bid),
                "P0_1M": float(p0_1m),
                "net_gain_if_accepted": float(delta_value - bid),
                "uplift_pct_vs_base_if_accepted": float((delta_value - bid) / p0_1m),
                "fee_roi_if_accepted": float((delta_value - bid) / bid) if bid > 0 else np.nan,
                "q_weighted": q_weighted(bid),
                "EV_weighted": float(p0_1m + q_weighted(bid) * (delta_value - bid)),
                "EV_uplift_weighted": float(q_weighted(bid) * (delta_value - bid)),
            }
            pessimistic = 0.0
            for scenario in CUTOFF_SCENARIOS:
                q = logistic_acceptance_probability(bid, scenario)
                row[f"q_{scenario.name}"] = q
                row[f"EV_{scenario.name}"] = float(p0_1m + q * (delta_value - bid))
                row[f"EV_uplift_{scenario.name}"] = float(q * (delta_value - bid))
                if scenario.name in {"high", "stress"}:
                    pessimistic += (0.6 if scenario.name == "high" else 0.4) * q * (delta_value - bid)
            row["EV_uplift_pessimistic"] = float(pessimistic)
            row["EV_pessimistic"] = float(p0_1m + pessimistic)
            rows.append(row)
    bid_df = pd.DataFrame(rows).sort_values(["delta_name", "bid"]).reset_index(drop=True)

    plateau_rows: List[Dict[str, float | int | str]] = []
    risk_sub = bid_df[bid_df["delta_name"] == "risk_adjusted"].copy()
    max_weighted = float(risk_sub["EV_uplift_weighted"].max())
    max_pessimistic = float(risk_sub["EV_uplift_pessimistic"].max())
    best_row = risk_sub.loc[risk_sub["EV_uplift_weighted"].idxmax()]
    plateau_rows.append(
        {
            "metric": "weighted_risk_adjusted",
            "best_bid": int(best_row["bid"]),
            "best_ev_uplift": max_weighted,
            "smallest_bid_within_95pct": int(risk_sub.loc[risk_sub["EV_uplift_weighted"] >= 0.95 * max_weighted, "bid"].min()),
            "smallest_bid_within_90pct": int(risk_sub.loc[risk_sub["EV_uplift_weighted"] >= 0.90 * max_weighted, "bid"].min()),
        }
    )
    best_pess = risk_sub.loc[risk_sub["EV_uplift_pessimistic"].idxmax()]
    plateau_rows.append(
        {
            "metric": "pessimistic_risk_adjusted",
            "best_bid": int(best_pess["bid"]),
            "best_ev_uplift": max_pessimistic,
            "smallest_bid_within_95pct": int(risk_sub.loc[risk_sub["EV_uplift_pessimistic"] >= 0.95 * max_pessimistic, "bid"].min()),
            "smallest_bid_within_90pct": int(risk_sub.loc[risk_sub["EV_uplift_pessimistic"] >= 0.90 * max_pessimistic, "bid"].min()),
        }
    )
    plateau_df = pd.DataFrame(plateau_rows)

    sensitivity_rows: List[Dict[str, float | int]] = []
    delta_grid = np.arange(400, 2201, 100)
    cutoff_medians = np.arange(20, 151, 10)
    for delta_value in delta_grid:
        for median in cutoff_medians:
            slope = max(6.0, median * 0.18)
            ev_rows = []
            for bid in BID_GRID:
                q = 1.0 / (1.0 + math.exp(-(float(bid) - median) / slope))
                ev = q * (float(delta_value) - bid)
                ev_rows.append((bid, ev))
            ev_df = pd.DataFrame(ev_rows, columns=["bid", "ev"])
            max_ev = float(ev_df["ev"].max())
            best_bid = int(ev_df.loc[ev_df["ev"].idxmax(), "bid"])
            plateau_95 = int(ev_df.loc[ev_df["ev"] >= 0.95 * max_ev, "bid"].min())
            sensitivity_rows.append(
                {
                    "delta_1m": float(delta_value),
                    "cutoff_median": float(median),
                    "cutoff_slope": float(slope),
                    "best_bid": best_bid,
                    "plateau95_bid": plateau_95,
                }
            )
    sensitivity_df = pd.DataFrame(sensitivity_rows)
    return bid_df, plateau_df, sensitivity_df


def save_dataframe(df: pd.DataFrame, name: str) -> None:
    df.to_csv(RESULTS_DIR / f"{name}.csv", index=False)


def plot_pnl_cumulative(total_runs: Mapping[str, pd.DataFrame], product_runs: Mapping[str, Dict[str, pd.DataFrame]]) -> None:
    configure_style()
    fig, axes = plt.subplots(3, 1, figsize=(15, 16), sharex=True)

    for scenario in SCENARIO_ORDER:
        total = add_day_offsets(total_runs[scenario], pnl_col="total_pnl")
        axes[0].plot(total["sample_global_ts"], total["sample_pnl"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.4)
    axes[0].set_title("PnL acumulado total — baseline vs proxies")
    axes[0].set_ylabel("PnL acumulado")
    axes[0].legend(ncol=2, fontsize=10)

    for scenario in SCENARIO_ORDER:
        ash = add_day_offsets(product_runs[scenario]["ASH_COATED_OSMIUM"], pnl_col="pnl")
        axes[1].plot(ash["sample_global_ts"], ash["sample_pnl"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.2)
    axes[1].set_title("PnL acumulado — ASH")
    axes[1].set_ylabel("PnL acumulado")

    for scenario in SCENARIO_ORDER:
        pepper = add_day_offsets(product_runs[scenario]["INTARIAN_PEPPER_ROOT"], pnl_col="pnl")
        axes[2].plot(pepper["sample_global_ts"], pepper["sample_pnl"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.2)
    axes[2].set_title("PnL acumulado — PEPPER")
    axes[2].set_xlabel("Tiempo de muestra (3 días independientes, concatenados)")
    axes[2].set_ylabel("PnL acumulado")

    fig.suptitle("model_kiko — PnL acumulado baseline vs proxies", x=0.01, ha="left", fontsize=22)
    fig.savefig(PLOTS_DIR / "pnl_cumulative_baseline_vs_proxies.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_curves(total_delta_df: pd.DataFrame) -> None:
    configure_style()
    fig, ax = plt.subplots(figsize=(14, 7))
    for scenario in ["uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]:
        sub = (
            total_delta_df[total_delta_df["scenario"] == scenario]
            .groupby("timestamp", as_index=False)
            .agg(mean_delta=("delta", "mean"), min_delta=("delta", "min"), max_delta=("delta", "max"))
            .sort_values("timestamp")
        )
        ax.plot(sub["timestamp"], sub["mean_delta"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.5)
        ax.fill_between(sub["timestamp"], sub["min_delta"], sub["max_delta"], color=PALETTE[scenario], alpha=0.10)
    ax.axhline(0, color="#6B7280", linewidth=1.0)
    ax.set_title("Curva acumulada Δ(t) = P1(t) - P0(t)")
    ax.set_xlabel("Timestamp dentro del día (~0 → 999900)")
    ax.set_ylabel("Delta acumulado promedio por día")
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "delta_cumulative_curve.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_incremental_blocks(bucket_df: pd.DataFrame) -> None:
    configure_style()
    baseline = bucket_df[bucket_df["scenario"] == "baseline"][ ["product", "day", "bucket", "bucket_pnl"] ].rename(columns={"bucket_pnl": "bucket_pnl_base"})
    work = bucket_df.merge(baseline, on=["product", "day", "bucket"], how="left")
    work = work[work["scenario"] != "baseline"].copy()
    work["delta_bucket_pnl"] = work["bucket_pnl"] - work["bucket_pnl_base"]
    plot_df = (
        work[work["product"] == "TOTAL"]
        .groupby(["scenario", "bucket"], as_index=False)
        .agg(mean_delta_bucket=("delta_bucket_pnl", "mean"))
    )

    fig, ax = plt.subplots(figsize=(14, 7))
    width = 0.22
    centers = np.arange(1, 11)
    for idx, scenario in enumerate(["uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]):
        sub = plot_df[plot_df["scenario"] == scenario].sort_values("bucket")
        ax.bar(centers + (idx - 1) * width, sub["mean_delta_bucket"], width=width, label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], alpha=0.92)
    ax.axhline(0, color="#6B7280", linewidth=1.0)
    ax.set_title("Delta incremental por bloques temporales (promedio por día)")
    ax.set_xlabel("Bucket temporal dentro del día")
    ax.set_ylabel("Delta incremental promedio")
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "delta_incremental_blocks.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_pepper_inventory(product_runs: Mapping[str, Dict[str, pd.DataFrame]]) -> None:
    configure_style()
    fig, ax = plt.subplots(figsize=(14, 7))
    for scenario in SCENARIO_ORDER:
        pepper = product_runs[scenario]["INTARIAN_PEPPER_ROOT"]
        sub = pepper.groupby("timestamp", as_index=False)["position"].mean().sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["position"], label=SCENARIO_LABELS[scenario], color=PALETTE[scenario], linewidth=2.5)
    for level, color in [(50, "#94A3B8"), (70, "#F59E0B"), (80, "#DC2626")]:
        ax.axhline(level, color=color, linestyle="--", linewidth=1.2)
    ax.set_title("Trayectoria de inventario de PEPPER — promedio por día")
    ax.set_xlabel("Timestamp dentro del día")
    ax.set_ylabel("Posición promedio")
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "pepper_inventory_trajectory.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_inventory_heatmap(inventory_dist_df: pd.DataFrame) -> None:
    configure_style()
    pivot = inventory_dist_df.pivot(index="scenario_label", columns="inventory_bin", values="pct_time").reindex(columns=INVENTORY_BIN_ORDER)
    fig, ax = plt.subplots(figsize=(12, 5.6))
    sns.heatmap(pivot, annot=True, fmt=".1%", cmap="Blues", cbar_kws={"label": "% del tiempo"}, ax=ax)
    ax.set_title("PEPPER — distribución del tiempo por nivel de inventario")
    ax.set_xlabel("Bin de inventario")
    ax.set_ylabel("")
    fig.savefig(PLOTS_DIR / "pepper_inventory_heatmap.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_delta_vs_inventory(delta_vs_inv_df: pd.DataFrame) -> None:
    configure_style()
    fig, ax = plt.subplots(figsize=(13, 6.5))
    plot_df = delta_vs_inv_df.copy()
    plot_df["inventory_bin"] = pd.Categorical(plot_df["inventory_bin"], INVENTORY_BIN_ORDER, ordered=True)
    plot_df = plot_df.sort_values(["scenario", "inventory_bin"])
    for scenario in ["uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]:
        sub = plot_df[plot_df["scenario"] == scenario]
        ax.plot(sub["inventory_bin"], sub["mean_delta_increment"], marker="o", linewidth=2.3, label=SCENARIO_LABELS[scenario], color=PALETTE[scenario])
    ax.axhline(0, color="#6B7280", linewidth=1.0)
    ax.set_title("Delta marginal promedio vs inventario baseline de PEPPER")
    ax.set_xlabel("Inventario baseline de PEPPER")
    ax.set_ylabel("Delta marginal promedio por timestamp")
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "delta_marginal_vs_inventory.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_bid_ev(bid_df: pd.DataFrame, plateau_df: pd.DataFrame) -> None:
    configure_style()
    risk = bid_df[bid_df["delta_name"] == "risk_adjusted"].copy().sort_values("bid")
    weighted_plateau = plateau_df[plateau_df["metric"] == "weighted_risk_adjusted"].iloc[0]
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(risk["bid"], risk["EV_uplift_low"], label="Competencia baja", color=PALETTE["low"], linewidth=1.8)
    ax.plot(risk["bid"], risk["EV_uplift_central"], label="Central", color=PALETTE["central"], linewidth=2.0)
    ax.plot(risk["bid"], risk["EV_uplift_high"], label="Competencia alta", color=PALETTE["high"], linewidth=2.0)
    ax.plot(risk["bid"], risk["EV_uplift_stress"], label="Stress muy alto", color=PALETTE["stress"], linewidth=2.0)
    ax.plot(risk["bid"], risk["EV_uplift_weighted"], label="Mixto ponderado (risk-adjusted)", color=PALETTE["weighted"], linewidth=3.2)
    ax.axvline(weighted_plateau["best_bid"], color="#0F766E", linestyle="--", linewidth=1.4)
    ax.axvspan(weighted_plateau["smallest_bid_within_95pct"], risk.loc[risk["EV_uplift_weighted"] >= 0.95 * risk["EV_uplift_weighted"].max(), "bid"].max(), color="#A7F3D0", alpha=0.20, label="Meseta 95% EV")
    ax.set_title("EV incremental del bid por escenario de cutoff")
    ax.set_xlabel("Bid")
    ax.set_ylabel("EV(b) - P0_1M")
    ax.legend(fontsize=10, ncol=2)
    fig.savefig(PLOTS_DIR / "bid_ev_curves.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_acceptance_probabilities(bid_df: pd.DataFrame) -> None:
    configure_style()
    risk = bid_df[bid_df["delta_name"] == "risk_adjusted"].copy().sort_values("bid")
    fig, ax = plt.subplots(figsize=(14, 7))
    for scenario in CUTOFF_SCENARIOS:
        ax.plot(risk["bid"], risk[f"q_{scenario.name}"], label=scenario.label, color=PALETTE[scenario.name], linewidth=2.4)
    ax.plot(risk["bid"], risk["q_weighted"], label="q(b) ponderado", color=PALETTE["weighted"], linewidth=3.0)
    ax.set_title("Probabilidad de aceptación q(b) por bid")
    ax.set_xlabel("Bid")
    ax.set_ylabel("Probabilidad de aceptación")
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "acceptance_probability_by_bid.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_uplift_and_roi(bid_df: pd.DataFrame) -> None:
    configure_style()
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharex=True)
    for delta_name, color in [("risk_adjusted", PALETTE["risk_adjusted"]), ("conservative", PALETTE["uniform_depth_125"]), ("central", PALETTE["front_bias_depth_25"] )]:
        sub = bid_df[bid_df["delta_name"] == delta_name].sort_values("bid")
        axes[0].plot(sub["bid"], 100 * sub["uplift_pct_vs_base_if_accepted"], label=delta_name, color=color, linewidth=2.4)
        axes[1].plot(sub["bid"], sub["fee_roi_if_accepted"], label=delta_name, color=color, linewidth=2.4)
    axes[0].axhline(0, color="#6B7280", linewidth=1.0)
    axes[1].axhline(0, color="#6B7280", linewidth=1.0)
    axes[0].set_title("Uplift % condicional si el bid entra")
    axes[0].set_xlabel("Bid")
    axes[0].set_ylabel("Uplift % vs P0_1M")
    axes[1].set_title("ROI del fee pagado si el bid entra")
    axes[1].set_xlabel("Bid")
    axes[1].set_ylabel("(Delta - b) / b")
    axes[0].legend(title="Delta usado", fontsize=10)
    fig.savefig(PLOTS_DIR / "uplift_and_fee_roi_by_bid.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_bid_sensitivity_heatmap(sensitivity_df: pd.DataFrame) -> None:
    configure_style()
    pivot = sensitivity_df.pivot(index="cutoff_median", columns="delta_1m", values="plateau95_bid")
    fig, ax = plt.subplots(figsize=(14, 7))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="YlGnBu", cbar_kws={"label": "Bid robusto (plateau 95%)"}, ax=ax)
    ax.set_title("Sensibilidad del bid recomendado a Delta_1M y cutoff rival")
    ax.set_xlabel("Delta_1M asumido")
    ax.set_ylabel("Mediana del cutoff rival")
    fig.savefig(PLOTS_DIR / "bid_sensitivity_heatmap.png", dpi=PLOT_DPI)
    plt.close(fig)


def plot_scaling_model(total_delta_df: pd.DataFrame, fit_df: pd.DataFrame) -> None:
    configure_style()
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.4), sharey=True)
    for ax, scenario in zip(axes, ["uniform_depth_125", "front_bias_depth_25"]):
        sub = (
            total_delta_df[total_delta_df["scenario"] == scenario]
            .groupby("timestamp", as_index=False)
            .agg(mean_delta=("delta", "mean"))
            .sort_values("timestamp")
        )
        x = sub["timestamp"].to_numpy() / DAY_MAX_TS
        y = sub["mean_delta"].to_numpy() / float(sub["mean_delta"].iloc[-1])
        best = fit_df[fit_df["scenario"] == scenario].sort_values("rmse").iloc[0]
        yhat = best_model_curve(best, x)
        ax.plot(x, y, label="Delta(t) normalizado", color=PALETTE[scenario], linewidth=2.8)
        ax.plot(x, yhat, label=f"Mejor ajuste: {best['model']}", color="#111827", linestyle="--", linewidth=2.1)
        ax.plot(x, x, label="Lineal", color="#94A3B8", linestyle=":", linewidth=1.8)
        ax.set_title(f"Escalado dentro del día — {SCENARIO_LABELS[scenario]}")
        ax.set_xlabel("Progreso relativo del día")
        ax.set_ylabel("Delta acumulado normalizado")
        ax.legend(fontsize=10)
    fig.savefig(PLOTS_DIR / "delta_scaling_model_fit.png", dpi=PLOT_DPI)
    plt.close(fig)


def write_report(
    summary_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    total_delta_df: pd.DataFrame,
    delta_vs_inv_df: pd.DataFrame,
    fit_df: pd.DataFrame,
    bid_df: pd.DataFrame,
    plateau_df: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
) -> None:
    base_total = summary_df.query("scenario == 'baseline' and product == 'TOTAL'").iloc[0]
    base_products = summary_df.query("scenario == 'baseline' and product != 'TOTAL'").copy()
    proxy_total = summary_df.query("scenario != 'baseline' and product == 'TOTAL'").copy()
    proxy_products = summary_df.query("scenario != 'baseline' and product != 'TOTAL'").copy()
    proxy_products = proxy_products.merge(
        summary_df.query("scenario == 'baseline' and product != 'TOTAL'")[["product", "total_pnl", "pnl_per_1m", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position"]].rename(
            columns={
                "total_pnl": "P0_sample",
                "pnl_per_1m": "P0_1m_product",
                "fill_count": "fill_count_base",
                "maker_share": "maker_share_base",
                "avg_fill_size": "avg_fill_size_base",
                "avg_abs_position": "avg_abs_position_base",
            }
        ),
        on="product",
        how="left",
    )
    proxy_products["Delta_sample"] = proxy_products["total_pnl"] - proxy_products["P0_sample"]
    proxy_products["Delta_1m"] = proxy_products["pnl_per_1m"] - proxy_products["P0_1m_product"]
    proxy_products["fill_count_change"] = proxy_products["fill_count"] - proxy_products["fill_count_base"]
    proxy_products["maker_share_change"] = proxy_products["maker_share"] - proxy_products["maker_share_base"]
    proxy_products["avg_fill_size_change"] = proxy_products["avg_fill_size"] - proxy_products["avg_fill_size_base"]
    proxy_products["avg_abs_position_change"] = proxy_products["avg_abs_position"] - proxy_products["avg_abs_position_base"]

    delta_1m = {
        "conservative": float(proxy_total.loc[proxy_total["scenario"] == "uniform_depth_125", "pnl_per_1m"].iloc[0] - base_total["pnl_per_1m"]),
        "central": float(proxy_total.loc[proxy_total["scenario"] == "front_bias_depth_25", "pnl_per_1m"].iloc[0] - base_total["pnl_per_1m"]),
        "aggressive": float(proxy_total.loc[proxy_total["scenario"] == "uniform_depth_trade_125", "pnl_per_1m"].iloc[0] - base_total["pnl_per_1m"]),
    }
    risk_adjusted_delta = 0.70 * delta_1m["conservative"]
    risk_bid = bid_df[bid_df["delta_name"] == "risk_adjusted"].copy()
    weighted_plateau = plateau_df[plateau_df["metric"] == "weighted_risk_adjusted"].iloc[0]
    pess_plateau = plateau_df[plateau_df["metric"] == "pessimistic_risk_adjusted"].iloc[0]
    recommended_bid = int(weighted_plateau["smallest_bid_within_95pct"])
    rec_row_risk = risk_bid.loc[risk_bid["bid"] == recommended_bid].iloc[0]
    rec_row_cons = bid_df[(bid_df["delta_name"] == "conservative") & (bid_df["bid"] == recommended_bid)].iloc[0]
    rec_row_cent = bid_df[(bid_df["delta_name"] == "central") & (bid_df["bid"] == recommended_bid)].iloc[0]

    pepper_daily = daily_df[(daily_df["product"] == "INTARIAN_PEPPER_ROOT") & (daily_df["scenario"].isin(["baseline", "uniform_depth_125", "front_bias_depth_25", "uniform_depth_trade_125"]))][[
        "scenario_label", "day", "day_pnl", "avg_position", "pct_time_pos_ge_70", "pct_time_pos_at_80", "time_to_50", "time_to_70", "time_to_80"
    ]].copy()

    proxy_total_table = proxy_total.merge(
        summary_df.query("scenario == 'baseline' and product == 'TOTAL'")[["total_pnl", "pnl_per_1m", "fill_count", "maker_share", "avg_fill_size"]].rename(
            columns={
                "total_pnl": "P0_sample",
                "pnl_per_1m": "P0_1m",
                "fill_count": "fill_count_base",
                "maker_share": "maker_share_base",
                "avg_fill_size": "avg_fill_size_base",
            }
        ),
        how="cross",
    )
    proxy_total_table["Delta_sample"] = proxy_total_table["total_pnl"] - proxy_total_table["P0_sample"]
    proxy_total_table["Delta_1m"] = proxy_total_table["pnl_per_1m"] - proxy_total_table["P0_1m"]
    proxy_total_table["fill_count_change"] = proxy_total_table["fill_count"] - proxy_total_table["fill_count_base"]
    proxy_total_table["maker_share_change"] = proxy_total_table["maker_share"] - proxy_total_table["maker_share_base"]
    proxy_total_table["avg_fill_size_change"] = proxy_total_table["avg_fill_size"] - proxy_total_table["avg_fill_size_base"]

    proxy_contrib = proxy_products.pivot_table(index="scenario_label", columns="product_label", values="Delta_1m")

    block_delta = bucket_df.merge(
        bucket_df[bucket_df["scenario"] == "baseline"][ ["product", "day", "bucket", "bucket_pnl"] ].rename(columns={"bucket_pnl": "bucket_pnl_base"}),
        on=["product", "day", "bucket"],
        how="left",
    )
    block_delta = block_delta[(block_delta["product"] == "TOTAL") & (block_delta["scenario"] != "baseline")].copy()
    block_delta["delta_bucket_pnl"] = block_delta["bucket_pnl"] - block_delta["bucket_pnl_base"]
    block_summary = block_delta.groupby(["scenario_label", "bucket"], as_index=False)["delta_bucket_pnl"].mean()

    fit_summary = (
        fit_df.groupby("model", as_index=False)
        .agg(avg_rmse=("rmse", "mean"), max_rmse=("rmse", "max"))
        .sort_values(["avg_rmse", "max_rmse"])
        .reset_index(drop=True)
    )
    chosen_scaling_model = str(fit_summary.iloc[0]["model"])
    linear_row = fit_summary.loc[fit_summary["model"] == "linear"]
    if not linear_row.empty and float(linear_row.iloc[0]["avg_rmse"]) <= float(fit_summary.iloc[0]["avg_rmse"]) + 1e-6:
        chosen_scaling_model = "linear"
    if chosen_scaling_model == "linear":
        scaling_interpretation = (
            "La mejor lectura empírica es casi lineal dentro del día: no aparece evidencia fuerte de una saturación pronunciada "
            "del Delta. Hay concentración de valor en algunos buckets, pero no la suficiente como para defender un crecimiento log/capped fuerte."
        )
    else:
        scaling_interpretation = (
            "La mejor lectura empírica muestra valor marginal decreciente dentro del día: el Delta acelera temprano y luego se aplana, "
            "lo que sí sería consistente con saturación."
        )

    cutoff_table = pd.DataFrame(
        [
            {
                "escenario": s.label,
                "median_bid": s.median_bid,
                "slope": s.slope,
                "weight": s.weight,
                "lectura": s.description,
            }
            for s in CUTOFF_SCENARIOS
        ]
    )

    bid_table = bid_df[bid_df["bid"].isin(CORE_BID_GRID) & bid_df["delta_name"].isin(["risk_adjusted", "conservative", "central"])].copy()
    bid_table = bid_table[[
        "delta_name", "bid", "q_low", "q_central", "q_high", "q_stress", "q_weighted", "net_gain_if_accepted", "uplift_pct_vs_base_if_accepted", "fee_roi_if_accepted", "EV_uplift_weighted"
    ]]
    bid_table["uplift_pct_vs_base_if_accepted"] *= 100.0

    sensitivity_slice = sensitivity_df[sensitivity_df["delta_1m"].isin([600, 800, 1000, 1200, 1600, 2000]) & sensitivity_df["cutoff_median"].isin([20, 40, 60, 80, 100, 120, 140])]
    sensitivity_pivot = sensitivity_slice.pivot(index="cutoff_median", columns="delta_1m", values="plateau95_bid").reset_index()

    front_ash_share = float(proxy_contrib.loc["Front-biased depth +25%", "ASH"] / delta_1m["central"])
    uniform_ash_share = float(proxy_contrib.loc["Uniform depth +25%", "ASH"] / delta_1m["conservative"])

    lines: List[str] = [
        "# Round 2 — análisis cuantitativo riguroso del MAF para model_kiko",
        "",
        "## A. Resumen ejecutivo",
        "",
        f"- `P0_sample` observado de `model_kiko` en los 3 días de Round 2 (días independientes, arrancando flat): **{base_total['total_pnl']:,.1f}**.",
        f"- `P0_1M` usado para valorar una ronda de ~1M timestamps: **{base_total['pnl_per_1m']:,.1f}** por día. Esto surge del promedio de tres días locales que ya cubren `timestamp = 0 → 999900`.",
        f"- `Delta_1M` estimado por extra access: **conservador {delta_1m['conservative']:,.1f}**, **central {delta_1m['central']:,.1f}**, **agresivo {delta_1m['aggressive']:,.1f}**.",
        f"- Haircut prudente para decisión de bid: **risk-adjusted = {risk_adjusted_delta:,.1f}** (= 70% del proxy conservador).",
        f"- Con el bid recomendado `{recommended_bid}`, el uplift neto condicional si el bid entra es **{100*rec_row_cons['uplift_pct_vs_base_if_accepted']:.2f}%** a **{100*rec_row_cent['uplift_pct_vs_base_if_accepted']:.2f}%** sobre `P0_1M` (conservador → central).",
        f"- Con ese mismo bid, el ROI del fee es **{rec_row_cons['fee_roi_if_accepted']:.2f}x** a **{rec_row_cent['fee_roi_if_accepted']:.2f}x** si el bid es aceptado.",
        f"- Rango razonable de bids: **{int(weighted_plateau['smallest_bid_within_90pct'])}–{int(pess_plateau['smallest_bid_within_95pct'])}**.",
        f"- Bid robusto recomendado: **`{recommended_bid}`**.",
        f"- Razón principal: el valor del MAF en `model_kiko` sale positivo y robusto, pero está **MUY** lejos de +25% PnL; además, el uplift viene sobre todo de **ASH** ({uniform_ash_share:.0%} del Delta conservador y {front_ash_share:.0%} del Delta central), no de desbloquear un edge nuevo enorme en PEPPER.",
        "",
        "## B. Formalización matemática",
        "",
        "Definiciones usadas:",
        "",
        "- `P0`: PnL sin extra access.",
        "- `P1`: PnL con extra access bajo un proxy contrafactual explícito.",
        "- `Delta = P1 - P0`.",
        "- `b`: bid.",
        "- `A(b)`: indicador de aceptación del bid, con `A(b)=1` si el bid entra en el top 50%.",
        "- `q(b) = Prob(C < b)`, donde `C` es el cutoff rival modelado como variable aleatoria.",
        "",
        "Fórmulas exactas:",
        "",
        "- `Pi(b) = P0 + A(b) * (Delta - b)`",
        "- `net_gain_if_accepted = Delta - b`",
        "- `uplift_pct_vs_base = (Delta - b) / P0`",
        "- `fee_roi = (Delta - b) / b`",
        "- `EV(b) = P0 + q(b) * (Delta - b)`",
        "",
        "Separación lógica que respeté durante todo el análisis:",
        "",
        "1. Primero fijé la lógica de trading de `model_kiko` y medí `P0` y `P1`.",
        "2. Recién después modelé la aceptación del bid vía `q(b)`.",
        "3. No mezclé la valuación del access extra con rediseños de estrategia.",
        "",
        "## C. Resultados por proxy",
        "",
        "### Baseline limpio de `model_kiko`",
        "",
        markdown_table(
            summary_df.query("scenario == 'baseline'")[[
                "product_label", "total_pnl", "pnl_per_1m", "max_drawdown", "fill_count", "maker_share", "avg_fill_size", "avg_abs_position", "pct_time_abs_ge_70", "pct_time_at_limit"
            ]].rename(columns={
                "product_label": "product",
                "total_pnl": "P0_sample",
                "pnl_per_1m": "P0_1M",
                "max_drawdown": "drawdown",
                "fill_count": "fill_count",
                "maker_share": "maker_share",
                "avg_fill_size": "avg_fill_size",
                "avg_abs_position": "avg_abs_position",
                "pct_time_abs_ge_70": "pct_time_abs_ge_70",
                "pct_time_at_limit": "pct_time_at_limit",
            }),
            ".3f",
        ),
        "",
        "### Timing e inventario de PEPPER en baseline (cada día arranca flat)",
        "",
        markdown_table(
            pepper_daily[pepper_daily["scenario_label"] == "Baseline"].copy(),
            ".1f",
        ),
        "",
        f"Lectura baseline: PEPPER ya pasa **{100*float(summary_df.query("scenario == 'baseline' and product == 'INTARIAN_PEPPER_ROOT'").iloc[0]['pct_time_pos_ge_70']):.1f}%** del tiempo en `>=70` y **{100*float(summary_df.query("scenario == 'baseline' and product == 'INTARIAN_PEPPER_ROOT'").iloc[0]['pct_time_pos_at_80']):.1f}%** exactamente en `80`. O sea: la saturación existe, pero en `model_kiko` el cuello marginal del MAF NO está dominado por PEPPER; está más en ASH/fill quality.",
        "",
        "### `P0`, `P1` y `Delta` por proxy (TOTAL)",
        "",
        markdown_table(
            proxy_total_table[[
                "scenario_label", "P0_sample", "total_pnl", "Delta_sample", "P0_1m", "pnl_per_1m", "Delta_1m", "fill_count_change", "maker_share_change", "avg_fill_size_change"
            ]].rename(columns={
                "scenario_label": "proxy",
                "total_pnl": "P1_sample",
                "pnl_per_1m": "P1_1M_equiv",
            }),
            ".3f",
        ),
        "",
        "### Descomposición por producto",
        "",
        markdown_table(
            proxy_products[[
                "scenario_label", "product_label", "P0_sample", "total_pnl", "Delta_sample", "P0_1m_product", "pnl_per_1m", "Delta_1m", "fill_count_change", "maker_share_change", "avg_fill_size_change", "avg_abs_position_change"
            ]].rename(columns={
                "scenario_label": "proxy",
                "product_label": "product",
                "total_pnl": "P1_sample",
                "pnl_per_1m": "P1_1M_equiv",
            }),
            ".3f",
        ),
        "",
        "### Cambios de timing/inventario en PEPPER",
        "",
        markdown_table(
            pepper_daily[pepper_daily["scenario_label"] != "Baseline"].copy(),
            ".1f",
        ),
        "",
        f"Hallazgo clave: el proxy conservador suma **{delta_1m['conservative']:,.1f}** por ~1M timestamps y el central **{delta_1m['central']:,.1f}**; pero la parte de PEPPER es chica frente a ASH. Con el proxy central, ASH explica ~**{front_ash_share:.0%}** del Delta. Así que para `model_kiko` el MAF es más una mejora de acceso/calidad de ejecución que un cambio estructural del carry de PEPPER.",
        "",
        "## D. Escalado a 1M timestamps",
        "",
        f"No hice `Delta_1M = Delta_sample * (1,000,000 / T_sample)` porque sería metodológicamente flojo. De hecho, los CSV locales ya recorren `timestamp = 0 → 999900` por día, con saltos de 100. O sea: **cada día ya cubre ~1M unidades de timestamp**. Lo correcto es tratar los tres días como tres draws de una ronda ~1M arrancando flat y estimar `Delta_1M` desde la distribución diaria, no reescalar el total de 3 días linealmente.",
        "",
        f"Resultado explícito: `Delta_1M_conservative = {delta_1m['conservative']:,.1f}`, `Delta_1M_central = {delta_1m['central']:,.1f}`, `Delta_1M_aggressive = {delta_1m['aggressive']:,.1f}`.",
        "",
        "### Delta incremental por bloques (promedio por día, TOTAL)",
        "",
        markdown_table(block_summary.pivot(index="bucket", columns="scenario_label", values="delta_bucket_pnl").reset_index(), ".1f"),
        "",
        "### Comparativa de funciones de scaling para la forma de `Delta(t)` dentro del día",
        "",
        markdown_table(fit_summary, ".5f"),
        "",
        f"La función más defendible es **`{chosen_scaling_model}`**. {scaling_interpretation} Como cada día ya es un horizonte ~1M, esta comparación sirve para entender la forma de `Delta(t)`, no para extrapolar mecánicamente el Delta local 100x.",
        "",
        "## E. Análisis game theoretic del cutoff",
        "",
        "No observamos bids rivales, así que modelé el cutoff `C` con una mezcla de escenarios logísticos simples y explicables:",
        "",
        markdown_table(cutoff_table, ".3f"),
        "",
        f"Para decidir el bid usé `Delta_risk_adjusted = {risk_adjusted_delta:,.1f}`. También reporto sensibilidad con `Delta` conservador y central.",
        "",
        "### Grid de bids",
        "",
        markdown_table(bid_table, ".3f"),
        "",
        f"- Bid que maximiza el EV ponderado (risk-adjusted): **{int(weighted_plateau['best_bid'])}**.",
        f"- Menor bid dentro del 95% del EV máximo: **{int(weighted_plateau['smallest_bid_within_95pct'])}**.",
        f"- Menor bid dentro del 90% del EV máximo: **{int(weighted_plateau['smallest_bid_within_90pct'])}**.",
        f"- Bid robusto bajo escenario pesimista (95% del máximo high+stress): **{int(pess_plateau['smallest_bid_within_95pct'])}**.",
        f"- En el bid recomendado `{recommended_bid}`, `q(b)` ponderado ≈ **{100*rec_row_risk['q_weighted']:.1f}%** y el EV incremental risk-adjusted es **{rec_row_risk['EV_uplift_weighted']:,.1f}**.",
        "",
        "### Sensibilidad de la recomendación",
        "",
        markdown_table(sensitivity_pivot, ".0f"),
        "",
        "Lectura: la meseta de EV es bastante ancha. Por eso NO elijo el máximo puntual del EV sin más. Prefiero el menor bid que ya entra en esa meseta, porque eso captura casi todo el valor esperado sin regalar fee innecesario.",
        "",
        "## F. Visualizaciones",
        "",
        "Archivos generados en `/Users/pablo/Desktop/prosperity/round_2/results/kiko_maf_rigorous/plots/`:",
        "",
        "1. `pnl_cumulative_baseline_vs_proxies.png` — compara PnL acumulado total y por producto; muestra que el uplift bajo proxies razonables es positivo pero moderado, y que ASH explica gran parte del gap.",
        "2. `delta_cumulative_curve.png` — curva `Delta(t)` acumulada; permite ver cuándo nace el valor del extra access y si se acumula de forma frontal o más homogénea a lo largo del día.",
        "3. `delta_incremental_blocks.png` — Delta incremental por bloques; sirve para detectar la caída del valor marginal y dónde se concentra el edge del MAF.",
        "4. `pepper_inventory_trajectory.png` — trayectoria de inventario de PEPPER con líneas en 50/70/80; muestra que el extra access acelera algunos hitos, pero no cambia dramáticamente el régimen final.",
        "5. `pepper_inventory_heatmap.png` — heatmap del tiempo por bin de inventario; cuantifica la saturación cerca de 70–80.",
        "6. `delta_marginal_vs_inventory.png` — Delta marginal vs inventario baseline de PEPPER; ayuda a ver si el valor marginal cae cuando la posición ya está alta.",
        "7. `bid_ev_curves.png` — EV incremental del bid por escenario de cutoff + mezcla ponderada; marca la meseta del 95%.",
        "8. `acceptance_probability_by_bid.png` — `q(b)` por bid; visualiza el trade-off entre pagar más y comprar más probabilidad de aceptación.",
        "9. `uplift_and_fee_roi_by_bid.png` — uplift % condicional y ROI del fee por bid; deja claro qué bids siguen siendo muy rentables si son aceptados.",
        "10. `bid_sensitivity_heatmap.png` — sensibilidad del bid recomendado a `Delta_1M` y a la mediana del cutoff rival.",
        "11. `delta_scaling_model_fit.png` — compara el `Delta(t)` normalizado con la mejor función de scaling dentro del día y con una recta lineal.",
        "",
        "## G. Recomendación final",
        "",
        f"- **Bid recomendado:** `{recommended_bid}`.",
        f"- **Intervalo alternativo razonable:** `{int(weighted_plateau['smallest_bid_within_90pct'])}`–`{int(pess_plateau['smallest_bid_within_95pct'])}`.",
        f"- **Subiría el bid** hacia `{int(pess_plateau['smallest_bid_within_95pct'])}` si creés que el campo rival se parece más a los escenarios `high/stress` o si tenés evidencia externa de que los equipos van a pagar tres cifras.",
        f"- **Bajaría el bid** hacia `{int(weighted_plateau['smallest_bid_within_90pct'])}` si querés minimizar fee y tu prior es que el cutoff real está bastante por debajo de 80.",
        "",
        f"Con estos resultados para `model_kiko`, el uplift neto condicional a ser aceptado es de **{100*rec_row_cons['uplift_pct_vs_base_if_accepted']:.2f}%** a **{100*rec_row_cent['uplift_pct_vs_base_if_accepted']:.2f}%** sobre baseline.",
        f"El ROI del fee es de **{rec_row_cons['fee_roi_if_accepted']:.2f}x** a **{rec_row_cent['fee_roi_if_accepted']:.2f}x**.",
        f"El bid robusto recomendado es **{recommended_bid}**.",
        f"La principal razón es que el MAF sí agrega valor, pero en `model_kiko` ese valor es **moderado, no explosivo**, viene mayormente de **ASH/fill quality**, y la curva de EV es lo bastante plana como para priorizar robustez y no sobrepagar.",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    loaded_data = load_all_raw_data()
    summary_frames: List[pd.DataFrame] = []
    product_runs: Dict[str, Dict[str, pd.DataFrame]] = {}
    product_fills: Dict[str, Dict[str, pd.DataFrame]] = {}
    total_runs: Dict[str, pd.DataFrame] = {}

    for scenario in SCENARIO_ORDER:
        proxy = None if scenario == "baseline" else PROXY_LOOKUP[scenario]
        summary_df, prod_res, prod_fills, combined_df, _combined_fills = run_scenario(scenario, proxy, loaded_data)
        summary_frames.append(summary_df)
        product_runs[scenario] = prod_res
        product_fills[scenario] = prod_fills
        total_runs[scenario] = combined_df

    summary_df = pd.concat(summary_frames, ignore_index=True)
    daily_df = build_daily_metrics(product_runs, total_runs)
    bucket_df = build_bucket_metrics(product_runs, total_runs)
    total_delta_df, product_delta_df = build_delta_curves(total_runs, product_runs)
    inventory_dist_df = build_inventory_distribution(product_runs)
    delta_vs_inv_df = build_delta_vs_inventory(total_delta_df, product_runs)

    fit_rows: List[pd.DataFrame] = []
    for scenario in ["uniform_depth_125", "front_bias_depth_25"]:
        mean_curve = (
            total_delta_df[total_delta_df["scenario"] == scenario]
            .groupby("timestamp", as_index=False)
            .agg(mean_delta=("delta", "mean"))
            .sort_values("timestamp")
        )
        x = mean_curve["timestamp"].to_numpy() / DAY_MAX_TS
        y = mean_curve["mean_delta"].to_numpy() / float(mean_curve["mean_delta"].iloc[-1])
        fit_df = fit_shape_models(x, y)
        fit_df["scenario"] = scenario
        fit_rows.append(fit_df)
    fit_df = pd.concat(fit_rows, ignore_index=True)

    base_total = summary_df.query("scenario == 'baseline' and product == 'TOTAL'").iloc[0]
    delta_1m = {
        "conservative": float(summary_df.query("scenario == 'uniform_depth_125' and product == 'TOTAL'").iloc[0]["pnl_per_1m"] - base_total["pnl_per_1m"]),
        "central": float(summary_df.query("scenario == 'front_bias_depth_25' and product == 'TOTAL'").iloc[0]["pnl_per_1m"] - base_total["pnl_per_1m"]),
        "aggressive": float(summary_df.query("scenario == 'uniform_depth_trade_125' and product == 'TOTAL'").iloc[0]["pnl_per_1m"] - base_total["pnl_per_1m"]),
    }
    risk_adjusted_delta = 0.70 * delta_1m["conservative"]
    bid_df, plateau_df, sensitivity_df = build_bid_grid(float(base_total["pnl_per_1m"]), delta_1m, risk_adjusted_delta)

    save_dataframe(summary_df, "summary_metrics")
    save_dataframe(daily_df, "daily_metrics")
    save_dataframe(bucket_df, "bucket_metrics")
    save_dataframe(total_delta_df, "delta_curves_total")
    save_dataframe(product_delta_df, "delta_curves_by_product")
    save_dataframe(inventory_dist_df, "pepper_inventory_distribution")
    save_dataframe(delta_vs_inv_df, "delta_vs_inventory")
    save_dataframe(fit_df, "delta_scaling_fits")
    save_dataframe(bid_df, "bid_grid")
    save_dataframe(plateau_df, "bid_plateau_summary")
    save_dataframe(sensitivity_df, "bid_sensitivity")

    plot_pnl_cumulative(total_runs, product_runs)
    plot_delta_curves(total_delta_df)
    plot_delta_incremental_blocks(bucket_df)
    plot_pepper_inventory(product_runs)
    plot_inventory_heatmap(inventory_dist_df)
    plot_delta_vs_inventory(delta_vs_inv_df)
    plot_bid_ev(bid_df, plateau_df)
    plot_acceptance_probabilities(bid_df)
    plot_uplift_and_roi(bid_df)
    plot_bid_sensitivity_heatmap(sensitivity_df)
    plot_scaling_model(total_delta_df, fit_df)

    write_report(summary_df, daily_df, bucket_df, total_delta_df, delta_vs_inv_df, fit_df, bid_df, plateau_df, sensitivity_df)


if __name__ == "__main__":
    main()
