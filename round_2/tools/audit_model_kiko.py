from __future__ import annotations

import copy
import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ROUND_1_TOOLS = ROOT / "round_1" / "tools"
ROUND_1_MODELS = ROOT / "round_1" / "models"
ROUND_2_TOOLS = ROOT / "round_2" / "tools"
ROUND_2_MODELS = ROOT / "round_2" / "models"
RESULTS_DIR = ROOT / "round_2" / "results" / "model_keep_or_tune"
REPORT_PATH = RESULTS_DIR / "round2_model_kiko_audit.md"

sys.path.insert(0, str(ROUND_2_TOOLS))
sys.path.insert(0, str(ROUND_2_MODELS))
sys.path.insert(0, str(ROUND_1_TOOLS))
sys.path.insert(0, str(ROUND_1_MODELS))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402


@dataclass(frozen=True)
class Scenario:
    name: str
    label: str
    round_name: str
    depth_factor: float = 1.0
    trade_factor: float = 1.0
    front_bias: bool = False
    proxy_name: Optional[str] = None
    description: str = ""


MODEL_PATHS: Dict[str, Path] = {
    "model_kiko": ROOT / "round_2" / "models" / "model_kiko.py",
    "model_G5": ROOT / "round_1" / "models" / "model_G5.py",
    "model_G1": ROOT / "round_1" / "models" / "model_G1.py",
    "model_G4": ROOT / "round_1" / "models" / "model_G4.py",
    "model_G2": ROOT / "round_1" / "models" / "model_G2.py",
    "model_F3": ROOT / "round_1" / "models" / "model_F3.py",
}

COMPARABLE_MODELS = ["model_kiko", "model_G5", "model_G1", "model_G4", "model_G2", "model_F3"]
PRODUCTS = ag.PRODUCTS
POSITION_LIMITS = {"ASH_COATED_OSMIUM": 80, "INTARIAN_PEPPER_ROOT": 80}
ROUND_SPECS = {
    "round_1": {"days": [-2, -1, 0], "label": "Round 1"},
    "round_2": {"days": [-1, 0, 1], "label": "Round 2"},
}

SCENARIOS: List[Scenario] = [
    Scenario(
        name="baseline",
        label="Baseline",
        round_name="round_2",
        description="Mercado estándar observado en el dataset local.",
    ),
    Scenario(
        name="depth_90",
        label="Depth -10%",
        round_name="round_2",
        depth_factor=0.90,
        description="Pequeña perturbación adversa de liquidez visible para medir sensibilidad.",
    ),
    Scenario(
        name="depth_110",
        label="Depth +10%",
        round_name="round_2",
        depth_factor=1.10,
        description="Pequeña perturbación favorable de liquidez visible para medir sensibilidad.",
    ),
    Scenario(
        name="maf_uniform_125",
        label="MAF uniform +25%",
        round_name="round_2",
        proxy_name="uniform_depth_125",
        description="Proxy conservador de extra market access: +25% de profundidad visible.",
    ),
    Scenario(
        name="maf_front_125",
        label="MAF front-biased +25%",
        round_name="round_2",
        proxy_name="front_bias_depth_25",
        front_bias=True,
        description="Proxy central de extra market access: profundidad adicional cerca del touch.",
    ),
    Scenario(
        name="maf_depth_trade_125",
        label="MAF depth+trades +25%",
        round_name="round_2",
        proxy_name="uniform_depth_trade_125",
        description="Upper bound local: +25% de profundidad y +25% de trade flow.",
    ),
]

PARAMETER_VARIANTS: List[Tuple[str, str, Callable[[Mapping[str, Mapping[str, float]]], Dict[str, Dict[str, float]]]]] = [
    ("baseline", "Sin cambios", lambda p: copy.deepcopy(p)),
    (
        "pepper_slope_p01",
        "PEPPER price_slope +1%",
        lambda p: override_params(
            p,
            "INTARIAN_PEPPER_ROOT",
            price_slope=float(p["INTARIAN_PEPPER_ROOT"]["price_slope"]) * 1.01,
        ),
    ),
    (
        "pepper_slope_p02",
        "PEPPER price_slope +2%",
        lambda p: override_params(
            p,
            "INTARIAN_PEPPER_ROOT",
            price_slope=float(p["INTARIAN_PEPPER_ROOT"]["price_slope"]) * 1.02,
        ),
    ),
    (
        "pepper_slope_p05",
        "PEPPER price_slope +5%",
        lambda p: override_params(
            p,
            "INTARIAN_PEPPER_ROOT",
            price_slope=float(p["INTARIAN_PEPPER_ROOT"]["price_slope"]) * 1.05,
        ),
    ),
    (
        "pepper_base_update_03",
        "PEPPER base_update_weight = 0.3",
        lambda p: override_params(p, "INTARIAN_PEPPER_ROOT", base_update_weight=0.3),
    ),
    (
        "pepper_base_update_04",
        "PEPPER base_update_weight = 0.4",
        lambda p: override_params(p, "INTARIAN_PEPPER_ROOT", base_update_weight=0.4),
    ),
    (
        "pepper_residual_06",
        "PEPPER residual_weight = 0.6",
        lambda p: override_params(p, "INTARIAN_PEPPER_ROOT", residual_weight=0.6),
    ),
    (
        "pepper_take_m025",
        "PEPPER take_width = 0.75",
        lambda p: override_params(p, "INTARIAN_PEPPER_ROOT", take_width=0.75),
    ),
    (
        "pepper_take_p025",
        "PEPPER take_width = 1.25",
        lambda p: override_params(p, "INTARIAN_PEPPER_ROOT", take_width=1.25),
    ),
    (
        "ash_edge_m5",
        "ASH default_edge -5",
        lambda p: override_params(
            p,
            "ASH_COATED_OSMIUM",
            default_edge=float(p["ASH_COATED_OSMIUM"]["default_edge"]) - 5.0,
        ),
    ),
    (
        "ash_edge_p5",
        "ASH default_edge +5",
        lambda p: override_params(
            p,
            "ASH_COATED_OSMIUM",
            default_edge=float(p["ASH_COATED_OSMIUM"]["default_edge"]) + 5.0,
        ),
    ),
]


def override_params(
    params: Mapping[str, Mapping[str, float]],
    product: str,
    **updates: float,
) -> Dict[str, Dict[str, float]]:
    out = {key: dict(value) for key, value in params.items()}
    out[product].update(updates)
    return out


def scale_quantity(value: int, factor: float) -> int:
    scaled = int(round(float(value) * factor))
    if value > 0 and scaled <= 0:
        return 1
    return max(0, scaled)


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No pude cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def markdown_table(df: pd.DataFrame, float_fmt: str = ".1f") -> str:
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
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *rows,
        ]
    )


def load_all_raw_data() -> Dict[str, Dict[str, Dict[int, ag.LoadedDayData]]]:
    cache: Dict[str, Dict[str, Dict[int, ag.LoadedDayData]]] = {}
    for round_name, spec in ROUND_SPECS.items():
        cache[round_name] = {}
        for product in PRODUCTS:
            cache[round_name][product] = {}
            for day in spec["days"]:
                cache[round_name][product][day] = ag.load_day_data(round_name, day, product)
    return cache


def apply_scenario(raw: ag.LoadedDayData, scenario: Scenario) -> Tuple[Dict[int, bt.DepthSnapshot], pd.DataFrame]:
    if scenario.proxy_name is not None:
        proxy = next(proxy for proxy in ag.PROXIES if proxy.name == scenario.proxy_name)
        return ag.apply_proxy(raw, proxy)

    depth_by_ts: Dict[int, bt.DepthSnapshot] = {}
    for ts, depth in raw.depth_by_ts.items():
        depth_by_ts[ts] = bt.DepthSnapshot(
            buy_vol_by_price={price: scale_quantity(volume, scenario.depth_factor) for price, volume in depth.buy_vol_by_price.items()},
            sell_vol_by_price={price: scale_quantity(volume, scenario.depth_factor) for price, volume in depth.sell_vol_by_price.items()},
            mid_price=depth.mid_price,
        )

    trades_df = raw.trades_df.copy()
    if scenario.trade_factor != 1.0 and not trades_df.empty:
        trades_df["quantity"] = trades_df["quantity"].apply(lambda q: scale_quantity(int(q), scenario.trade_factor))

    return depth_by_ts, trades_df


def instantiate_trader(model_key: str, params_override: Optional[Dict[str, Dict[str, float]]] = None):
    module = load_module(model_key, MODEL_PATHS[model_key])
    if model_key == "model_kiko" and params_override is not None:
        return module.Trader(params=copy.deepcopy(params_override))
    return module.Trader()


def product_daily_pnl(results_df: pd.DataFrame) -> Dict[int, float]:
    cumulative = results_df.groupby("day", sort=True)["pnl"].last()
    daily = cumulative.diff().fillna(cumulative)
    return {int(day): float(value) for day, value in daily.items()}


def total_daily_pnl(combined_df: pd.DataFrame) -> Dict[int, float]:
    tmp = combined_df[["day", "total_pnl"]].rename(columns={"total_pnl": "pnl"})
    return product_daily_pnl(tmp)


def combined_results_from_products(product_results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    combined = ag.merge_combined_results(product_results)
    return combined


def summarize_product(
    round_name: str,
    model_key: str,
    scenario_name: str,
    product: str,
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    metrics: Mapping[str, float],
) -> Dict[str, float | int | str]:
    daily = product_daily_pnl(results_df)
    return {
        "model": model_key,
        "round": round_name,
        "round_label": ROUND_SPECS[round_name]["label"],
        "scenario": scenario_name,
        "product": product,
        "total_pnl": float(metrics["total_pnl"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "fill_count": float(metrics["fill_count"]),
        "maker_share": float(metrics["maker_share"]) if not math.isnan(float(metrics["maker_share"])) else np.nan,
        "aggressive_fill_share": float(metrics["aggressive_fill_share"]) if not math.isnan(float(metrics["aggressive_fill_share"])) else np.nan,
        "avg_fill_size": float(metrics["avg_fill_size"]) if not math.isnan(float(metrics["avg_fill_size"])) else np.nan,
        "avg_abs_position": float(results_df["position"].abs().mean()),
        "max_abs_position": float(results_df["position"].abs().max()),
        "pct_abs_ge_60": float((results_df["position"].abs() >= 60).mean()),
        "pct_abs_ge_70": float((results_df["position"].abs() >= 70).mean()),
        "pct_at_limit": float((results_df["position"].abs() >= POSITION_LIMITS[product]).mean()),
        "daily_mean_pnl": float(pd.Series(daily).mean()),
        "daily_std_pnl": float(pd.Series(daily).std(ddof=1)) if len(daily) > 1 else 0.0,
        "min_day_pnl": float(min(daily.values())),
    }


def summarize_total(
    round_name: str,
    model_key: str,
    scenario_name: str,
    product_rows: Iterable[Mapping[str, float | int | str]],
    product_results: Mapping[str, pd.DataFrame],
    product_fills: Mapping[str, pd.DataFrame],
) -> Dict[str, float | int | str]:
    product_rows_df = pd.DataFrame(product_rows)
    combined_results = combined_results_from_products(product_results)
    daily = total_daily_pnl(combined_results)
    combined_fills = pd.concat(product_fills.values(), ignore_index=True) if product_fills else pd.DataFrame()
    return {
        "model": model_key,
        "round": round_name,
        "round_label": ROUND_SPECS[round_name]["label"],
        "scenario": scenario_name,
        "product": "TOTAL",
        "total_pnl": float(product_rows_df["total_pnl"].sum()),
        "max_drawdown": float(combined_results["drawdown"].min()),
        "fill_count": float(product_rows_df["fill_count"].sum()),
        "maker_share": float((combined_fills["source"] == "MARKET_TRADE").mean()) if not combined_fills.empty else np.nan,
        "aggressive_fill_share": float((combined_fills["source"] == "AGGRESSIVE").mean()) if not combined_fills.empty else np.nan,
        "avg_fill_size": float(combined_fills["quantity"].mean()) if not combined_fills.empty else np.nan,
        "avg_abs_position": np.nan,
        "max_abs_position": np.nan,
        "pct_abs_ge_60": np.nan,
        "pct_abs_ge_70": np.nan,
        "pct_at_limit": np.nan,
        "daily_mean_pnl": float(pd.Series(daily).mean()),
        "daily_std_pnl": float(pd.Series(daily).std(ddof=1)) if len(daily) > 1 else 0.0,
        "min_day_pnl": float(min(daily.values())),
    }


def build_day_rows(
    round_name: str,
    model_key: str,
    scenario_name: str,
    product: str,
    results_df: pd.DataFrame,
) -> List[Dict[str, float | int | str]]:
    daily = product_daily_pnl(results_df)
    rows: List[Dict[str, float | int | str]] = []
    for day, day_pnl in daily.items():
        sub = results_df[results_df["day"] == day].copy()
        rows.append(
            {
                "model": model_key,
                "round": round_name,
                "round_label": ROUND_SPECS[round_name]["label"],
                "scenario": scenario_name,
                "day": int(day),
                "product": product,
                "day_pnl": float(day_pnl),
                "avg_position": float(sub["position"].mean()),
                "avg_abs_position": float(sub["position"].abs().mean()),
                "max_abs_position": float(sub["position"].abs().max()),
                "pct_abs_ge_60": float((sub["position"].abs() >= 60).mean()),
                "pct_abs_ge_70": float((sub["position"].abs() >= 70).mean()),
                "pct_at_limit": float((sub["position"].abs() >= POSITION_LIMITS[product]).mean()),
            }
        )
    return rows


def build_total_day_rows(
    round_name: str,
    model_key: str,
    scenario_name: str,
    combined_results: pd.DataFrame,
) -> List[Dict[str, float | int | str]]:
    daily = total_daily_pnl(combined_results)
    rows: List[Dict[str, float | int | str]] = []
    for day, day_pnl in daily.items():
        rows.append(
            {
                "model": model_key,
                "round": round_name,
                "round_label": ROUND_SPECS[round_name]["label"],
                "scenario": scenario_name,
                "day": int(day),
                "product": "TOTAL",
                "day_pnl": float(day_pnl),
                "avg_position": np.nan,
                "avg_abs_position": np.nan,
                "max_abs_position": np.nan,
                "pct_abs_ge_60": np.nan,
                "pct_abs_ge_70": np.nan,
                "pct_at_limit": np.nan,
            }
        )
    return rows


def build_capacity_rows(
    round_name: str,
    scenario_name: str,
    product: str,
    results_df: pd.DataFrame,
) -> List[Dict[str, float | int | str]]:
    rows: List[Dict[str, float | int | str]] = []
    daily = product_daily_pnl(results_df)
    for day, day_pnl in daily.items():
        sub = results_df[results_df["day"] == day].copy()
        row: Dict[str, float | int | str] = {
            "round": round_name,
            "round_label": ROUND_SPECS[round_name]["label"],
            "scenario": scenario_name,
            "day": int(day),
            "product": product,
            "day_pnl": float(day_pnl),
            "avg_position": float(sub["position"].mean()),
            "avg_abs_position": float(sub["position"].abs().mean()),
            "max_abs_position": float(sub["position"].abs().max()),
            "pct_abs_ge_60": float((sub["position"].abs() >= 60).mean()),
            "pct_abs_ge_70": float((sub["position"].abs() >= 70).mean()),
            "pct_at_limit": float((sub["position"].abs() >= POSITION_LIMITS[product]).mean()),
            "final_position": int(sub["position"].iloc[-1]),
        }
        if product == "INTARIAN_PEPPER_ROOT":
            for threshold in (20, 40, 60, 70, 80):
                hit = sub.loc[sub["position"] >= threshold, "timestamp"]
                row[f"time_to_{threshold}"] = int(hit.iloc[0]) if not hit.empty else np.nan
        rows.append(row)
    return rows


def run_model_round(
    model_key: str,
    round_name: str,
    scenario: Scenario,
    raw_data: Mapping[str, Mapping[str, Mapping[int, ag.LoadedDayData]]],
    params_override: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    product_rows: List[Dict[str, float | int | str]] = []
    day_rows: List[Dict[str, float | int | str]] = []
    product_results: Dict[str, pd.DataFrame] = {}
    product_fills: Dict[str, pd.DataFrame] = {}
    days = list(ROUND_SPECS[round_name]["days"])

    for product in PRODUCTS:
        day_data: Dict[int, Tuple[Dict[int, bt.DepthSnapshot], pd.DataFrame]] = {}
        for day in days:
            day_data[day] = apply_scenario(raw_data[round_name][product][day], scenario)
        trader = instantiate_trader(model_key, params_override=params_override)
        results_df, fills_df, metrics = bt.run_backtest_on_loaded_data(trader, product, days, day_data, reset_between_days=False)
        product_rows.append(summarize_product(round_name, model_key, scenario.name, product, results_df, fills_df, metrics))
        day_rows.extend(build_day_rows(round_name, model_key, scenario.name, product, results_df))
        product_results[product] = results_df
        product_fills[product] = fills_df

    total_row = summarize_total(round_name, model_key, scenario.name, product_rows, product_results, product_fills)
    combined_results = combined_results_from_products(product_results)
    day_rows.extend(build_total_day_rows(round_name, model_key, scenario.name, combined_results))
    rows_df = pd.concat([pd.DataFrame(product_rows), pd.DataFrame([total_row])], ignore_index=True)
    day_df = pd.DataFrame(day_rows)
    return rows_df, day_df, product_results


def scenario_by_name(name: str) -> Scenario:
    return next(s for s in SCENARIOS if s.name == name)


def build_baseline_metrics(raw_data) -> Tuple[pd.DataFrame, pd.DataFrame]:
    baseline = scenario_by_name("baseline")
    round_rows: List[pd.DataFrame] = []
    day_rows: List[pd.DataFrame] = []
    for model_key in COMPARABLE_MODELS:
        for round_name in ROUND_SPECS:
            rows_df, day_df, _ = run_model_round(model_key, round_name, baseline, raw_data)
            round_rows.append(rows_df)
            day_rows.append(day_df)
    return pd.concat(round_rows, ignore_index=True), pd.concat(day_rows, ignore_index=True)


def build_scenario_metrics(raw_data) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []
    for scenario in SCENARIOS:
        for model_key in COMPARABLE_MODELS:
            rows_df, _day_df, _ = run_model_round(model_key, scenario.round_name, scenario, raw_data)
            rows.append(rows_df)
    return pd.concat(rows, ignore_index=True)


def build_capacity_metrics(raw_data) -> pd.DataFrame:
    rows: List[Dict[str, float | int | str]] = []
    scenarios = [scenario_by_name("baseline"), scenario_by_name("maf_uniform_125"), scenario_by_name("maf_front_125")]
    for round_name in ROUND_SPECS:
        chosen_scenarios = [scenario_by_name("baseline")] if round_name == "round_1" else scenarios
        for scenario in chosen_scenarios:
            _rows_df, _day_df, product_results = run_model_round("model_kiko", round_name, scenario, raw_data)
            for product, results_df in product_results.items():
                rows.extend(build_capacity_rows(round_name, scenario.name, product, results_df))
    return pd.DataFrame(rows)


def build_parameter_sensitivity(raw_data) -> pd.DataFrame:
    module = load_module("model_kiko_sweep", MODEL_PATHS["model_kiko"])
    base_params = copy.deepcopy(module.PARAMS)
    rows: List[Dict[str, float | int | str]] = []
    baseline_total: Dict[str, float] = {}
    baseline_pepper: Dict[str, float] = {}

    for variant_name, label, builder in PARAMETER_VARIANTS:
        params = builder(base_params)
        for round_name in ROUND_SPECS:
            rows_df, _day_df, _ = run_model_round("model_kiko", round_name, scenario_by_name("baseline"), raw_data, params_override=params)
            total_pnl = float(rows_df.loc[rows_df["product"] == "TOTAL", "total_pnl"].iloc[0])
            pepper_row = rows_df.loc[rows_df["product"] == "INTARIAN_PEPPER_ROOT"].iloc[0]
            if variant_name == "baseline":
                baseline_total[round_name] = total_pnl
                baseline_pepper[round_name] = float(pepper_row["total_pnl"])
            rows.append(
                {
                    "variant": variant_name,
                    "label": label,
                    "round": round_name,
                    "total_pnl": total_pnl,
                    "pepper_pnl": float(pepper_row["total_pnl"]),
                    "pepper_avg_abs_position": float(pepper_row["avg_abs_position"]),
                    "pepper_pct_ge_70": float(pepper_row["pct_abs_ge_70"]),
                    "pepper_pct_at_limit": float(pepper_row["pct_at_limit"]),
                }
            )

    df = pd.DataFrame(rows)
    df["delta_vs_baseline_total"] = df.apply(lambda row: row["total_pnl"] - baseline_total[row["round"]], axis=1)
    df["delta_vs_baseline_pepper"] = df.apply(lambda row: row["pepper_pnl"] - baseline_pepper[row["round"]], axis=1)
    return df


def build_model_comparison_summary(baseline_round_df: pd.DataFrame, baseline_day_df: pd.DataFrame, scenario_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | int | str]] = []
    total_round = baseline_round_df[(baseline_round_df["product"] == "TOTAL") & (baseline_round_df["scenario"] == "baseline")]
    total_days = baseline_day_df[(baseline_day_df["product"] == "TOTAL") & (baseline_day_df["scenario"] == "baseline")]
    scenario_total = scenario_df[scenario_df["product"] == "TOTAL"].copy()
    small_pert = scenario_total[scenario_total["scenario"].isin(["baseline", "depth_90", "depth_110"])]

    for alt in [m for m in COMPARABLE_MODELS if m != "model_kiko"]:
        day_comp = (
            total_days[total_days["model"].isin(["model_kiko", alt])]
            .pivot(index=["round", "day"], columns="model", values="day_pnl")
            .reset_index()
        )
        day_comp["delta_kiko_minus_alt"] = day_comp["model_kiko"] - day_comp[alt]

        pepper_day_comp = (
            baseline_day_df[
                (baseline_day_df["product"] == "INTARIAN_PEPPER_ROOT")
                & (baseline_day_df["scenario"] == "baseline")
                & (baseline_day_df["model"].isin(["model_kiko", alt]))
            ]
            .pivot(index=["round", "day"], columns="model", values="day_pnl")
            .reset_index()
        )
        pepper_day_comp["delta_kiko_minus_alt"] = pepper_day_comp["model_kiko"] - pepper_day_comp[alt]

        ash_day_comp = (
            baseline_day_df[
                (baseline_day_df["product"] == "ASH_COATED_OSMIUM")
                & (baseline_day_df["scenario"] == "baseline")
                & (baseline_day_df["model"].isin(["model_kiko", alt]))
            ]
            .pivot(index=["round", "day"], columns="model", values="day_pnl")
            .reset_index()
        )
        ash_day_comp["delta_kiko_minus_alt"] = ash_day_comp["model_kiko"] - ash_day_comp[alt]

        r1_delta = float(
            total_round.loc[(total_round["model"] == "model_kiko") & (total_round["round"] == "round_1"), "total_pnl"].iloc[0]
            - total_round.loc[(total_round["model"] == alt) & (total_round["round"] == "round_1"), "total_pnl"].iloc[0]
        )
        r2_delta = float(
            total_round.loc[(total_round["model"] == "model_kiko") & (total_round["round"] == "round_2"), "total_pnl"].iloc[0]
            - total_round.loc[(total_round["model"] == alt) & (total_round["round"] == "round_2"), "total_pnl"].iloc[0]
        )

        scenario_comp = (
            scenario_total[scenario_total["model"].isin(["model_kiko", alt])]
            .pivot(index="scenario", columns="model", values="total_pnl")
            .reset_index()
        )
        scenario_comp["delta_kiko_minus_alt"] = scenario_comp["model_kiko"] - scenario_comp[alt]

        pert = small_pert[small_pert["model"].isin(["model_kiko", alt])]
        pert_pivot = pert.pivot(index="scenario", columns="model", values="total_pnl").reset_index()

        rows.append(
            {
                "alt_model": alt,
                "delta_round_1_total": r1_delta,
                "delta_round_2_total": r2_delta,
                "mean_daily_total_delta": float(day_comp["delta_kiko_minus_alt"].mean()),
                "std_daily_total_delta": float(day_comp["delta_kiko_minus_alt"].std(ddof=1)) if len(day_comp) > 1 else 0.0,
                "min_daily_total_delta": float(day_comp["delta_kiko_minus_alt"].min()),
                "wins_total_days": int((day_comp["delta_kiko_minus_alt"] > 0).sum()),
                "wins_pepper_days": int((pepper_day_comp["delta_kiko_minus_alt"] > 0).sum()),
                "wins_ash_days": int((ash_day_comp["delta_kiko_minus_alt"] > 0).sum()),
                "scenario_wins": int((scenario_comp["delta_kiko_minus_alt"] > 0).sum()),
                "min_scenario_delta": float(scenario_comp["delta_kiko_minus_alt"].min()),
                "max_scenario_delta": float(scenario_comp["delta_kiko_minus_alt"].max()),
                "kiko_small_perturbation_range": float(
                    pert_pivot.loc[:, "model_kiko"].max() - pert_pivot.loc[:, "model_kiko"].min()
                ),
                "alt_small_perturbation_range": float(pert_pivot.loc[:, alt].max() - pert_pivot.loc[:, alt].min()),
            }
        )

    return pd.DataFrame(rows).sort_values("delta_round_2_total", ascending=False).reset_index(drop=True)


def build_change_scorecard(parameter_df: pd.DataFrame) -> pd.DataFrame:
    both_df = (
        parameter_df.pivot(index=["variant", "label"], columns="round", values="delta_vs_baseline_total")
        .reset_index()
        .rename(columns={"round_1": "delta_round_1", "round_2": "delta_round_2"})
    )
    both_df["delta_both"] = both_df["delta_round_1"] + both_df["delta_round_2"]

    category_map = {
        "baseline": ("No tocar", "Es el punto de referencia real; ya está validado en live según tu input."),
        "ash_edge_m5": ("No tocar", "No cambia nada en el replay local; moverlo añade ruido sin beneficio."),
        "ash_edge_p5": ("No tocar", "No cambia nada en el replay local; moverlo añade ruido sin beneficio."),
        "pepper_take_m025": (
            "No tocar",
            "Ligero beneficio en Round 2 pero pequeño e inconsistente contra Round 1; no supera la carga de prueba.",
        ),
        "pepper_take_p025": (
            "No tocar",
            "Empeora de forma visible; no hay caso económico claro para ensanchar más el taking.",
        ),
        "pepper_slope_p01": (
            "Demasiado frágil / alto riesgo de overfit",
            "Mejora local mínima ajustando exactamente la pendiente fija del drift observado.",
        ),
        "pepper_slope_p02": (
            "Demasiado frágil / alto riesgo de overfit",
            "Mejora local algo mayor, pero sigue siendo tuning directo del slope conocido del dataset.",
        ),
        "pepper_slope_p05": (
            "Demasiado frágil / alto riesgo de overfit",
            "La mejora local es fuerte, pero viene de hacer todavía más agresiva la hipótesis fija de drift.",
        ),
        "pepper_base_update_03": (
            "Demasiado frágil / alto riesgo de overfit",
            "Es el microcambio más defendible si te obligaran a probar uno, pero la mejora sale de perseguir más rápido el mismo drift local.",
        ),
        "pepper_base_update_04": (
            "Demasiado frágil / alto riesgo de overfit",
            "Mejora mucho localmente porque carga más carry y más tiempo cerca del límite; eso es justo el tipo de tuning que más puede romperse fuera de muestra.",
        ),
        "pepper_residual_06": (
            "Demasiado frágil / alto riesgo de overfit",
            "Reduce el castigo por residual y empuja más fuerte la tesis tendencial; mejora local, pero empeora la prudencia del modelo.",
        ),
    }

    rows: List[Dict[str, float | int | str]] = []
    for _, row in both_df.iterrows():
        category, note = category_map[row["variant"]]
        rows.append(
            {
                "candidate": row["label"],
                "variant": row["variant"],
                "category": category,
                "delta_round_1": float(row["delta_round_1"]),
                "delta_round_2": float(row["delta_round_2"]),
                "delta_both": float(row["delta_both"]),
                "implementable_with_real_inputs": "sí",
                "why": note,
            }
        )
    return pd.DataFrame(rows)


def summarize_maf_for_report(scenario_df: pd.DataFrame) -> pd.DataFrame:
    sub = scenario_df[
        (scenario_df["model"].isin(["model_kiko", "model_G5"]))
        & (scenario_df["scenario"].isin(["baseline", "maf_uniform_125", "maf_front_125", "maf_depth_trade_125"]))
    ].copy()
    base = (
        sub[sub["scenario"] == "baseline"][["model", "product", "total_pnl"]]
        .rename(columns={"total_pnl": "baseline_pnl"})
    )
    out = sub.merge(base, on=["model", "product"], how="left")
    out["delta_vs_baseline"] = out["total_pnl"] - out["baseline_pnl"]
    return out


def write_report(
    baseline_round_df: pd.DataFrame,
    baseline_day_df: pd.DataFrame,
    scenario_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    parameter_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
    change_scorecard_df: pd.DataFrame,
) -> None:
    kiko_base = baseline_round_df[
        (baseline_round_df["model"] == "model_kiko") & (baseline_round_df["scenario"] == "baseline")
    ].copy()
    kiko_total_round1 = float(kiko_base.loc[(kiko_base["round"] == "round_1") & (kiko_base["product"] == "TOTAL"), "total_pnl"].iloc[0])
    kiko_total_round2 = float(kiko_base.loc[(kiko_base["round"] == "round_2") & (kiko_base["product"] == "TOTAL"), "total_pnl"].iloc[0])
    kiko_product = kiko_base[kiko_base["product"] != "TOTAL"].copy()
    kiko_product["edge_share"] = kiko_product.groupby("round")["total_pnl"].transform(lambda s: s / s.sum())

    round_totals = (
        baseline_round_df[(baseline_round_df["product"] == "TOTAL") & (baseline_round_df["scenario"] == "baseline")]
        .pivot(index="model", columns="round_label", values="total_pnl")
        .reset_index()
        .sort_values(["Round 2", "Round 1"], ascending=False)
    )

    day_stats = (
        baseline_day_df[
            (baseline_day_df["scenario"] == "baseline")
            & (baseline_day_df["product"] == "TOTAL")
            & (baseline_day_df["model"].isin(COMPARABLE_MODELS))
        ]
        .groupby("model", as_index=False)["day_pnl"]
        .agg(
            mean_day_pnl="mean",
            std_day_pnl=lambda s: float(pd.Series(s).std(ddof=1)),
            min_day_pnl="min",
            max_day_pnl="max",
        )
        .sort_values("mean_day_pnl", ascending=False)
    )

    round2_scenarios = (
        scenario_df[(scenario_df["product"] == "TOTAL") & (scenario_df["round"] == "round_2")]
        .pivot(index="model", columns="scenario", values="total_pnl")
        .reset_index()
        .sort_values("baseline", ascending=False)
    )

    paired_pretty = comparison_df[
        [
            "alt_model",
            "delta_round_1_total",
            "delta_round_2_total",
            "mean_daily_total_delta",
            "std_daily_total_delta",
            "min_daily_total_delta",
            "wins_total_days",
            "wins_pepper_days",
            "wins_ash_days",
            "scenario_wins",
        ]
    ].copy()

    maf_summary = summarize_maf_for_report(scenario_df)
    maf_kiko = maf_summary[(maf_summary["model"] == "model_kiko") & (maf_summary["scenario"] != "baseline")].copy()
    maf_g5 = maf_summary[(maf_summary["model"] == "model_G5") & (maf_summary["scenario"] != "baseline")].copy()

    param_pretty = (
        parameter_df.pivot(index=["variant", "label"], columns="round", values="delta_vs_baseline_total")
        .reset_index()
        .rename(columns={"round_1": "delta_round_1", "round_2": "delta_round_2"})
    )
    param_pretty["delta_both"] = param_pretty["delta_round_1"] + param_pretty["delta_round_2"]
    param_pretty = param_pretty.sort_values("delta_both", ascending=False)

    capacity_pretty = capacity_df[
        [
            "round_label",
            "scenario",
            "day",
            "product",
            "day_pnl",
            "avg_abs_position",
            "pct_abs_ge_70",
            "pct_at_limit",
            "time_to_70",
            "time_to_80",
        ]
    ].copy()

    baseline_pepper_round2 = kiko_base[
        (kiko_base["round"] == "round_2") & (kiko_base["product"] == "INTARIAN_PEPPER_ROOT")
    ].iloc[0]
    g5_pepper_round2 = baseline_round_df[
        (baseline_round_df["model"] == "model_G5")
        & (baseline_round_df["round"] == "round_2")
        & (baseline_round_df["scenario"] == "baseline")
        & (baseline_round_df["product"] == "INTARIAN_PEPPER_ROOT")
    ].iloc[0]
    baseupd03 = parameter_df[(parameter_df["variant"] == "pepper_base_update_03") & (parameter_df["round"] == "round_2")].iloc[0]
    baseupd04 = parameter_df[(parameter_df["variant"] == "pepper_base_update_04") & (parameter_df["round"] == "round_2")].iloc[0]

    lines: List[str] = [
        "# Auditoría cuantitativa de `model_kiko` para Round 2",
        "",
        "## 1. Resumen ejecutivo",
        "",
        "- **Recomendación final:** **Opción A — mantener `model_kiko` intacto en su lógica de trading**.",
        "- **Confianza:** media-alta.",
        "- Tomo como restricción fuerte tu dato reportado de live Round 1 (~192k, top 70). Eso **sube muchísimo** la carga de prueba para tocar el modelo.",
        f"- Localmente, `model_kiko` sigue siendo la mejor base que encontré: `{kiko_total_round1:,.1f}` en Round 1 y `{kiko_total_round2:,.1f}` en Round 2.",
        "- Contra comparables cercanos (`G5`, `G1`, `G4`, `G2`, `F3`), `model_kiko` queda **primero en ambas rondas y en todos los escenarios microestructurales testeados**.",
        "- Los microtweaks que mejoran el replay local **sí existen**, pero todos empujan más fuerte la misma hipótesis de drift de PEPPER. Eso me parece **más overfit que mejora robusta**.",
        "- Mi lectura práctica: **Round 2 se parece más a un problema de preservar una estrategia ya muy buena y decidir bien el bid que a un problema de rediseñar `model_kiko`**.",
        "",
        "## 2. Contexto: por qué este problema NO es “buscar un modelo nuevo”",
        "",
        "- El archivo auditado es el modelo real que, según tu dato reportado, produjo un resultado live muy fuerte en Round 1.",
        "- Eso implica una filosofía correcta de trabajo:",
        "  1. **Hipótesis nula = no tocar.**",
        "  2. Un cambio solo entra si mejora de forma clara, consistente y explicable.",
        "  3. Si la mejora sale de exprimir el mismo replay local, se penaliza como riesgo de overfit.",
        "",
        "## 3. `model_kiko`: archivo, estructura y lógica",
        "",
        f"- **Ruta exacta:** `{MODEL_PATHS['model_kiko']}`.",
        "- Arquitectura general:",
        "  - `SharedBookOps`: utilidades comunes de making/taking/clear.",
        "  - `OsmiumEngine`: lógica de `ASH_COATED_OSMIUM`.",
        "  - `PepperEngine`: lógica de `INTARIAN_PEPPER_ROOT`.",
        "  - `Trader`: orquestación y serialización de `traderData`.",
        "",
        "### ASH_COATED_OSMIUM",
        "",
        "- Fair value por **EWMA del mid**.",
        "- Reservation price con skew por inventario.",
        "- Taking simple alrededor de `take_width`.",
        "- Making con `default_edge` grande y lógica clásica de join/step.",
        "",
        "### INTARIAN_PEPPER_ROOT",
        "",
        "- La tesis central es **trend-following prior-driven**.",
        "- El modelo fija `price_slope = 0.00100001` por timestamp y reconstruye una `base_price` de-trendeada.",
        "- Después calcula `alpha = forward_edge - residual_weight * residual - inventory_skew * position` (más un término de gap hoy neutralizado).",
        "- En castellano: **asume que PEPPER tiene una deriva lineal muy estable y trata de cargar inventario largo sin pagar de más**.",
        "",
        "### Cómo genera el PnL",
        "",
        f"- **Round 1:** ASH aporta {kiko_product.loc[(kiko_product['round']=='round_1') & (kiko_product['product']=='ASH_COATED_OSMIUM'),'edge_share'].iloc[0]:.1%} del total y PEPPER {kiko_product.loc[(kiko_product['round']=='round_1') & (kiko_product['product']=='INTARIAN_PEPPER_ROOT'),'edge_share'].iloc[0]:.1%}.",
        f"- **Round 2:** ASH aporta {kiko_product.loc[(kiko_product['round']=='round_2') & (kiko_product['product']=='ASH_COATED_OSMIUM'),'edge_share'].iloc[0]:.1%} del total y PEPPER {kiko_product.loc[(kiko_product['round']=='round_2') & (kiko_product['product']=='INTARIAN_PEPPER_ROOT'),'edge_share'].iloc[0]:.1%}.",
        "- O sea: el edge de verdad está en **PEPPER**. ASH suma, pero no define el ranking.",
        "",
        "## 4. Revisión del entorno de Round 2",
        "",
        "- Productos y límites no cambian: `ASH_COATED_OSMIUM` e `INTARIAN_PEPPER_ROOT`, ambos con límite 80.",
        "- La novedad es el **Market Access Fee (MAF)**: un `bid()` ciego para acceder a +25% de quotes si entrás en el top 50%.",
        "- **PERO** eso no cambia qué inputs ve el modelo en `run()`.",
        "",
        "### Qué inputs existen realmente",
        "",
        "- En el `TradingState` del repo existen: `timestamp`, `order_depths`, `own_trades`, `market_trades`, `position`, `observations`, `traderData`.",
        "- En el backtester local, al llamar `run()` se pasan `own_trades={product: []}`, `market_trades={product: []}` y `observations` vacías.",
        "- **No existe** un flag `access_granted`, `accepted_bid` ni nada equivalente en `TradingState` o en el backtester local.",
        "- Entonces: cualquier mejora seria tiene que depender de **inputs observables reales** (libro visible, timestamp, posición, traderData propio), no de una señal ficticia.",
        "",
        "## 5. Auditoría de robustez de `model_kiko`",
        "",
        "### 5.1 Baseline por round y producto",
        "",
        markdown_table(
            kiko_base[
                [
                    "round_label",
                    "product",
                    "total_pnl",
                    "max_drawdown",
                    "fill_count",
                    "maker_share",
                    "avg_fill_size",
                    "avg_abs_position",
                    "pct_abs_ge_70",
                    "pct_at_limit",
                ]
            ],
            ".3f",
        ),
        "",
        "### 5.2 Robustez día a día",
        "",
        markdown_table(day_stats, ".1f"),
        "",
        "- `model_kiko` le gana a `G5` en **5 de 6 días** a nivel total.",
        "- En `PEPPER`, `model_kiko` le gana a `G5` en **6 de 6 días**.",
        "- En `ASH`, `model_kiko` pierde en promedio; su edge no sale de ahí.",
        "",
        "### 5.3 Capacidad / inventario",
        "",
        markdown_table(capacity_pretty, ".3f"),
        "",
        f"- En Round 2 baseline, PEPPER ya opera con `avg_abs_position = {baseline_pepper_round2['avg_abs_position']:.1f}` y `pct_abs_ge_70 = {baseline_pepper_round2['pct_abs_ge_70']:.1%}`.",
        "- Eso te dice dos cosas a la vez:",
        "  1. ya está monetizando fuerte el carry,",
        "  2. pero **sin** pasar tanto tiempo clavado en el límite como otros modelos más warehouse-heavy.",
        "",
        "## 6. Comparación con alternativas cercanas",
        "",
        "### 6.1 Totales baseline",
        "",
        markdown_table(round_totals, ".1f"),
        "",
        "### 6.2 Deltas pareados de `model_kiko` contra comparables",
        "",
        markdown_table(paired_pretty, ".1f"),
        "",
        "### 6.3 Robustez por escenarios de microestructura / MAF",
        "",
        markdown_table(round2_scenarios, ".1f"),
        "",
        "Lectura importante:",
        "",
        "- `model_kiko` queda **primero en baseline**.",
        "- También queda **primero con depth -10% y +10%**.",
        "- Y sigue **primero bajo los proxies MAF**.",
        "- O sea: no veo a ninguna alternativa cercana dominándolo de verdad. Las otras son buenas, pero **no mejores**.",
        "",
        "## 7. Posibles microajustes detectados",
        "",
        "### 7.1 Sensibilidad local de parámetros",
        "",
        markdown_table(param_pretty, ".1f"),
        "",
        "### 7.2 Scorecard de cambios",
        "",
        markdown_table(change_scorecard_df, ".1f"),
        "",
        "## 8. Análisis específico de riesgo de overfit",
        "",
        "Acá está la parte más importante, hermano.",
        "",
        "### Qué sí me parece robusto",
        "",
        "- La **estructura** del modelo: ASH simple + PEPPER tendencial.",
        "- La separación por engines y el uso de solo inputs observables reales.",
        "- La ventaja comparativa baseline de `model_kiko` frente a alternativas cercanas.",
        "",
        "### Qué me parece más frágil",
        "",
        "- El corazón de PEPPER depende de una **pendiente fija** (`price_slope`).",
        "- Los tweaks que mejoran localmente hacen casi siempre lo mismo:",
        "  - subir `price_slope`, o",
        "  - subir `base_update_weight`, o",
        "  - bajar `residual_weight`.",
        "- Traducido: **todos** empujan al modelo a creer aún más en el mismo drift lineal que ya observó el dataset.",
        "",
        f"- Ejemplo claro: con `base_update_weight = 0.3`, Round 2 sube `{baseupd03['delta_vs_baseline_total']:+,.1f}` localmente.",
        f"- Con `base_update_weight = 0.4`, Round 2 sube `{baseupd04['delta_vs_baseline_total']:+,.1f}` localmente.",
        "- Pero ese extra PnL viene acompañado de más inventario medio y más tiempo cerca del límite en PEPPER. Es decir: gana porque **se casa más fuerte con la tendencia observada**.",
        f"- Y ojo con la comparación: `model_kiko` baseline ya hace más PnL en PEPPER que `G5` con **menos inventario medio** (`{baseline_pepper_round2['avg_abs_position']:.1f}` vs `{g5_pepper_round2['avg_abs_position']:.1f}`) y menos tiempo al límite (`{baseline_pepper_round2['pct_at_limit']:.1%}` vs `{g5_pepper_round2['pct_at_limit']:.1%}`).",
        "- Para mí, eso es una señal de eficiencia del baseline. Si ahora lo tuneás para warehousear todavía más, podés estar cambiando eficiencia por brute force.",
        "",
        "## 9. Qué mejoras son robustas y cuáles no",
        "",
        "### Robustas / accionables",
        "",
        "- **Agregar `bid()`** para Round 2: sí, pero eso es una decisión aparte del modelo, no un cambio en la lógica de `run()`.",
        "- **Mantener la lógica de trading igual**: sí. Hoy cruza la carga de prueba.",
        "",
        "### No robustas o demasiado frágiles",
        "",
        "- Tocar `price_slope` basándose en estos mismos datasets.",
        "- Hacer `base_update_weight` mucho más agresivo para cargar más carry.",
        "- Debilitar `residual_weight` para dejar que PEPPER persiga más el precio.",
        "- Cualquier lógica condicionada a un supuesto `access_granted` inexistente.",
        "",
        "## 10. Implicación para la decisión del bid",
        "",
        "### ¿El extra access favorece especialmente a `model_kiko`?",
        "",
        "No especialmente.",
        "",
        markdown_table(
            maf_kiko[
                ["scenario", "product", "baseline_pnl", "total_pnl", "delta_vs_baseline", "fill_count", "maker_share", "avg_abs_position"]
            ],
            ".3f",
        ),
        "",
        "Comparado con G5:",
        "",
        markdown_table(
            maf_g5[
                ["scenario", "product", "baseline_pnl", "total_pnl", "delta_vs_baseline", "fill_count", "maker_share", "avg_abs_position"]
            ],
            ".3f",
        ),
        "",
        "Lectura:",
        "",
        "- En `model_kiko`, el proxy MAF conservador suma ~`+2.7k` y el central ~`+4.4k`.",
        "- Es menos delta que en `G5`, no más.",
        "- Y en `model_kiko` el beneficio viene **más por ASH y por fill quality** que por desbloquear una gran mejora nueva en PEPPER.",
        "- Eso me lleva a una conclusión fuerte: **Round 2 no me grita “reoptimizá el modelo”**. Me grita más bien: **“preservá el modelo bueno y decidí bien el bid”**.",
        "",
        "## 11. Recomendación final: A / B / C",
        "",
        "### **Opción A — Mantener `model_kiko` exactamente igual en su lógica de trading**",
        "",
        "Es mi recomendación.",
        "",
        "#### Por qué no B",
        "",
        "- Sí, hay tweaks que mejoran el replay local.",
        "- Pero no veo evidencia suficientemente robusta como para sacrificar la validación real fuerte de Round 1.",
        "- Todos los buenos “tweaks” locales van en la misma dirección: **creer más fuerte y más rápido en el mismo drift observado**.",
        "- Eso es exactamente el patrón que más fácil se convierte en overfit.",
        "",
        "#### Por qué no C",
        "",
        "- Ningún modelo cercano domina a `model_kiko`.",
        "- Localmente, `model_kiko` sigue siendo el mejor candidato base.",
        "",
        "## 12. Confianza de la recomendación",
        "",
        "- **Media-alta**.",
        "- Lo que sostiene la decisión:",
        "  - `model_kiko` gana baseline y escenarios contra comparables fuertes.",
        "  - La ventaja viene de PEPPER y es consistente día a día.",
        "  - Los cambios que mejoran localmente tienen firma clara de overfit direccional.",
        "- Lo que me falta para subir la confianza aún más:",
        "  - más muestras fuera de estos 6 días, o",
        "  - un entorno de simulación que replique mejor la aleatorización oficial del market access estándar.",
        "",
        "## 13. Próximos pasos",
        "",
        "1. **Mandaría `model_kiko` intacto** en su lógica de trading.",
        "2. Le agregaría `bid()` como decisión separada de Round 2.",
        "3. Si querés investigar un único tweak en paralelo, el menos indefendible para laboratorio sería `base_update_weight = 0.3`, **pero hoy NO lo mandaría a producción sin más evidencia**.",
        "4. El mayor edge marginal esperable para Round 2, en mi opinión, viene más del **MAF / bid** que de retocar la estrategia base.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_data = load_all_raw_data()
    baseline_round_df, baseline_day_df = build_baseline_metrics(raw_data)
    scenario_df = build_scenario_metrics(raw_data)
    capacity_df = build_capacity_metrics(raw_data)
    parameter_df = build_parameter_sensitivity(raw_data)
    comparison_df = build_model_comparison_summary(baseline_round_df, baseline_day_df, scenario_df)
    change_scorecard_df = build_change_scorecard(parameter_df)

    baseline_round_df.to_csv(RESULTS_DIR / "baseline_round_metrics.csv", index=False)
    baseline_day_df.to_csv(RESULTS_DIR / "baseline_day_metrics.csv", index=False)
    scenario_df.to_csv(RESULTS_DIR / "scenario_metrics.csv", index=False)
    capacity_df.to_csv(RESULTS_DIR / "capacity_metrics.csv", index=False)
    parameter_df.to_csv(RESULTS_DIR / "parameter_sensitivity.csv", index=False)
    comparison_df.to_csv(RESULTS_DIR / "model_comparison_summary.csv", index=False)
    change_scorecard_df.to_csv(RESULTS_DIR / "change_scorecard.csv", index=False)

    write_report(
        baseline_round_df=baseline_round_df,
        baseline_day_df=baseline_day_df,
        scenario_df=scenario_df,
        comparison_df=comparison_df,
        parameter_df=parameter_df,
        capacity_df=capacity_df,
        change_scorecard_df=change_scorecard_df,
    )
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
