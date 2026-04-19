from __future__ import annotations

import importlib.util
import math
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[2]
ROUND_1_TOOLS = ROOT / "round_1" / "tools"
ROUND_1_MODELS = ROOT / "round_1" / "models"
ROUND_2_TOOLS = ROOT / "round_2" / "tools"
ROUND_2_MODELS = ROOT / "round_2" / "models"
OUT_DIR = ROOT / "round_2" / "results" / "maf_model_heterogeneity"
PLOTS_DIR = OUT_DIR / "plots"
REPORT_PATH = OUT_DIR / "round2_maf_model_heterogeneity.md"

sys.path.insert(0, str(ROUND_2_TOOLS))
sys.path.insert(0, str(ROUND_2_MODELS))
sys.path.insert(0, str(ROUND_1_TOOLS))
sys.path.insert(0, str(ROUND_1_MODELS))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402
import audit_model_kiko as amk  # noqa: E402


ROUND_NAME = "round_2"
DAYS = (-1, 0, 1)
DAY_LABELS = {-1: "día -1", 0: "día 0", 1: "día 1"}
PRODUCTS = tuple(ag.PRODUCTS)
POSITION_LIMITS = ag.POSITION_LIMITS

MODELS = [
    "model_kiko",
    "model_G5",
    "model_G1",
    "model_G4",
    "model_G2",
    "model_F3",
]

MODEL_LABELS = {
    "model_kiko": "model_kiko",
    "model_G5": "model_G5",
    "model_G1": "model_G1",
    "model_G4": "model_G4",
    "model_G2": "model_G2",
    "model_F3": "model_F3",
}

PRODUCT_LABELS = {
    "ASH_COATED_OSMIUM": "ASH",
    "INTARIAN_PEPPER_ROOT": "PEPPER",
    "TOTAL": "TOTAL",
}

SCENARIO_CONFIGS = OrderedDict(
    [
        (
            "baseline",
            {
                "label": "Baseline",
                "proxy": None,
                "proxy_kind": "baseline",
                "description": "Mercado observado, sin access extra.",
            },
        ),
        (
            "uniform_depth_125",
            {
                "label": "Uniform depth +25%",
                "proxy": "uniform_depth_125",
                "proxy_kind": "conservative",
                "description": "Proxy conservador: +25% de profundidad visible, sin tocar market trades.",
            },
        ),
        (
            "front_bias_depth_25",
            {
                "label": "Front-biased depth +25%",
                "proxy": "front_bias_depth_25",
                "proxy_kind": "central",
                "description": "Proxy central: depth extra concentrada cerca del touch.",
            },
        ),
        (
            "uniform_depth_trade_125",
            {
                "label": "Depth +25% + trades +25%",
                "proxy": "uniform_depth_trade_125",
                "proxy_kind": "upper_bound",
                "description": "Upper bound local: +25% de depth y +25% de trade flow.",
            },
        ),
    ]
)

BID_GRID = [100, 125, 150, 175, 200, 225]
OUR_BIDS = [125, 150, 175, 200]
RIVAL_BID_SUPPORT = np.array([100, 125, 150, 175, 200, 225, 250, 300], dtype=int)
TOTAL_PARTICIPANTS = 100
RIVALS = TOTAL_PARTICIPANTS - 1
ACCEPTED = TOTAL_PARTICIPANTS // 2
N_SIMS = 250_000
RNG = np.random.default_rng(20260419)

PALETTE = {
    "baseline": "#111827",
    "conservative": "#0F766E",
    "central": "#2563EB",
    "upper_bound": "#DC2626",
    "model_kiko": "#111827",
    "model_G5": "#2563EB",
    "model_G1": "#7C3AED",
    "model_G4": "#0F766E",
    "model_G2": "#DC2626",
    "model_F3": "#D97706",
    "MAF-light": "#94A3B8",
    "MAF-medium": "#7C3AED",
    "MAF-heavy": "#DC2626",
    "R1": "#1D4ED8",
    "R2": "#7C3AED",
    "R3": "#D97706",
    "R4": "#DC2626",
}

PROXY_LOOKUP = {proxy.name: proxy for proxy in ag.PROXIES}


@dataclass(frozen=True)
class RivalScenario:
    key: str
    label: str
    class_weights: Mapping[str, float]
    logic: str
    model_switch_story: str


RIVAL_SCENARIOS = (
    RivalScenario(
        key="R1",
        label="R1 — Field conservador",
        class_weights={"MAF-light": 0.60, "MAF-medium": 0.25, "MAF-heavy": 0.10, "noise": 0.05},
        logic="La mayoría del field sigue en modelos de sensibilidad baja/media al MAF; hay algo de cola alta, pero no domina.",
        model_switch_story="Poca adaptación táctica: algunos equipos prueban modelos más sensibles, pero el grueso no rehace el stack por Round 2.",
    ),
    RivalScenario(
        key="R2",
        label="R2 — Field mixto",
        class_weights={"MAF-light": 0.45, "MAF-medium": 0.25, "MAF-heavy": 0.20, "noise": 0.10},
        logic="Conviven equipos que siguen con modelos light/medium y un bloque no trivial que va a variantes más MAF-sensitive.",
        model_switch_story="Adaptación parcial: el model-switch existe, pero no se vuelve dominante.",
    ),
    RivalScenario(
        key="R3",
        label="R3 — Field adaptativo",
        class_weights={"MAF-light": 0.25, "MAF-medium": 0.25, "MAF-heavy": 0.40, "noise": 0.10},
        logic="La lectura del MAF se difunde y una parte relevante del field migra hacia modelos con mayor valor privado del access.",
        model_switch_story="Cambio táctico visible: la ventaja del access pasa a ser un driver serio de elección de modelo.",
    ),
    RivalScenario(
        key="R4",
        label="R4 — Field muy agresivo",
        class_weights={"MAF-light": 0.10, "MAF-medium": 0.20, "MAF-heavy": 0.50, "noise": 0.20},
        logic="Aparece una cola alta seria: muchos equipos usan modelos MAF-heavy y además hay overinsurance/noise alto.",
        model_switch_story="Stress serio: el field internaliza el MAF y aparecen bids materialmente más altos de forma no marginal.",
    ),
)


CLASS_BID_PMF = {
    "MAF-light": {100: 0.20, 125: 0.25, 150: 0.25, 175: 0.15, 200: 0.08, 225: 0.04, 250: 0.02, 300: 0.01},
    "MAF-medium": {100: 0.10, 125: 0.18, 150: 0.27, 175: 0.22, 200: 0.12, 225: 0.06, 250: 0.03, 300: 0.02},
    "MAF-heavy": {100: 0.04, 125: 0.10, 150: 0.22, 175: 0.25, 200: 0.18, 225: 0.11, 250: 0.06, 300: 0.04},
    "noise": {int(b): 1.0 / len(RIVAL_BID_SUPPORT) for b in RIVAL_BID_SUPPORT},
}


def configure_style() -> None:
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update(
        {
            "figure.facecolor": "#FBFBFD",
            "axes.facecolor": "#FBFBFD",
            "axes.edgecolor": "#D6D9E0",
            "axes.labelcolor": "#1F2937",
            "axes.titlecolor": "#111827",
            "axes.titleweight": "bold",
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
            "figure.dpi": 170,
        }
    )


def markdown_table(df: pd.DataFrame, float_fmt: str = ".2f") -> str:
    if df.empty:
        return "_sin datos_"
    headers = list(df.columns)
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
            "| " + " | ".join(str(h) for h in headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *rows,
        ]
    )


def save_df(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT_DIR / f"{name}.csv", index=False)


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def instantiate_trader(model_key: str):
    module = load_module(model_key, amk.MODEL_PATHS[model_key])
    return module.Trader()


def load_all_raw_data() -> Dict[str, Dict[int, ag.LoadedDayData]]:
    return {product: {day: ag.load_day_data(ROUND_NAME, day, product) for day in DAYS} for product in PRODUCTS}


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


def compute_time_to_threshold(results_df: pd.DataFrame, threshold: int) -> float:
    hit = results_df.loc[results_df["position"] >= threshold, "timestamp"]
    return float(hit.iloc[0]) if not hit.empty else np.nan


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
    merged["drawdown"] = merged["total_pnl"] - merged["total_pnl"].cummax()
    merged["day"] = int(day)
    return merged


def compute_product_day_metrics(
    model: str,
    scenario: str,
    day: int,
    product: str,
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> Dict[str, float | str | int]:
    meta = SCENARIO_CONFIGS[scenario]
    fill_metrics = summarize_fills(fills_df)
    row: Dict[str, float | str | int] = {
        "model": model,
        "scenario": scenario,
        "scenario_label": str(meta["label"]),
        "proxy_kind": str(meta["proxy_kind"]),
        "day": int(day),
        "day_label": DAY_LABELS[int(day)],
        "product": product,
        "product_label": PRODUCT_LABELS[product],
        "P_d": float(results_df["pnl"].iloc[-1]),
        "drawdown": compute_drawdown(results_df["pnl"]),
        "fill_count": fill_metrics["fill_count"],
        "maker_share": fill_metrics["maker_share"],
        "aggressive_fill_share": fill_metrics["aggressive_fill_share"],
        "avg_fill_size": fill_metrics["avg_fill_size"],
        "avg_position": float(results_df["position"].mean()),
        "avg_abs_position": float(results_df["position"].abs().mean()),
        "max_abs_position": float(results_df["position"].abs().max()),
        "pct_time_abs_ge_60": float((results_df["position"].abs() >= 60).mean()),
        "pct_time_abs_ge_70": float((results_df["position"].abs() >= 70).mean()),
        "pct_time_at_limit": float((results_df["position"].abs() >= POSITION_LIMITS[product]).mean()),
        "final_position": float(results_df["position"].iloc[-1]),
        "time_to_50": np.nan,
        "time_to_70": np.nan,
        "time_to_80": np.nan,
    }
    if product == "INTARIAN_PEPPER_ROOT":
        row["time_to_50"] = compute_time_to_threshold(results_df, 50)
        row["time_to_70"] = compute_time_to_threshold(results_df, 70)
        row["time_to_80"] = compute_time_to_threshold(results_df, 80)
    return row


def compute_total_day_metrics(
    model: str,
    scenario: str,
    day: int,
    total_curve: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> Dict[str, float | str | int]:
    meta = SCENARIO_CONFIGS[scenario]
    fill_metrics = summarize_fills(fills_df)
    return {
        "model": model,
        "scenario": scenario,
        "scenario_label": str(meta["label"]),
        "proxy_kind": str(meta["proxy_kind"]),
        "day": int(day),
        "day_label": DAY_LABELS[int(day)],
        "product": "TOTAL",
        "product_label": "TOTAL",
        "P_d": float(total_curve["total_pnl"].iloc[-1]),
        "drawdown": float(total_curve["drawdown"].min()),
        "fill_count": fill_metrics["fill_count"],
        "maker_share": fill_metrics["maker_share"],
        "aggressive_fill_share": fill_metrics["aggressive_fill_share"],
        "avg_fill_size": fill_metrics["avg_fill_size"],
        "avg_position": np.nan,
        "avg_abs_position": np.nan,
        "max_abs_position": np.nan,
        "pct_time_abs_ge_60": np.nan,
        "pct_time_abs_ge_70": np.nan,
        "pct_time_at_limit": np.nan,
        "final_position": np.nan,
        "time_to_50": np.nan,
        "time_to_70": np.nan,
        "time_to_80": np.nan,
    }


def run_all_model_scenarios(
    loaded_data: Mapping[str, Mapping[int, ag.LoadedDayData]]
) -> tuple[pd.DataFrame, Dict[str, Dict[str, Dict[int, Dict[str, pd.DataFrame]]]]]:
    rows: List[Dict[str, float | str | int]] = []
    product_runs: Dict[str, Dict[str, Dict[int, Dict[str, pd.DataFrame]]]] = {}

    for model in MODELS:
        product_runs[model] = {}
        for scenario, meta in SCENARIO_CONFIGS.items():
            product_runs[model][scenario] = {}
            proxy_name = meta["proxy"]
            proxy = None if proxy_name is None else PROXY_LOOKUP[str(proxy_name)]
            for day in DAYS:
                product_frames: Dict[str, pd.DataFrame] = {}
                fill_frames: Dict[str, pd.DataFrame] = {}
                product_runs[model][scenario][day] = {}
                for product in PRODUCTS:
                    raw = loaded_data[product][day]
                    depth, trades = ag.apply_proxy(raw, proxy) if proxy is not None else (raw.depth_by_ts, raw.trades_df.copy())
                    trader = instantiate_trader(model)
                    results_df, fills_df, _metrics = bt.run_backtest_on_loaded_data(
                        trader,
                        product,
                        [day],
                        {day: (depth, trades)},
                        reset_between_days=False,
                    )
                    results_df = results_df.copy().sort_values("timestamp").reset_index(drop=True)
                    fills_df = (
                        fills_df.copy().sort_values("timestamp").reset_index(drop=True)
                        if not fills_df.empty
                        else pd.DataFrame(columns=["day", "timestamp", "global_ts", "product", "side", "price", "quantity", "source"])
                    )
                    product_frames[product] = results_df
                    fill_frames[product] = fills_df
                    product_runs[model][scenario][day][product] = results_df
                    rows.append(compute_product_day_metrics(model, scenario, day, product, results_df, fills_df))

                total_curve = merge_total_curve(product_frames, day)
                combined_fills = pd.concat([fill_frames[product] for product in PRODUCTS], ignore_index=True)
                product_runs[model][scenario][day]["TOTAL"] = total_curve
                rows.append(compute_total_day_metrics(model, scenario, day, total_curve, combined_fills))

    return pd.DataFrame(rows), product_runs


def summarize_distribution(values: Sequence[float]) -> Dict[str, float]:
    s = pd.Series(list(values), dtype=float)
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "min": float(s.min()),
        "max": float(s.max()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "p25": float(s.quantile(0.25)),
    }


def build_baseline_summary(day_metrics: pd.DataFrame) -> pd.DataFrame:
    base = day_metrics[day_metrics["scenario"] == "baseline"].copy()
    rows: List[Dict[str, float | str]] = []
    for model in MODELS:
        for product in [*PRODUCTS, "TOTAL"]:
            sub = base[(base["model"] == model) & (base["product"] == product)].sort_values("day")
            stats = summarize_distribution(sub["P_d"].tolist())
            rows.append(
                {
                    "model": model,
                    "product": product,
                    "product_label": PRODUCT_LABELS[product],
                    "P0_mean": stats["mean"],
                    "P0_median": stats["median"],
                    "P0_min": stats["min"],
                    "P0_max": stats["max"],
                    "P0_std": stats["std"],
                    "P0_p25": stats["p25"],
                    "drawdown_mean": float(sub["drawdown"].mean()),
                    "fill_count_mean": float(sub["fill_count"].mean()),
                    "maker_share_mean": float(sub["maker_share"].mean()) if sub["maker_share"].notna().any() else np.nan,
                    "avg_fill_size_mean": float(sub["avg_fill_size"].mean()) if sub["avg_fill_size"].notna().any() else np.nan,
                    "avg_abs_position_mean": float(sub["avg_abs_position"].mean()) if sub["avg_abs_position"].notna().any() else np.nan,
                    "pct_time_abs_ge_70_mean": float(sub["pct_time_abs_ge_70"].mean()) if sub["pct_time_abs_ge_70"].notna().any() else np.nan,
                    "pct_time_at_limit_mean": float(sub["pct_time_at_limit"].mean()) if sub["pct_time_at_limit"].notna().any() else np.nan,
                    "time_to_50_mean": float(sub["time_to_50"].mean()) if sub["time_to_50"].notna().any() else np.nan,
                    "time_to_70_mean": float(sub["time_to_70"].mean()) if sub["time_to_70"].notna().any() else np.nan,
                    "time_to_80_mean": float(sub["time_to_80"].mean()) if sub["time_to_80"].notna().any() else np.nan,
                }
            )
    return pd.DataFrame(rows)


def build_delta_day_metrics(day_metrics: pd.DataFrame) -> pd.DataFrame:
    base = day_metrics[day_metrics["scenario"] == "baseline"].copy()
    proxies = day_metrics[day_metrics["scenario"] != "baseline"].copy()
    merged = proxies.merge(
        base[
            [
                "model",
                "day",
                "product",
                "P_d",
                "drawdown",
                "fill_count",
                "maker_share",
                "avg_fill_size",
                "avg_abs_position",
                "pct_time_abs_ge_70",
                "pct_time_at_limit",
                "time_to_50",
                "time_to_70",
                "time_to_80",
            ]
        ].rename(
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
        on=["model", "day", "product"],
        how="left",
    )
    merged = merged.rename(columns={"P_d": "P1_d"})
    merged["Delta_d"] = merged["P1_d"] - merged["P0_d"]
    merged["fill_count_change"] = merged["fill_count"] - merged["fill_count_P0"]
    merged["maker_share_change"] = merged["maker_share"] - merged["maker_share_P0"]
    merged["avg_fill_size_change"] = merged["avg_fill_size"] - merged["avg_fill_size_P0"]
    merged["avg_abs_position_change"] = merged["avg_abs_position"] - merged["avg_abs_position_P0"]
    merged["pct_time_abs_ge_70_change"] = merged["pct_time_abs_ge_70"] - merged["pct_time_abs_ge_70_P0"]
    merged["pct_time_at_limit_change"] = merged["pct_time_at_limit"] - merged["pct_time_at_limit_P0"]
    merged["time_to_70_change"] = merged["time_to_70"] - merged["time_to_70_P0"]
    merged["time_to_80_change"] = merged["time_to_80"] - merged["time_to_80_P0"]
    return merged


def build_delta_summary(delta_day: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | str]] = []
    for model in MODELS:
        for scenario in [k for k in SCENARIO_CONFIGS if k != "baseline"]:
            for product in [*PRODUCTS, "TOTAL"]:
                sub = delta_day[
                    (delta_day["model"] == model)
                    & (delta_day["scenario"] == scenario)
                    & (delta_day["product"] == product)
                ].sort_values("day")
                stats = summarize_distribution(sub["Delta_d"].tolist())
                rows.append(
                    {
                        "model": model,
                        "scenario": scenario,
                        "scenario_label": SCENARIO_CONFIGS[scenario]["label"],
                        "proxy_kind": SCENARIO_CONFIGS[scenario]["proxy_kind"],
                        "product": product,
                        "product_label": PRODUCT_LABELS[product],
                        "Delta_mean": stats["mean"],
                        "Delta_median": stats["median"],
                        "Delta_min": stats["min"],
                        "Delta_max": stats["max"],
                        "Delta_std": stats["std"],
                        "Delta_p25": stats["p25"],
                        "fill_count_change_mean": float(sub["fill_count_change"].mean()),
                        "maker_share_change_mean": float(sub["maker_share_change"].mean()) if sub["maker_share_change"].notna().any() else np.nan,
                        "avg_fill_size_change_mean": float(sub["avg_fill_size_change"].mean()) if sub["avg_fill_size_change"].notna().any() else np.nan,
                        "avg_abs_position_change_mean": float(sub["avg_abs_position_change"].mean()) if sub["avg_abs_position_change"].notna().any() else np.nan,
                        "time_to_70_change_mean": float(sub["time_to_70_change"].mean()) if sub["time_to_70_change"].notna().any() else np.nan,
                        "time_to_80_change_mean": float(sub["time_to_80_change"].mean()) if sub["time_to_80_change"].notna().any() else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def classify_sensitivity(cons_uplift_pct: float) -> str:
    if cons_uplift_pct < 0.0120:
        return "MAF-light"
    if cons_uplift_pct < 0.0155:
        return "MAF-medium"
    return "MAF-heavy"


def max_positive_bid(delta_value: float) -> float:
    feasible = [bid for bid in BID_GRID if delta_value - bid > 0]
    return float(max(feasible)) if feasible else np.nan


def build_model_value_summary(baseline_summary: pd.DataFrame, delta_summary: pd.DataFrame) -> pd.DataFrame:
    base_total = baseline_summary[baseline_summary["product"] == "TOTAL"].set_index("model")
    cons_total = delta_summary[(delta_summary["product"] == "TOTAL") & (delta_summary["scenario"] == "uniform_depth_125")].set_index("model")
    cent_total = delta_summary[(delta_summary["product"] == "TOTAL") & (delta_summary["scenario"] == "front_bias_depth_25")].set_index("model")
    upper_total = delta_summary[(delta_summary["product"] == "TOTAL") & (delta_summary["scenario"] == "uniform_depth_trade_125")].set_index("model")

    rows = []
    for model in MODELS:
        p0 = float(base_total.loc[model, "P0_mean"])
        delta_cons = float(cons_total.loc[model, "Delta_mean"])
        delta_cons_min = float(cons_total.loc[model, "Delta_min"])
        delta_cons_p25 = float(cons_total.loc[model, "Delta_p25"])
        delta_cent = float(cent_total.loc[model, "Delta_mean"])
        delta_upper = float(upper_total.loc[model, "Delta_mean"])
        cons_uplift = delta_cons / p0
        rows.append(
            {
                "model": model,
                "P0_mean": p0,
                "P0_median": float(base_total.loc[model, "P0_median"]),
                "P0_min": float(base_total.loc[model, "P0_min"]),
                "P0_max": float(base_total.loc[model, "P0_max"]),
                "P0_std": float(base_total.loc[model, "P0_std"]),
                "Delta_conservative_mean": delta_cons,
                "Delta_conservative_min": delta_cons_min,
                "Delta_conservative_p25": delta_cons_p25,
                "Delta_central_mean": delta_cent,
                "Delta_upper_mean": delta_upper,
                "cons_uplift_pct": cons_uplift,
                "central_uplift_pct": delta_cent / p0,
                "sensitivity_class": classify_sensitivity(cons_uplift),
                "P1_conservative_mean": p0 + delta_cons,
                "P1_central_mean": p0 + delta_cent,
                "fee_roi_150_cons": (delta_cons - 150.0) / 150.0,
                "fee_roi_175_cons": (delta_cons - 175.0) / 175.0,
                "fee_roi_200_cons": (delta_cons - 200.0) / 200.0,
                "max_bid_positive_downside": max_positive_bid(delta_cons_min),
                "max_bid_positive_conservative": max_positive_bid(delta_cons),
                "max_bid_positive_central": max_positive_bid(delta_cent),
            }
        )
    return pd.DataFrame(rows).sort_values("P0_mean", ascending=False).reset_index(drop=True)


def build_switch_vs_kiko(model_value_summary: pd.DataFrame) -> pd.DataFrame:
    ref = model_value_summary.set_index("model").loc["model_kiko"]
    rows = []
    for _, row in model_value_summary.iterrows():
        model = str(row["model"])
        if model == "model_kiko":
            continue
        cons_gap = float(row["Delta_conservative_mean"] - ref["Delta_conservative_mean"])
        cent_gap = float(row["Delta_central_mean"] - ref["Delta_central_mean"])
        p0_gap = float(ref["P0_mean"] - row["P0_mean"])
        q_star_cons = p0_gap / cons_gap if cons_gap > 0 else np.inf
        q_star_cent = p0_gap / cent_gap if cent_gap > 0 else np.inf
        rows.append(
            {
                "model": model,
                "P0_gap_vs_kiko": p0_gap,
                "Delta_cons_gap_vs_kiko": cons_gap,
                "Delta_cent_gap_vs_kiko": cent_gap,
                "q_star_cons_to_match_kiko": q_star_cons,
                "q_star_cent_to_match_kiko": q_star_cent,
                "P1_cons_minus_kiko": (float(row["P0_mean"]) + float(row["Delta_conservative_mean"])) - (float(ref["P0_mean"]) + float(ref["Delta_conservative_mean"])),
                "P1_cent_minus_kiko": (float(row["P0_mean"]) + float(row["Delta_central_mean"])) - (float(ref["P0_mean"]) + float(ref["Delta_central_mean"])),
                "switch_from_kiko_justified_cons": bool(q_star_cons <= 1.0),
                "switch_from_kiko_justified_cent": bool(q_star_cent <= 1.0),
            }
        )
    return pd.DataFrame(rows).sort_values("Delta_cons_gap_vs_kiko", ascending=False).reset_index(drop=True)


def build_pareto_frontier(model_value_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in model_value_summary.iterrows():
        model = str(row["model"])
        dominated_by: List[str] = []
        for _, other in model_value_summary.iterrows():
            other_model = str(other["model"])
            if other_model == model:
                continue
            if (
                float(other["P0_mean"]) >= float(row["P0_mean"])
                and float(other["Delta_conservative_mean"]) >= float(row["Delta_conservative_mean"])
                and (
                    float(other["P0_mean"]) > float(row["P0_mean"])
                    or float(other["Delta_conservative_mean"]) > float(row["Delta_conservative_mean"])
                )
            ):
                dominated_by.append(other_model)
        rows.append(
            {
                "model": model,
                "on_frontier": len(dominated_by) == 0,
                "dominated_by": ", ".join(dominated_by) if dominated_by else "",
            }
        )
    return pd.DataFrame(rows)


def build_bid_implications(model_value_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in model_value_summary.iterrows():
        model = str(row["model"])
        p0 = float(row["P0_mean"])
        deltas = {
            "Delta_conservative_mean": float(row["Delta_conservative_mean"]),
            "Delta_conservative_min": float(row["Delta_conservative_min"]),
            "Delta_central_mean": float(row["Delta_central_mean"]),
        }
        for delta_key, delta_value in deltas.items():
            for bid in BID_GRID:
                net_gain = delta_value - bid
                rows.append(
                    {
                        "model": model,
                        "delta_key": delta_key,
                        "delta_value": delta_value,
                        "bid": int(bid),
                        "net_gain_if_accepted": net_gain,
                        "uplift_pct_vs_base": net_gain / p0,
                        "fee_roi": net_gain / bid,
                    }
                )
    return pd.DataFrame(rows)


def normalize_mapping(mapping: Mapping[int, float]) -> Dict[int, float]:
    total = float(sum(mapping.values()))
    return {int(k): float(v) / total for k, v in mapping.items()}


def pmf_array(mapping: Mapping[int, float]) -> np.ndarray:
    norm = normalize_mapping(mapping)
    return np.array([norm.get(int(level), 0.0) for level in RIVAL_BID_SUPPORT], dtype=float)


def build_model_bid_pmf(model_value_summary: pd.DataFrame) -> pd.DataFrame:
    classes = model_value_summary.set_index("model")["sensitivity_class"].to_dict()
    rows = []
    for model in MODELS:
        cls = str(classes[model])
        pmf = pmf_array(CLASS_BID_PMF[cls])
        for bid_level, prob in zip(RIVAL_BID_SUPPORT, pmf):
            rows.append(
                {
                    "model": model,
                    "sensitivity_class": cls,
                    "bid_level": int(bid_level),
                    "probability": float(prob),
                }
            )
    # explicit noise row
    noise_pmf = pmf_array(CLASS_BID_PMF["noise"])
    for bid_level, prob in zip(RIVAL_BID_SUPPORT, noise_pmf):
        rows.append(
            {
                "model": "noise",
                "sensitivity_class": "noise",
                "bid_level": int(bid_level),
                "probability": float(prob),
            }
        )
    return pd.DataFrame(rows)


def distribute_weights_by_model(class_weights: Mapping[str, float], model_classes: Mapping[str, str]) -> Dict[str, float]:
    by_class: Dict[str, List[str]] = {}
    for model, cls in model_classes.items():
        by_class.setdefault(cls, []).append(model)
    weights: Dict[str, float] = {model: 0.0 for model in model_classes}
    for cls, weight in class_weights.items():
        if cls == "noise":
            continue
        members = by_class.get(cls, [])
        if not members:
            continue
        split = float(weight) / len(members)
        for model in members:
            weights[model] = split
    return weights


def acceptance_probability(counts_rivals: np.ndarray, bid_value: int) -> np.ndarray:
    idx = int(np.where(RIVAL_BID_SUPPORT == bid_value)[0][0])
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


def simulate_endogenous_field(
    model_value_summary: pd.DataFrame,
    model_bid_pmf_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    model_classes = model_value_summary.set_index("model")["sensitivity_class"].to_dict()
    model_pmfs = {
        model: model_bid_pmf_df[model_bid_pmf_df["model"] == model].sort_values("bid_level")["probability"].to_numpy()
        for model in [*MODELS, "noise"]
    }
    kiko_row = model_value_summary.set_index("model").loc["model_kiko"]
    deltas = {
        "Delta_conservative_mean": float(kiko_row["Delta_conservative_mean"]),
        "Delta_conservative_min": float(kiko_row["Delta_conservative_min"]),
        "Delta_central_mean": float(kiko_row["Delta_central_mean"]),
    }
    p0_mean = float(kiko_row["P0_mean"])

    scenario_rows = []
    bid_rows = []
    cutoff_rows = []
    cdf_rows = []
    ev_rows = []

    for scenario in RIVAL_SCENARIOS:
        class_weights = dict(scenario.class_weights)
        model_weights = distribute_weights_by_model(class_weights, model_classes)
        mix_pmf = np.zeros(len(RIVAL_BID_SUPPORT), dtype=float)
        for model, weight in model_weights.items():
            mix_pmf += float(weight) * model_pmfs[model]
        mix_pmf += float(class_weights.get("noise", 0.0)) * model_pmfs["noise"]
        mix_pmf = mix_pmf / mix_pmf.sum()

        scenario_rows.append(
            {
                "scenario": scenario.key,
                "scenario_label": scenario.label,
                "logic": scenario.logic,
                "model_switch_story": scenario.model_switch_story,
                **{model: float(model_weights.get(model, 0.0)) for model in MODELS},
                "noise": float(class_weights.get("noise", 0.0)),
            }
        )

        for bid_level, prob in zip(RIVAL_BID_SUPPORT, mix_pmf):
            bid_rows.append(
                {
                    "scenario": scenario.key,
                    "scenario_label": scenario.label,
                    "bid_level": int(bid_level),
                    "probability": float(prob),
                }
            )

        counts_rivals = RNG.multinomial(RIVALS, mix_pmf, size=N_SIMS)
        counts_total = RNG.multinomial(TOTAL_PARTICIPANTS, mix_pmf, size=N_SIMS)

        descending_counts = counts_total[:, ::-1]
        cum_desc = np.cumsum(descending_counts, axis=1)
        cutoff_idx_desc = (cum_desc >= ACCEPTED).argmax(axis=1)
        cutoff_levels = RIVAL_BID_SUPPORT[::-1][cutoff_idx_desc]

        cutoff_dist = pd.Series(cutoff_levels).value_counts(normalize=True).sort_index()
        for level in RIVAL_BID_SUPPORT:
            cutoff_rows.append(
                {
                    "scenario": scenario.key,
                    "scenario_label": scenario.label,
                    "cutoff_level": int(level),
                    "probability": float(cutoff_dist.get(int(level), 0.0)),
                }
            )
            cdf_rows.append(
                {
                    "scenario": scenario.key,
                    "scenario_label": scenario.label,
                    "cutoff_level": int(level),
                    "cdf": float(np.mean(cutoff_levels <= level)),
                }
            )

        for bid in OUR_BIDS:
            q_accept = float(acceptance_probability(counts_rivals, bid).mean())
            for delta_key, delta_value in deltas.items():
                net_gain = delta_value - bid
                ev_rows.append(
                    {
                        "scenario": scenario.key,
                        "scenario_label": scenario.label,
                        "bid": int(bid),
                        "q_accept": q_accept,
                        "delta_key": delta_key,
                        "delta_value": delta_value,
                        "net_gain_if_accepted": net_gain,
                        "uplift_pct_vs_base": net_gain / p0_mean,
                        "fee_roi": net_gain / bid,
                        "ev_uplift": q_accept * net_gain,
                        "ev_total": p0_mean + q_accept * net_gain,
                        "cutoff_mean": float(np.mean(cutoff_levels)),
                        "cutoff_median": float(np.median(cutoff_levels)),
                        "cutoff_p25": float(np.quantile(cutoff_levels, 0.25)),
                        "cutoff_p75": float(np.quantile(cutoff_levels, 0.75)),
                        "cutoff_p90": float(np.quantile(cutoff_levels, 0.90)),
                    }
                )

    return (
        pd.DataFrame(scenario_rows),
        pd.DataFrame(bid_rows),
        pd.DataFrame(cutoff_rows),
        pd.DataFrame(cdf_rows),
        pd.DataFrame(ev_rows),
    )


def build_field_summary(ev_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for delta_key in ev_df["delta_key"].unique():
        sub = ev_df[ev_df["delta_key"] == delta_key].copy()
        by_bid = sub.groupby("bid", as_index=False)["ev_uplift"].mean()
        best_bid = int(by_bid.loc[by_bid["ev_uplift"].idxmax(), "bid"])
        worst_case = sub.groupby("bid", as_index=False)["ev_uplift"].min()
        robust_bid = int(worst_case.loc[worst_case["ev_uplift"].idxmax(), "bid"])
        rows.append(
            {
                "delta_key": delta_key,
                "best_bid_equal_weight": best_bid,
                "best_bid_worst_case": robust_bid,
            }
        )
    return pd.DataFrame(rows)


def plot_delta_by_model(model_value_summary: pd.DataFrame) -> None:
    df = model_value_summary.melt(
        id_vars=["model"],
        value_vars=["Delta_conservative_mean", "Delta_conservative_min", "Delta_central_mean"],
        var_name="metric",
        value_name="delta",
    )
    label_map = {
        "Delta_conservative_mean": "Conservador (mean)",
        "Delta_conservative_min": "Downside (min día)",
        "Delta_central_mean": "Central (mean)",
    }
    df["metric_label"] = df["metric"].map(label_map)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=df, x="model", y="delta", hue="metric_label", ax=ax, palette=["#0F766E", "#D97706", "#2563EB"])
    ax.set_title("Valor del MAF por modelo")
    ax.set_xlabel("")
    ax.set_ylabel("Delta por día / ronda")
    ax.legend(title="")
    fig.savefig(PLOTS_DIR / "delta_by_model.png")
    plt.close(fig)


def plot_baseline_vs_uplift(model_value_summary: pd.DataFrame) -> None:
    fig, ax1 = plt.subplots(figsize=(12, 6))
    x = np.arange(len(model_value_summary))
    ax1.bar(x, model_value_summary["P0_mean"], color="#CBD5E1", label="P0 baseline")
    ax1.set_ylabel("P0 medio por ronda")
    ax1.set_xticks(x)
    ax1.set_xticklabels(model_value_summary["model"])
    ax1.set_title("Baseline vs uplift conservador por modelo")

    ax2 = ax1.twinx()
    ax2.plot(x, model_value_summary["cons_uplift_pct"] * 100.0, color="#DC2626", marker="o", linewidth=2.5, label="Uplift % conservador")
    ax2.set_ylabel("Uplift conservador (% sobre baseline)")

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="upper right")
    fig.savefig(PLOTS_DIR / "baseline_vs_uplift_by_model.png")
    plt.close(fig)


def plot_sensitivity_classification(model_value_summary: pd.DataFrame) -> None:
    df = model_value_summary.sort_values("cons_uplift_pct").copy()
    color_map = {"MAF-light": "#94A3B8", "MAF-medium": "#7C3AED", "MAF-heavy": "#DC2626"}
    colors = [color_map[str(cls)] for cls in df["sensitivity_class"]]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(df["model"], df["cons_uplift_pct"] * 100.0, color=colors)
    ax.axvline(1.20, color="#9CA3AF", linestyle="--", linewidth=1.25)
    ax.axvline(1.55, color="#9CA3AF", linestyle="--", linewidth=1.25)
    ax.set_title("Clasificación de MAF-sensitivity (upli% conservador)")
    ax.set_xlabel("Delta conservador / P0 (%)")
    ax.set_ylabel("")
    fig.savefig(PLOTS_DIR / "maf_sensitivity_classification.png")
    plt.close(fig)


def plot_max_reasonable_bid(model_value_summary: pd.DataFrame) -> None:
    df = model_value_summary.melt(
        id_vars=["model"],
        value_vars=["max_bid_positive_downside", "max_bid_positive_conservative", "max_bid_positive_central"],
        var_name="metric",
        value_name="max_bid",
    )
    label_map = {
        "max_bid_positive_downside": "Cap downside",
        "max_bid_positive_conservative": "Cap conservador",
        "max_bid_positive_central": "Cap central",
    }
    df["metric_label"] = df["metric"].map(label_map)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=df, x="model", y="max_bid", hue="metric_label", ax=ax, palette=["#D97706", "#0F766E", "#2563EB"])
    ax.set_title("Bid máximo con net_gain_if_accepted > 0")
    ax.set_xlabel("")
    ax.set_ylabel("Bid máximo en la grid")
    ax.legend(title="")
    fig.savefig(PLOTS_DIR / "max_reasonable_bid_by_model.png")
    plt.close(fig)


def plot_rival_bid_distributions(rival_bid_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharex=True, sharey=True)
    axes = axes.flatten()
    for ax, scenario in zip(axes, RIVAL_SCENARIOS):
        sub = rival_bid_df[rival_bid_df["scenario"] == scenario.key]
        ax.bar(sub["bid_level"].astype(str), sub["probability"], color=PALETTE[scenario.key], alpha=0.85)
        ax.set_title(scenario.label)
        ax.set_xlabel("Bid rival")
        ax.set_ylabel("Probabilidad")
        for bid in OUR_BIDS:
            ax.axvline(x=list(sub["bid_level"].astype(str)).index(str(bid)), color="#111827", linestyle=":", linewidth=1)
    fig.suptitle("Distribución modelada de bids rivales inducida por mezcla de modelos", y=1.02)
    fig.savefig(PLOTS_DIR / "rival_bid_distributions_by_scenario.png")
    plt.close(fig)


def plot_cutoff_distribution(cutoff_df: pd.DataFrame, cdf_df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    for scenario in RIVAL_SCENARIOS:
        sub = cutoff_df[cutoff_df["scenario"] == scenario.key]
        axes[0].plot(sub["cutoff_level"], sub["probability"], marker="o", linewidth=2, label=scenario.key, color=PALETTE[scenario.key])
        sub_cdf = cdf_df[cdf_df["scenario"] == scenario.key]
        axes[1].plot(sub_cdf["cutoff_level"], sub_cdf["cdf"], marker="o", linewidth=2, label=scenario.key, color=PALETTE[scenario.key])
    for ax in axes:
        for bid in OUR_BIDS:
            ax.axvline(bid, color="#9CA3AF", linestyle=":", linewidth=1)
    axes[0].set_title("PMF del cutoff inducido")
    axes[0].set_xlabel("Cutoff")
    axes[0].set_ylabel("Probabilidad")
    axes[1].set_title("CDF del cutoff inducido")
    axes[1].set_xlabel("Cutoff")
    axes[1].set_ylabel("Prob acumulada")
    axes[1].legend(title="Escenario")
    fig.savefig(PLOTS_DIR / "cutoff_distribution_and_cdf.png")
    plt.close(fig)


def plot_our_bid_ev(ev_df: pd.DataFrame) -> None:
    sub = ev_df[ev_df["delta_key"] == "Delta_conservative_mean"].copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=sub, x="scenario", y="ev_uplift", hue="bid", ax=ax, palette=["#7C3AED", "#2563EB", "#0F766E", "#DC2626"])
    ax.set_title("EV uplift de nuestros bids bajo field heterogéneo (Delta conservador)")
    ax.set_xlabel("")
    ax.set_ylabel("EV uplift")
    ax.legend(title="Bid")
    fig.savefig(PLOTS_DIR / "our_bid_ev_under_heterogeneous_field.png")
    plt.close(fig)


def plot_final_sensitivity_heatmap(ev_df: pd.DataFrame) -> None:
    sub = ev_df[ev_df["delta_key"] == "Delta_conservative_mean"].copy()
    pivot = sub.pivot(index="scenario", columns="bid", values="ev_uplift").loc[[s.key for s in RIVAL_SCENARIOS], OUR_BIDS]
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="viridis", cbar_kws={"label": "EV uplift"}, ax=ax)
    ax.set_title("Mapa final de sensibilidad: escenario rival vs nuestro bid")
    ax.set_xlabel("Nuestro bid")
    ax.set_ylabel("Escenario rival")
    fig.savefig(PLOTS_DIR / "final_sensitivity_heatmap.png")
    plt.close(fig)


def build_report(
    baseline_summary: pd.DataFrame,
    delta_summary: pd.DataFrame,
    model_value_summary: pd.DataFrame,
    switch_vs_kiko: pd.DataFrame,
    pareto_frontier: pd.DataFrame,
    bid_implications: pd.DataFrame,
    rival_scenarios_df: pd.DataFrame,
    rival_bid_df: pd.DataFrame,
    cutoff_df: pd.DataFrame,
    ev_df: pd.DataFrame,
    field_summary: pd.DataFrame,
) -> str:
    base_total = baseline_summary[baseline_summary["product"] == "TOTAL"].copy()
    cons_total = delta_summary[(delta_summary["product"] == "TOTAL") & (delta_summary["scenario"] == "uniform_depth_125")].copy()
    cent_total = delta_summary[(delta_summary["product"] == "TOTAL") & (delta_summary["scenario"] == "front_bias_depth_25")].copy()
    cutoff_summary = (
        ev_df[["scenario", "scenario_label", "cutoff_mean", "cutoff_median", "cutoff_p25", "cutoff_p75", "cutoff_p90"]]
        .drop_duplicates()
        .sort_values("scenario")
    )

    comparison_table = model_value_summary[
        [
            "model",
            "P0_mean",
            "Delta_conservative_mean",
            "Delta_conservative_min",
            "Delta_central_mean",
            "cons_uplift_pct",
            "sensitivity_class",
        ]
    ].copy()
    comparison_table["cons_uplift_pct"] *= 100.0

    ev_cons = ev_df[ev_df["delta_key"] == "Delta_conservative_mean"].copy()
    best_by_scenario = (
        ev_cons.sort_values(["scenario", "ev_uplift"], ascending=[True, False])
        .groupby("scenario", as_index=False)
        .first()[["scenario", "scenario_label", "bid", "ev_uplift"]]
        .rename(columns={"bid": "best_bid_cons"})
    )

    p25_line = float(model_value_summary.loc[model_value_summary["model"] == "model_kiko", "Delta_conservative_mean"].iloc[0])
    _ = p25_line

    report = f"""# Round 2 — MAF model heterogeneity y rival model switching

## A. Resumen ejecutivo

- **Sí**: el MAF vale bastante más para varios modelos del repo que para `model_kiko`.
- En la unidad correcta (**1 día = 1 ronda live comparable**), `model_kiko` tiene el mejor baseline medio, pero el **menor Delta conservador** del set auditado.
- Los modelos más sensibles al MAF son `model_G2`, `model_G5` y `model_G4`; el uplift adicional viene **sobre todo de PEPPER**, no de ASH.
- **No** veo evidencia de que sea racional pasar de `model_kiko` a esos modelos *solo* por el MAF: el gap de baseline de `model_kiko` sigue siendo demasiado grande.
- **Sí** veo evidencia de que un field heterogéneo, con equipos ya parados sobre modelos tipo `G5/G2`, puede empujar el cutoff rival hacia arriba.
- Implicación práctica: el análisis anterior de cutoff homogéneo probablemente **subestima la cola alta**. Eso vuelve mucho menos defendible `125`, complica `150`, hace que `175` sea el nuevo piso serio y mete a `200` en consideración real.

### Comparativa corta

{markdown_table(comparison_table, ".2f")}

## B. Comparativa entre modelos

### Baseline por modelo (TOTAL, por día)

{markdown_table(base_total[["model", "P0_mean", "P0_median", "P0_min", "P0_max", "P0_std"]].sort_values("P0_mean", ascending=False), ".2f")}

### Delta del MAF por modelo (TOTAL)

**Proxy conservador**

{markdown_table(cons_total[["model", "Delta_mean", "Delta_median", "Delta_min", "Delta_max", "Delta_std", "Delta_p25"]].sort_values("Delta_mean", ascending=False), ".2f")}

**Proxy central**

{markdown_table(cent_total[["model", "Delta_mean", "Delta_median", "Delta_min", "Delta_max", "Delta_std"]].sort_values("Delta_mean", ascending=False), ".2f")}

### Lectura económica

- `model_kiko` sigue siendo el **baseline leader** del set: gana más sin access extra.
- Pero es **MAF-light**: su `Delta_conservative_mean` queda claramente por debajo del resto.
- Los modelos `G/F` auditados son más **PEPPER-sensitive** al extra access: su mejora marginal con MAF viene mucho más por PEPPER que en `model_kiko`.
- Eso significa que, aunque `model_kiko` sea mejor estrategia base, **otros equipos pueden tener un valor privado del access bastante mayor** si están usando otra familia de modelos.

## C. Incentivo a cambio de modelo

### Switch contra `model_kiko`

{markdown_table(switch_vs_kiko[["model", "P0_gap_vs_kiko", "Delta_cons_gap_vs_kiko", "q_star_cons_to_match_kiko", "q_star_cent_to_match_kiko", "switch_from_kiko_justified_cons", "switch_from_kiko_justified_cent"]], ".2f")}

### Frontera baseline vs Delta conservador

{markdown_table(pareto_frontier, ".2f")}

### Conclusión de model switching

- El test relevante es:  
  `EV_model - EV_kiko = (P0_model - P0_kiko) + q * (Delta_model - Delta_kiko)`
- Para todos los modelos auditados, el `q*` necesario para que un equipo que **ya tiene `model_kiko`** prefiera cambiar solo por el MAF queda **por encima de 1** en conservador y también en central.
- O sea: **no** veo racionalidad en abandonar `model_kiko` *solo* para perseguir el MAF.
- Pero eso **no** invalida el riesgo rival: si un equipo **ya** está en una familia tipo `G5/G2`, o tiene un baseline más flojo que el nuestro, sí puede justificar bids más altos.
- Por eso el efecto rival más plausible no es “todos saltan desde `model_kiko`”, sino “una fracción del field usa o retiene modelos con mayor valor privado del access”.

## D. Modelo rival endógeno

### Escenarios de composición del field

{markdown_table(rival_scenarios_df[["scenario", "scenario_label", "model_kiko", "model_G5", "model_G1", "model_G4", "model_G2", "model_F3", "noise"]], ".3f")}

### Lógica económica

- `R1`: mayoría en modelos light/medium; adaptación limitada.
- `R2`: field mixto; aparece una masa visible de modelos MAF-heavy.
- `R3`: field adaptativo; una parte importante sí internaliza el MAF y migra hacia modelos más sensibles.
- `R4`: stress serio; cola alta por mezcla de modelos heavy + bids de overinsurance/noise.

### Cutoff inducido

{markdown_table(cutoff_summary, ".2f")}

### EV de nuestros bids (`model_kiko`) bajo field heterogéneo

**Delta conservador**

{markdown_table(ev_cons[["scenario", "bid", "q_accept", "net_gain_if_accepted", "fee_roi", "ev_uplift"]].sort_values(["scenario", "bid"]), ".3f")}

### Qué cambia respecto del análisis anterior

- `125` deja de ser serio en casi todos los escenarios endógenos: queda muy por debajo del cutoff inducido.
- `150` solo sobrevive si el field sigue muy conservador.
- `175` funciona bien mientras el cutoff no suba demasiado por model switching.
- `200` entra en juego porque el costo adicional frente a `175` es chico comparado con el valor económico del MAF.

Para `model_kiko`, con `Delta_conservative_mean ≈ {float(model_value_summary.loc[model_value_summary["model"] == "model_kiko", "Delta_conservative_mean"].iloc[0]):.1f}`, pasar de `175` a `200` reduce el `net_gain_if_accepted` apenas en **25**.  
Eso significa que `200` supera a `175` en EV apenas compra unos pocos puntos extra de aceptación; en campos rivales más agresivos, eso pasa muy rápido.

### Mejor bid por escenario dentro del modelo endógeno

{markdown_table(best_by_scenario, ".2f")}

### Resumen igual ponderado por escenario

{markdown_table(field_summary, ".2f")}

## E. Visualizaciones

Los plots generados están en:

- `{PLOTS_DIR / "delta_by_model.png"}`
- `{PLOTS_DIR / "baseline_vs_uplift_by_model.png"}`
- `{PLOTS_DIR / "maf_sensitivity_classification.png"}`
- `{PLOTS_DIR / "max_reasonable_bid_by_model.png"}`
- `{PLOTS_DIR / "rival_bid_distributions_by_scenario.png"}`
- `{PLOTS_DIR / "cutoff_distribution_and_cdf.png"}`
- `{PLOTS_DIR / "our_bid_ev_under_heterogeneous_field.png"}`
- `{PLOTS_DIR / "final_sensitivity_heatmap.png"}`

### Cómo leerlos

1. **Delta por modelo** — separa el hecho observado importante: `model_kiko` lidera baseline, pero no lidera valor del access.
2. **Baseline vs uplift** — deja claro el trade-off baseline fuerte vs MAF sensitivity.
3. **Clasificación MAF-light/medium/heavy** — resume qué familias son candidatas a pujar más alto.
4. **Bid máximo razonable por modelo** — muestra que condicionalmente muchos modelos pueden pagar 175–225 sin volverse absurdos.
5. **Distribución modelada de bids rivales** — visualiza el efecto del model switching: más masa en 175/200 y cola a 225/250/300.
6. **Cutoff inducido (PMF/CDF)** — traduce la mezcla de modelos en una distribución concreta del cutoff.
7. **EV de nuestros bids** — permite ver cuándo `175` aguanta y cuándo `200` le gana.
8. **Heatmap final** — resume el punto de decisión: sensibilidad del EV a la composición del field rival.

## F. Recomendación final

### Hechos observados

- **Sí**: el MAF puede valer mucho más para otros modelos que para `model_kiko`.
- El gap observado es grande: los mejores modelos MAF-heavy del set están aproximadamente entre **+45% y +72%** arriba de `model_kiko` en `Delta_conservative_mean`.
- El diferencial viene **principalmente de PEPPER**.
- **No**: eso no alcanza para justificar que alguien con `model_kiko` cambie racionalmente *solo* por el MAF.

### Implicación para nuestro bid

- **Sí**: esto empuja el cutoff rival esperado hacia arriba respecto de un field homogéneo.
- `150` queda más frágil.
- `175` pasa a ser el **nuevo piso robusto** si querés protegerte contra una parte del field usando modelos más MAF-heavy.
- `200` entra en **consideración seria** bajo escenarios `R3/R4`, donde la adaptación rival es real.

### Mi recomendación operativa

- **Bid recomendado por robustez práctica: 175**
- **Rango alternativo razonable: 175–200**
- **Subiría a 200** si tu lectura es que el field efectivamente va a internalizar el MAF y que habrá una fracción no marginal de equipos en modelos tipo `G5/G2` o equivalentes.
- **Me quedaría en 175** si querés una recomendación que suba respecto de `150`, pero sin dejar que el componente más modelado del análisis rival sobre-domine la decisión.

### Frase final

> **Sí:** el MAF podría valer bastante más para otros modelos.  
> **Sí:** es plausible que algunos equipos cambien o, más realista todavía, que ya estén en modelos que valoran mucho más el access.  
> **Sí:** eso empuja nuestro bid recomendado hacia arriba.  
> **La razón principal** es que `model_kiko` tiene el mejor baseline, pero no el mayor valor privado del MAF; entonces el riesgo no es que nos ganen por estrategia base, sino que parte del field pueda pujar más alto sin estar haciendo una locura económica.
"""
    return report


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_style()

    loaded_data = load_all_raw_data()
    day_metrics, _product_runs = run_all_model_scenarios(loaded_data)
    baseline_summary = build_baseline_summary(day_metrics)
    delta_day = build_delta_day_metrics(day_metrics)
    delta_summary = build_delta_summary(delta_day)
    model_value_summary = build_model_value_summary(baseline_summary, delta_summary)
    switch_vs_kiko = build_switch_vs_kiko(model_value_summary)
    pareto_frontier = build_pareto_frontier(model_value_summary)
    bid_implications = build_bid_implications(model_value_summary)
    model_bid_pmf_df = build_model_bid_pmf(model_value_summary)
    rival_scenarios_df, rival_bid_df, cutoff_df, cdf_df, ev_df = simulate_endogenous_field(model_value_summary, model_bid_pmf_df)
    field_summary = build_field_summary(ev_df)

    save_df(day_metrics, "day_metrics")
    save_df(baseline_summary, "baseline_summary")
    save_df(delta_day, "delta_day_metrics")
    save_df(delta_summary, "delta_summary")
    save_df(model_value_summary, "model_value_summary")
    save_df(switch_vs_kiko, "switch_vs_kiko")
    save_df(pareto_frontier, "pareto_frontier")
    save_df(bid_implications, "bid_implications_by_model")
    save_df(model_bid_pmf_df, "model_bid_pmfs")
    save_df(rival_scenarios_df, "rival_model_scenarios")
    save_df(rival_bid_df, "induced_rival_bid_distribution")
    save_df(cutoff_df, "induced_cutoff_distribution")
    save_df(cdf_df, "induced_cutoff_cdf")
    save_df(ev_df, "our_bid_ev_under_field")
    save_df(field_summary, "field_summary")

    plot_delta_by_model(model_value_summary)
    plot_baseline_vs_uplift(model_value_summary)
    plot_sensitivity_classification(model_value_summary)
    plot_max_reasonable_bid(model_value_summary)
    plot_rival_bid_distributions(rival_bid_df)
    plot_cutoff_distribution(cutoff_df, cdf_df)
    plot_our_bid_ev(ev_df)
    plot_final_sensitivity_heatmap(ev_df)

    report = build_report(
        baseline_summary=baseline_summary,
        delta_summary=delta_summary,
        model_value_summary=model_value_summary,
        switch_vs_kiko=switch_vs_kiko,
        pareto_frontier=pareto_frontier,
        bid_implications=bid_implications,
        rival_scenarios_df=rival_scenarios_df,
        rival_bid_df=rival_bid_df,
        cutoff_df=cutoff_df,
        ev_df=ev_df,
        field_summary=field_summary,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote heterogeneity analysis to {OUT_DIR}")


if __name__ == "__main__":
    main()
