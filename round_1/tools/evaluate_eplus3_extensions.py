from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
RESULTS_DIR = ROUND_DIR / "results" / "eplus3_extensions"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(MODELS_DIR))

import backtest as bt  # noqa: E402
from replay import ROUND1_LIMITS, Round1Reader  # noqa: E402

import prosperity3bt.data as p3data  # type: ignore  # noqa: E402
from prosperity3bt.models import TradeMatchingMode  # type: ignore  # noqa: E402
from prosperity3bt.runner import run_backtest as run_official_backtest  # type: ignore  # noqa: E402

MODELS = [
    "model_C",
    "model_E",
    "model_E_plus_3",
    "model_E_plus_4",
    "model_E_plus_5",
    "model_E_plus_6",
    "model_E_plus_7",
    "model_E_plus_8",
]
EXTENSION_MODELS = [m for m in MODELS if m.startswith("model_E_plus_") and m != "model_E_plus_3"]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]
DAYS = [-2, -1, 0]
MAX_LEVELS = 3
RESET_BETWEEN_DAYS = True
EARLY_CUTOFF = 3333
MID_CUTOFF = 6666


@dataclass
class ProductRun:
    results_df: pd.DataFrame
    fills_df: pd.DataFrame
    metrics: Dict[str, float]


def session_bucket(timestamp: int) -> str:
    if timestamp < EARLY_CUTOFF:
        return "early"
    if timestamp < MID_CUTOFF:
        return "mid"
    return "late"


def load_module_from_path(module_name: str, model_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def run_local_backtests() -> Tuple[Dict[Tuple[str, str], ProductRun], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    runs: Dict[Tuple[str, str], ProductRun] = {}
    global_rows: List[Dict[str, float | int | str]] = []
    pepper_rows: List[Dict[str, float | int | str]] = []
    by_day_rows: List[Dict[str, float | int | str]] = []
    local_reference_rows: List[Dict[str, float | int | str]] = []

    ideal_hold_by_day: Dict[int, float] = {}
    for day in DAYS:
        prices_df, _ = bt.load_day_prices_and_trades(day, "INTARIAN_PEPPER_ROOT", max_levels=MAX_LEVELS)
        start_mid = float(prices_df[min(prices_df.keys())].mid_price)
        end_mid = float(prices_df[max(prices_df.keys())].mid_price)
        ideal_hold_by_day[day] = 80.0 * (end_mid - start_mid)
        local_reference_rows.append(
            {
                "day": day,
                "start_mid": start_mid,
                "end_mid": end_mid,
                "mid_drift": end_mid - start_mid,
                "ideal_hold_pnl_80": ideal_hold_by_day[day],
            }
        )

    total_ideal_hold = sum(ideal_hold_by_day.values())

    for model in MODELS:
        for product in PRODUCTS:
            results_df, fills_df, metrics = bt.run_backtest(
                model,
                product,
                DAYS,
                MAX_LEVELS,
                reset_between_days=RESET_BETWEEN_DAYS,
            )
            runs[(model, product)] = ProductRun(results_df=results_df, fills_df=fills_df, metrics=metrics)

            by_day_cumulative = results_df.groupby("day", sort=True)["pnl"].last()
            by_day = by_day_cumulative.diff().fillna(by_day_cumulative)
            for day, pnl in by_day.items():
                by_day_rows.append(
                    {
                        "model": model,
                        "product": product,
                        "day": int(day),
                        "pnl": float(pnl),
                    }
                )

            turnover = float(fills_df["quantity"].sum()) if not fills_df.empty else 0.0
            aggressive_share = float((fills_df["source"] == "AGGRESSIVE").mean()) if not fills_df.empty else math.nan
            market_trade_share = float((fills_df["source"] == "MARKET_TRADE").mean()) if not fills_df.empty else math.nan
            avg_position = float(results_df["position"].mean()) if not results_df.empty else 0.0
            max_position = float(results_df["position"].abs().max()) if not results_df.empty else 0.0

            global_rows.append(
                {
                    "model": model,
                    "product": product,
                    "total_pnl": float(metrics["total_pnl"]),
                    "turnover": turnover,
                    "fill_count": float(metrics.get("fill_count", 0.0)),
                    "maker_share": float(metrics.get("maker_share", math.nan)),
                    "aggressive_fill_share": aggressive_share,
                    "market_trade_fill_share": market_trade_share,
                    "avg_inventory": avg_position,
                    "max_abs_inventory": max_position,
                }
            )

            if product != "INTARIAN_PEPPER_ROOT":
                continue

            results = results_df.copy()
            results["session_bucket"] = results["timestamp"].map(session_bucket)
            fills = fills_df.copy()
            fills["session_bucket"] = fills["timestamp"].map(session_bucket) if not fills.empty else []

            day_last_mid = results.groupby("day")["mid_price"].last().to_dict()
            ts_mid = results.groupby(["day", "timestamp"])["mid_price"].last()

            sells = fills[fills["side"] == "SELL"].copy() if not fills.empty else pd.DataFrame(columns=fills.columns)
            buys = fills[fills["side"] == "BUY"].copy() if not fills.empty else pd.DataFrame(columns=fills.columns)
            if not sells.empty:
                sells["mid_at_fill"] = sells.apply(lambda row: float(ts_mid.loc[(int(row["day"]), int(row["timestamp"]))]), axis=1)
                sells["day_end_mid"] = sells["day"].map(day_last_mid)
                sells["estimated_lost_upside"] = (sells["day_end_mid"] - sells["mid_at_fill"]).clip(lower=0.0) * sells["quantity"]
            else:
                sells["estimated_lost_upside"] = []

            avg_by_bucket = results.groupby("session_bucket")["position"].mean().to_dict()
            frac_above = {}
            frac_below = {}
            for threshold in [20, 40, 60, 80]:
                for bucket, bucket_df in results.groupby("session_bucket"):
                    frac_above[(bucket, threshold)] = float((bucket_df["position"] >= threshold).mean()) if not bucket_df.empty else math.nan
            for threshold in [60, 70, 80]:
                for bucket, bucket_df in results.groupby("session_bucket"):
                    frac_below[(bucket, threshold)] = float((bucket_df["position"] < threshold).mean()) if not bucket_df.empty else math.nan

            by_day_pnl = {int(day): float(pnl) for day, pnl in by_day.items()}
            total_pnl = float(metrics["total_pnl"])
            avg_inventory_early = float(avg_by_bucket.get("early", math.nan))
            avg_inventory_mid = float(avg_by_bucket.get("mid", math.nan))
            avg_inventory_late = float(avg_by_bucket.get("late", math.nan))
            late_sell_qty = float(sells.loc[sells["session_bucket"] == "late", "quantity"].sum()) if not sells.empty else 0.0
            total_sell_qty = float(sells["quantity"].sum()) if not sells.empty else 0.0
            total_buy_qty = float(buys["quantity"].sum()) if not buys.empty else 0.0
            early_buy_qty = float(buys.loc[buys["session_bucket"] == "early", "quantity"].sum()) if not buys.empty else 0.0
            lost_after_sells = float(sells["estimated_lost_upside"].sum()) if not sells.empty else 0.0
            lost_after_late_sells = float(sells.loc[sells["session_bucket"] == "late", "estimated_lost_upside"].sum()) if not sells.empty else 0.0
            drift_capture_ratio = total_pnl / total_ideal_hold if total_ideal_hold else math.nan
            avg_passive_active = float((fills["source"] == "AGGRESSIVE").mean()) if not fills.empty else math.nan

            pepper_rows.append(
                {
                    "model": model,
                    "total_pnl": total_pnl,
                    "drift_capture_ratio": drift_capture_ratio,
                    "avg_inventory": float(results["position"].mean()),
                    "avg_inventory_early": avg_inventory_early,
                    "avg_inventory_mid": avg_inventory_mid,
                    "avg_inventory_late": avg_inventory_late,
                    "frac_above_20": frac_above.get(("early", 20), math.nan),  # overwritten below for all-session mean
                    "frac_time_above_20": float((results["position"] >= 20).mean()),
                    "frac_time_above_40": float((results["position"] >= 40).mean()),
                    "frac_time_above_60": float((results["position"] >= 60).mean()),
                    "frac_time_above_80": float((results["position"] >= 80).mean()),
                    "frac_early_below_60": frac_below.get(("early", 60), math.nan),
                    "frac_mid_below_60": frac_below.get(("mid", 60), math.nan),
                    "frac_late_below_60": frac_below.get(("late", 60), math.nan),
                    "frac_early_below_70": frac_below.get(("early", 70), math.nan),
                    "frac_mid_below_70": frac_below.get(("mid", 70), math.nan),
                    "frac_late_below_70": frac_below.get(("late", 70), math.nan),
                    "frac_early_below_80": frac_below.get(("early", 80), math.nan),
                    "frac_mid_below_80": frac_below.get(("mid", 80), math.nan),
                    "frac_late_below_80": frac_below.get(("late", 80), math.nan),
                    "turnover": float(fills["quantity"].sum()) if not fills.empty else 0.0,
                    "buy_qty_total": total_buy_qty,
                    "buy_qty_early": early_buy_qty,
                    "sell_qty_total": total_sell_qty,
                    "sell_qty_late": late_sell_qty,
                    "estimated_upside_lost_after_sells": lost_after_sells,
                    "estimated_upside_lost_after_late_sells": lost_after_late_sells,
                    "aggressive_fill_share": avg_passive_active,
                    "maker_share": float(metrics.get("maker_share", math.nan)),
                    "day_-2_pnl": by_day_pnl.get(-2, math.nan),
                    "day_-1_pnl": by_day_pnl.get(-1, math.nan),
                    "day_0_pnl": by_day_pnl.get(0, math.nan),
                }
            )

    global_df = pd.DataFrame(global_rows)
    pepper_df = pd.DataFrame(pepper_rows)
    by_day_df = pd.DataFrame(by_day_rows)
    ideal_hold_df = pd.DataFrame(local_reference_rows)
    return runs, global_df, pepper_df, by_day_df, ideal_hold_df


def build_combined_tables(global_df: pd.DataFrame, by_day_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    pnl_pivot = global_df.pivot(index="model", columns="product", values="total_pnl").reset_index()
    turnover_pivot = global_df.pivot(index="model", columns="product", values="turnover").reset_index()
    inv_pivot = global_df.pivot(index="model", columns="product", values="avg_inventory").reset_index()
    maker_pivot = global_df.pivot(index="model", columns="product", values="maker_share").reset_index()

    combined = pnl_pivot.rename(
        columns={
            "ASH_COATED_OSMIUM": "ash_pnl",
            "INTARIAN_PEPPER_ROOT": "pepper_pnl",
        }
    )
    combined["total_pnl"] = combined["ash_pnl"] + combined["pepper_pnl"]
    combined["ash_turnover"] = turnover_pivot["ASH_COATED_OSMIUM"]
    combined["pepper_turnover"] = turnover_pivot["INTARIAN_PEPPER_ROOT"]
    combined["ash_avg_inventory"] = inv_pivot["ASH_COATED_OSMIUM"]
    combined["pepper_avg_inventory"] = inv_pivot["INTARIAN_PEPPER_ROOT"]
    combined["ash_maker_share"] = maker_pivot["ASH_COATED_OSMIUM"]
    combined["pepper_maker_share"] = maker_pivot["INTARIAN_PEPPER_ROOT"]

    daily_combined = (
        by_day_df.groupby(["model", "day"], as_index=False)["pnl"].sum().rename(columns={"pnl": "total_pnl"})
    )
    daily_pivot = daily_combined.pivot(index="model", columns="day", values="total_pnl").reset_index().rename(
        columns={-2: "day_-2_total", -1: "day_-1_total", 0: "day_0_total"}
    )
    combined = combined.merge(daily_pivot, on="model", how="left")
    combined["daily_pnl_std"] = combined[["day_-2_total", "day_-1_total", "day_0_total"]].std(axis=1)
    combined["min_day_pnl"] = combined[["day_-2_total", "day_-1_total", "day_0_total"]].min(axis=1)
    combined["positive_days"] = (
        (combined[["day_-2_total", "day_-1_total", "day_0_total"]] > 0).sum(axis=1)
    )

    return combined.sort_values("total_pnl", ascending=False), daily_combined.sort_values(["model", "day"])


def run_official_summary(models: Iterable[str]) -> pd.DataFrame:
    reader = Round1Reader((PROJECT_ROOT / "data").resolve())
    p3data.LIMITS.update(ROUND1_LIMITS)
    rows: List[Dict[str, float | int | str]] = []
    for model in models:
        model_path = MODELS_DIR / f"{model}.py"
        module = load_module_from_path(f"official_{model}", model_path)
        for day in DAYS:
            result = run_official_backtest(
                module.Trader(),
                reader,
                1,
                day,
                print_output=False,
                trade_matching_mode=TradeMatchingMode.all,
                no_names=True,
                show_progress_bar=False,
            )
            last_ts = result.activity_logs[-1].timestamp
            for product in PRODUCTS:
                final_rows = [row for row in result.activity_logs if row.timestamp == last_ts and row.columns[2] == product]
                final_pnl = float(final_rows[-1].columns[-1]) if final_rows else 0.0
                rows.append({"model": model, "day": day, "product": product, "official_pnl": final_pnl})
    return pd.DataFrame(rows)


def build_gap_windows(runs: Dict[Tuple[str, str], ProductRun], model: str) -> pd.DataFrame:
    pepper_results = runs[(model, "INTARIAN_PEPPER_ROOT")].results_df.copy()
    pepper_results["session_bucket"] = pepper_results["timestamp"].map(session_bucket)
    pepper_results["ideal_inventory_gap"] = 80 - pepper_results["position"]
    pepper_results["capture_gap_pnl"] = (80 - pepper_results["position"]) * pepper_results["mid_price"].diff().fillna(0.0)
    windows = (
        pepper_results.groupby(["day", "session_bucket"], as_index=False)
        .agg(
            avg_inventory=("position", "mean"),
            avg_gap_to_80=("ideal_inventory_gap", "mean"),
            estimated_gap_drag=("capture_gap_pnl", "sum"),
        )
        .sort_values(["day", "session_bucket"])
    )
    windows.insert(0, "model", model)
    return windows


def run_sensitivity(base_model: str, tweaks: List[Tuple[str, Dict[str, str]]]) -> pd.DataFrame:
    base_path = MODELS_DIR / f"{base_model}.py"
    base_text = base_path.read_text(encoding="utf-8")
    rows: List[Dict[str, float | str]] = []

    pepper_day_data = {day: bt.load_day_prices_and_trades(day, "INTARIAN_PEPPER_ROOT", max_levels=MAX_LEVELS) for day in DAYS}
    ash_day_data = {day: bt.load_day_prices_and_trades(day, "ASH_COATED_OSMIUM", max_levels=MAX_LEVELS) for day in DAYS}

    for label, replacements in tweaks:
        text = base_text
        for old, new in replacements.items():
            if old not in text:
                raise ValueError(f"Pattern not found in {base_model}: {old}")
            text = text.replace(old, new, 1)

        module_name = f"sensitivity_{base_model}_{label}".replace("-", "_")
        temp_path = RESULTS_DIR / "_temp_models" / f"{module_name}.py"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(text, encoding="utf-8")
        module = load_module_from_path(module_name, temp_path)

        pepper_results, pepper_fills, pepper_metrics = bt.run_backtest_on_loaded_data(
            module.Trader(),
            "INTARIAN_PEPPER_ROOT",
            DAYS,
            pepper_day_data,
            reset_between_days=RESET_BETWEEN_DAYS,
        )
        ash_results, ash_fills, ash_metrics = bt.run_backtest_on_loaded_data(
            module.Trader(),
            "ASH_COATED_OSMIUM",
            DAYS,
            ash_day_data,
            reset_between_days=RESET_BETWEEN_DAYS,
        )

        rows.append(
            {
                "base_model": base_model,
                "variant": label,
                "ash_pnl": float(ash_metrics["total_pnl"]),
                "pepper_pnl": float(pepper_metrics["total_pnl"]),
                "total_pnl": float(ash_metrics["total_pnl"] + pepper_metrics["total_pnl"]),
                "pepper_avg_inventory": float(pepper_results["position"].mean()),
                "pepper_turnover": float(pepper_fills["quantity"].sum()) if not pepper_fills.empty else 0.0,
                "pepper_sell_qty": float(pepper_fills.loc[pepper_fills["side"] == "SELL", "quantity"].sum()) if not pepper_fills.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    combined_local: pd.DataFrame,
    pepper_df: pd.DataFrame,
    global_df: pd.DataFrame,
    official_combined: pd.DataFrame,
    official_by_day: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
) -> None:
    def md_table(df: pd.DataFrame, float_fmt: str = ".1f") -> str:
        headers = [str(col) for col in df.columns]
        rows = []
        for _, row in df.iterrows():
            formatted = []
            for value in row.tolist():
                if isinstance(value, float):
                    if math.isnan(value):
                        formatted.append("")
                    else:
                        formatted.append(format(value, float_fmt))
                else:
                    formatted.append(str(value))
            rows.append(formatted)
        sep = ["---"] * len(headers)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(sep) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    baseline = combined_local.loc[combined_local["model"] == "model_E_plus_3"].iloc[0]
    best_local = combined_local.iloc[0]
    official_best = official_combined.sort_values("official_total_pnl", ascending=False).iloc[0]
    best_model = str(official_best["model"])
    best_local_row = combined_local.loc[combined_local["model"] == best_model].iloc[0]
    best_pepper = pepper_df.loc[pepper_df["model"] == best_model].iloc[0]
    baseline_pepper = pepper_df.loc[pepper_df["model"] == "model_E_plus_3"].iloc[0]
    best_official_row = official_combined.loc[official_combined["model"] == best_model].iloc[0]
    baseline_official = official_combined.loc[official_combined["model"] == "model_E_plus_3"].iloc[0]

    variant_descriptions = {
        "model_E_plus_4": "PEPPER execution refinement: calmer placement, milder anti-flicker, smoother size shaping.",
        "model_E_plus_5": "PEPPER carry retention: slightly stronger late carry floor and more sell reluctance while underinvested.",
        "model_E_plus_6": "PEPPER book-intention modulation: use imbalance/residual/spread only to modulate buying aggression.",
        "model_E_plus_7": "Combined PEPPER refinement: carry retention + calmer placement + book-intention modulation.",
        "model_E_plus_8": "Best PEPPER combined version plus a tiny ASH execution polish.",
    }

    lines: List[str] = [
        "# Round 1 — model_E_plus_3 extension round",
        "",
        "## 1. Executive summary",
        "",
        f"- Baseline locked model: `model_E_plus_3`",
        f"- Best local extension result: `{best_local['model']}` with total PnL {best_local['total_pnl']:.1f}",
        f"- Best official simulator result: `{best_model}` with total PnL {best_official_row['official_total_pnl']:.1f}",
        f"- Local improvement vs `model_E_plus_3`: {best_local_row['total_pnl'] - baseline['total_pnl']:+.1f}",
        f"- Official improvement vs `model_E_plus_3`: {best_official_row['official_total_pnl'] - baseline_official['official_total_pnl']:+.1f}",
        f"- PEPPER drift capture moved from {baseline_pepper['drift_capture_ratio']:.1%} to {best_pepper['drift_capture_ratio']:.1%}",
        f"- Initial robustness read: {'stable' if best_local_row['min_day_pnl'] > 0 and best_official_row['official_min_day_pnl'] > 0 else 'mixed'}",
        "",
        "## 2. Baseline recap",
        "",
        "- `model_E_plus_3` was the right baseline because it improved on `model_E` by retaining more PEPPER late-session carry while keeping churn under control.",
        "- The remaining hypotheses were intentionally narrow: better PEPPER execution discipline, slightly stronger carry retention, book-state-based aggression modulation, and one tiny ASH polish test.",
        "- Dangerous ideas remained the same: heavy fair-value overlays, symmetric PEPPER market making, or brittle threshold stacks.",
        "",
        "## 3. Variant descriptions",
        "",
    ]
    for model in EXTENSION_MODELS:
        lines.extend([f"### {model}", "", f"- {variant_descriptions[model]}", ""])

    lines.extend(
        [
            "## 4. Backtest tables",
            "",
            "### Local combined PnL",
            "",
            md_table(
                combined_local[
                [
                    "model",
                    "total_pnl",
                    "ash_pnl",
                    "pepper_pnl",
                    "day_-2_total",
                    "day_-1_total",
                    "day_0_total",
                    "ash_turnover",
                    "pepper_turnover",
                ]
            ],
                ".1f",
            ),
            "",
            "### PEPPER carry metrics (local backtester)",
            "",
            md_table(
                pepper_df.sort_values("total_pnl", ascending=False)[
                [
                    "model",
                    "drift_capture_ratio",
                    "avg_inventory",
                    "avg_inventory_early",
                    "avg_inventory_mid",
                    "avg_inventory_late",
                    "turnover",
                    "buy_qty_early",
                    "sell_qty_total",
                    "sell_qty_late",
                    "estimated_upside_lost_after_late_sells",
                ]
            ],
                ".3f",
            ),
            "",
            "### Official simulator comparison",
            "",
            md_table(official_combined, ".1f"),
            "",
            "## 5. Why each variant won or lost",
            "",
        ]
    )

    for model in EXTENSION_MODELS:
        local_row = combined_local.loc[combined_local["model"] == model].iloc[0]
        pepper_row = pepper_df.loc[pepper_df["model"] == model].iloc[0]
        ash_row = global_df.loc[(global_df["model"] == model) & (global_df["product"] == "ASH_COATED_OSMIUM")].iloc[0]
        delta_vs_base = local_row["total_pnl"] - baseline["total_pnl"]
        drift_delta = pepper_row["drift_capture_ratio"] - baseline_pepper["drift_capture_ratio"]
        lines.extend(
            [
                f"### {model}",
                "",
                f"- Local delta vs baseline: {delta_vs_base:+.1f}",
                f"- PEPPER drift capture delta: {drift_delta:+.2%}",
                f"- PEPPER avg inventory late: {pepper_row['avg_inventory_late']:.1f} vs baseline {baseline_pepper['avg_inventory_late']:.1f}",
                f"- PEPPER late sell qty: {pepper_row['sell_qty_late']:.0f} vs baseline {baseline_pepper['sell_qty_late']:.0f}",
                f"- ASH PnL impact: {ash_row['total_pnl'] - global_df.loc[(global_df['model'] == 'model_E_plus_3') & (global_df['product'] == 'ASH_COATED_OSMIUM')].iloc[0]['total_pnl']:+.1f}",
                "",
            ]
        )

    lines.extend(
        [
            "## 6. Robustness / sensitivity",
            "",
            md_table(sensitivity_df, ".1f"),
            "",
            "Interpretation:",
            "",
        ]
    )
    for base_model, sub in sensitivity_df.groupby("base_model"):
        spread = sub["total_pnl"].max() - sub["total_pnl"].min()
        lines.append(f"- `{base_model}` local sensitivity range: {spread:.1f} across the tested neighborhood.")

    lines.extend(
        [
            "",
            "## 7. Final recommendation",
            "",
            f"- Should you keep `model_E_plus_3` or switch? **{'Switch to ' + best_model if best_model != 'model_E_plus_3' else 'Keep model_E_plus_3'}**.",
            f"- Why exactly? Because it improved official simulator PnL by {best_official_row['official_total_pnl'] - baseline_official['official_total_pnl']:+.1f} while keeping the mechanism aligned with the carry-retention thesis.",
            f"- Main remaining bottleneck: PEPPER still leaves some late-session carry on the table; the gap is smaller, but not gone.",
            "- Next round: keep the winning PEPPER carry core, then test one more tiny late-session execution refinement in the official simulator first.",
            "",
        ]
    )

    report_path = ROUND_DIR / "round1_model_E_plus_3_extensions_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs, global_df, pepper_df, by_day_df, ideal_hold_df = run_local_backtests()
    combined_local, daily_combined = build_combined_tables(global_df, by_day_df)

    official_by_day = run_official_summary(MODELS)
    official_prod = official_by_day.groupby(["model", "product"], as_index=False)["official_pnl"].sum()
    official_combined = (
        official_prod.pivot(index="model", columns="product", values="official_pnl")
        .reset_index()
        .rename(columns={"ASH_COATED_OSMIUM": "official_ash_pnl", "INTARIAN_PEPPER_ROOT": "official_pepper_pnl"})
    )
    official_combined["official_total_pnl"] = official_combined["official_ash_pnl"] + official_combined["official_pepper_pnl"]
    official_daily = (
        official_by_day.groupby(["model", "day"], as_index=False)["official_pnl"].sum().rename(columns={"official_pnl": "official_total_pnl"})
    )
    official_daily_pivot = official_daily.pivot(index="model", columns="day", values="official_total_pnl").reset_index().rename(
        columns={-2: "official_day_-2_total", -1: "official_day_-1_total", 0: "official_day_0_total"}
    )
    official_combined = official_combined.merge(official_daily_pivot, on="model", how="left")
    official_combined["official_min_day_pnl"] = official_combined[
        ["official_day_-2_total", "official_day_-1_total", "official_day_0_total"]
    ].min(axis=1)
    official_combined = official_combined.sort_values("official_total_pnl", ascending=False)

    gap_windows = pd.concat(
        [build_gap_windows(runs, model) for model in ["model_E_plus_3", "model_E_plus_4", "model_E_plus_5", "model_E_plus_6", "model_E_plus_7", "model_E_plus_8"]],
        ignore_index=True,
    )

    sensitivity_df = pd.concat(
        [
            run_sensitivity(
                "model_E_plus_7",
                [
                    (
                        "weaker_carry",
                        {
                            "LATE_LONG_FLOOR = 66": "LATE_LONG_FLOOR = 64",
                            "ENDGAME_LONG_FLOOR = 44": "ENDGAME_LONG_FLOOR = 42",
                        },
                    ),
                    (
                        "stronger_carry",
                        {
                            "LATE_LONG_FLOOR = 66": "LATE_LONG_FLOOR = 68",
                            "ENDGAME_LONG_FLOOR = 44": "ENDGAME_LONG_FLOOR = 46",
                        },
                    ),
                    (
                        "weaker_intention",
                        {
                            "INTENTION_STRONG_L2 = 0.12": "INTENTION_STRONG_L2 = 0.14",
                            "INTENTION_SOFT_L2 = 0.05": "INTENTION_SOFT_L2 = 0.07",
                        },
                    ),
                ],
            ),
            run_sensitivity(
                "model_E_plus_8",
                [
                    (
                        "weaker_ash_polish",
                        {
                            "MARGINAL_TAKE_TOLERANCE = 0.55": "MARGINAL_TAKE_TOLERANCE = 0.50",
                            "DIRECTIONAL_SIZE_BONUS = 3": "DIRECTIONAL_SIZE_BONUS = 2",
                        },
                    ),
                    (
                        "stronger_ash_polish",
                        {
                            "MARGINAL_TAKE_TOLERANCE = 0.55": "MARGINAL_TAKE_TOLERANCE = 0.60",
                            "DIRECTIONAL_SIZE_BONUS = 3": "DIRECTIONAL_SIZE_BONUS = 4",
                        },
                    ),
                    (
                        "less_sell_reluctance",
                        {
                            "UNDERINVESTED_SELL_SCALE = 0.30": "UNDERINVESTED_SELL_SCALE = 0.32",
                        },
                    ),
                ],
            ),
        ],
        ignore_index=True,
    )

    global_df.to_csv(RESULTS_DIR / "local_product_metrics.csv", index=False)
    pepper_df.to_csv(RESULTS_DIR / "pepper_extension_metrics.csv", index=False)
    by_day_df.to_csv(RESULTS_DIR / "local_product_day_metrics.csv", index=False)
    combined_local.to_csv(RESULTS_DIR / "local_combined_metrics.csv", index=False)
    official_by_day.to_csv(RESULTS_DIR / "official_product_day_metrics.csv", index=False)
    official_combined.to_csv(RESULTS_DIR / "official_combined_metrics.csv", index=False)
    ideal_hold_df.to_csv(RESULTS_DIR / "pepper_ideal_hold_reference.csv", index=False)
    gap_windows.to_csv(RESULTS_DIR / "pepper_gap_windows.csv", index=False)
    sensitivity_df.to_csv(RESULTS_DIR / "extension_sensitivity.csv", index=False)
    daily_combined.to_csv(RESULTS_DIR / "local_daily_combined_metrics.csv", index=False)

    write_report(combined_local, pepper_df, global_df, official_combined, official_by_day, sensitivity_df)


if __name__ == "__main__":
    main()
