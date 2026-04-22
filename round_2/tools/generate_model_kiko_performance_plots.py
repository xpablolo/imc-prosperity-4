from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "round_2" / "results" / "model_kiko"
PLOTS_DIR = RESULTS_DIR / "plots"
REPORT_PATH = RESULTS_DIR / "model_kiko_performance_plot_pack.md"

sys.path.insert(0, str(ROOT / "round_2" / "tools"))
sys.path.insert(0, str(ROOT / "round_2" / "models"))
sys.path.insert(0, str(ROOT / "round_1" / "tools"))
sys.path.insert(0, str(ROOT / "round_1" / "models"))

import analyze_g5_maf as ag  # noqa: E402
import backtest as bt  # noqa: E402


MODEL_NAME = "model_kiko"
MODEL_PATH = ROOT / "round_2" / "models" / "model_kiko.py"
ROUND_SPECS = {
    "round_1": {"days": [-2, -1, 0], "label": "Round 1"},
    "round_2": {"days": [-1, 0, 1], "label": "Round 2"},
}
ROUND_COLORS = {"round_1": "#2563EB", "round_2": "#F97316"}
BUY_COLOR = "#10B981"
SELL_COLOR = "#EF4444"
SOURCE_LABELS = {"MARKET_TRADE": "passive / market trade", "AGGRESSIVE": "aggressive take"}
SOURCE_COLORS = {"passive / market trade": "#0F766E", "aggressive take": "#B91C1C"}
PLOT_SUFFIXES = [
    "pnl_curve_by_round",
    "drawdown_curve_by_round",
    "inventory_curve_by_round",
    "mid_and_fills_by_round",
    "daily_pnl_flow_dashboard",
    "execution_edge_dashboard",
    "inventory_utilization_dashboard",
    "pnl_increment_distribution",
]


@dataclass
class RunArtifacts:
    round_name: str
    round_label: str
    product: str
    days: List[int]
    results_df: pd.DataFrame
    fills_df: pd.DataFrame
    metrics: Dict[str, float]


def pretty_product(product: str) -> str:
    return product.replace("_", " ").title()


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
        return "_no data_"
    headers = list(df.columns)
    rows: List[str] = []
    for _, row in df.iterrows():
        rendered: List[str] = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                if math.isnan(value):
                    rendered.append("")
                else:
                    rendered.append(format(value, float_fmt))
            else:
                rendered.append(str(value))
        rows.append("| " + " | ".join(rendered) + " |")
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *rows,
        ]
    )


def load_trader_class():
    spec = importlib.util.spec_from_file_location(MODEL_NAME, MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {MODEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.Trader


def load_cache() -> Dict[str, Dict[str, Dict[int, Tuple[dict, pd.DataFrame]]]]:
    cache: Dict[str, Dict[str, Dict[int, Tuple[dict, pd.DataFrame]]]] = {}
    for round_name, spec in ROUND_SPECS.items():
        cache[round_name] = {}
        for product in ag.PRODUCTS:
            cache[round_name][product] = {}
            for day in spec["days"]:
                loaded = ag.load_day_data(round_name, day, product)
                cache[round_name][product][day] = (loaded.depth_by_ts, loaded.trades_df)
    return cache


def enrich_results(results_df: pd.DataFrame, round_name: str, round_label: str, product: str, days: List[int]) -> pd.DataFrame:
    df = results_df.copy().sort_values(["day", "timestamp"]).reset_index(drop=True)
    session_map = {day: index + 1 for index, day in enumerate(days)}
    df["round"] = round_name
    df["round_label"] = round_label
    df["product"] = product
    df["session_index"] = df["day"].map(session_map)
    df["session_label"] = df["day"].map(lambda day: f"session {session_map[day]} · day {day}")
    df["abs_position"] = df["position"].abs()
    df["drawdown"] = bt.compute_drawdown(df["pnl"])
    df["pnl_increment"] = df.groupby("day")["pnl"].diff().fillna(0.0)
    return df


def enrich_fills(fills_df: pd.DataFrame, results_df: pd.DataFrame, round_name: str, round_label: str, product: str) -> pd.DataFrame:
    columns = [
        "day",
        "timestamp",
        "global_ts",
        "product",
        "side",
        "price",
        "quantity",
        "source",
        "round",
        "round_label",
        "mid_at_fill",
        "future_mid_10",
        "signed_edge_to_mid",
        "signed_markout_10",
        "notional",
        "source_label",
    ]
    if fills_df.empty:
        return pd.DataFrame(columns=columns)

    fills = fills_df.copy().sort_values(["day", "timestamp", "global_ts"]).reset_index(drop=True)
    fills["round"] = round_name
    fills["round_label"] = round_label
    fills["product"] = product
    fills["source_label"] = fills["source"].map(SOURCE_LABELS).fillna(fills["source"])
    fills["notional"] = fills["price"] * fills["quantity"]

    result_map = results_df[["day", "timestamp", "mid_price"]].drop_duplicates().copy()
    result_map["future_mid_10"] = result_map.groupby("day")["mid_price"].shift(-10)
    result_map = result_map.set_index(["day", "timestamp"])

    fills["mid_at_fill"] = [result_map["mid_price"].get((day, ts), np.nan) for day, ts in zip(fills["day"], fills["timestamp"], strict=True)]
    fills["future_mid_10"] = [result_map["future_mid_10"].get((day, ts), np.nan) for day, ts in zip(fills["day"], fills["timestamp"], strict=True)]
    fills["signed_edge_to_mid"] = np.where(
        fills["side"] == "BUY",
        fills["mid_at_fill"] - fills["price"],
        fills["price"] - fills["mid_at_fill"],
    )
    fills["signed_markout_10"] = np.where(
        fills["side"] == "BUY",
        fills["future_mid_10"] - fills["price"],
        fills["price"] - fills["future_mid_10"],
    )
    return fills[columns]


def compute_round_summary(run: RunArtifacts) -> dict:
    fills_df = run.fills_df
    results_df = run.results_df
    return {
        "round": run.round_name,
        "round_label": run.round_label,
        "product": run.product,
        "total_pnl": float(run.metrics["total_pnl"]),
        "max_drawdown": float(run.metrics["max_drawdown"]),
        "fill_count": int(run.metrics["fill_count"]),
        "maker_share": float(run.metrics["maker_share"]),
        "aggressive_fill_share": float(run.metrics["aggressive_fill_share"]),
        "avg_fill_size": float(run.metrics["avg_fill_size"]),
        "turnover": float(fills_df["notional"].sum()) if not fills_df.empty else 0.0,
        "avg_abs_position": float(results_df["abs_position"].mean()),
        "max_abs_position": float(results_df["abs_position"].max()),
        "pct_at_limit": float((results_df["abs_position"] >= ag.POSITION_LIMITS[run.product]).mean()),
        "avg_signed_edge_to_mid": float(fills_df["signed_edge_to_mid"].mean()) if not fills_df.empty else np.nan,
        "avg_signed_markout_10": float(fills_df["signed_markout_10"].mean()) if not fills_df.empty else np.nan,
    }


def compute_daily_summary(run: RunArtifacts) -> List[dict]:
    results_df = run.results_df
    fills_df = run.fills_df
    limit = ag.POSITION_LIMITS[run.product]
    cumulative = results_df.groupby("day", sort=True)["pnl"].last()
    daily_pnl = cumulative.diff().fillna(cumulative)
    rows: List[dict] = []

    for session_index, day in enumerate(run.days, start=1):
        day_results = results_df[results_df["day"] == day].copy()
        day_fills = fills_df[fills_df["day"] == day].copy()
        rows.append(
            {
                "round": run.round_name,
                "round_label": run.round_label,
                "product": run.product,
                "day": day,
                "session_index": session_index,
                "session_label": f"session {session_index}",
                "day_label": f"day {day}",
                "day_pnl": float(daily_pnl.loc[day]),
                "max_drawdown": float(day_results["drawdown"].min()),
                "fill_count": int(len(day_fills)),
                "maker_share": float((day_fills["source"] == "MARKET_TRADE").mean()) if not day_fills.empty else np.nan,
                "aggressive_fill_share": float((day_fills["source"] == "AGGRESSIVE").mean()) if not day_fills.empty else np.nan,
                "avg_fill_size": float(day_fills["quantity"].mean()) if not day_fills.empty else np.nan,
                "turnover": float(day_fills["notional"].sum()) if not day_fills.empty else 0.0,
                "avg_abs_position": float(day_results["abs_position"].mean()),
                "max_abs_position": float(day_results["abs_position"].max()),
                "pct_abs_ge_20": float((day_results["abs_position"] >= 20).mean()),
                "pct_abs_ge_40": float((day_results["abs_position"] >= 40).mean()),
                "pct_abs_ge_60": float((day_results["abs_position"] >= 60).mean()),
                "pct_abs_ge_70": float((day_results["abs_position"] >= 70).mean()),
                "pct_abs_ge_80": float((day_results["abs_position"] >= 80).mean()),
                "pct_at_limit": float((day_results["abs_position"] >= limit).mean()),
                "avg_signed_edge_to_mid": float(day_fills["signed_edge_to_mid"].mean()) if not day_fills.empty else np.nan,
                "avg_signed_markout_10": float(day_fills["signed_markout_10"].mean()) if not day_fills.empty else np.nan,
            }
        )
    return rows


def build_runs(cache) -> Tuple[Dict[Tuple[str, str], RunArtifacts], pd.DataFrame, pd.DataFrame]:
    Trader = load_trader_class()
    runs: Dict[Tuple[str, str], RunArtifacts] = {}
    round_rows: List[dict] = []
    daily_rows: List[dict] = []

    for round_name, spec in ROUND_SPECS.items():
        days = list(spec["days"])
        for product in ag.PRODUCTS:
            trader = Trader()
            results_df, fills_df, metrics = bt.run_backtest_on_loaded_data(
                trader,
                product,
                days,
                cache[round_name][product],
                reset_between_days=False,
            )
            results_df = enrich_results(results_df, round_name, spec["label"], product, days)
            fills_df = enrich_fills(fills_df, results_df, round_name, spec["label"], product)
            run = RunArtifacts(
                round_name=round_name,
                round_label=spec["label"],
                product=product,
                days=days,
                results_df=results_df,
                fills_df=fills_df,
                metrics=metrics,
            )
            runs[(round_name, product)] = run
            round_rows.append(compute_round_summary(run))
            daily_rows.extend(compute_daily_summary(run))

    round_summary_df = pd.DataFrame(round_rows)
    daily_summary_df = pd.DataFrame(daily_rows)
    return runs, round_summary_df, daily_summary_df


def infer_day_step(run: RunArtifacts) -> int:
    return int(run.results_df["timestamp"].max()) + 100


def add_session_background(ax: plt.Axes, run: RunArtifacts) -> None:
    step = infer_day_step(run)
    for index, day in enumerate(run.days):
        start = index * step
        end = start + step
        if index % 2 == 0:
            ax.axvspan(start, end, color="#F8FAFC", alpha=0.65)
        if index < len(run.days) - 1:
            ax.axvline(end, color="#D1D5DB", linewidth=1.0, alpha=0.9)
    ax.set_xticks([step * index + step / 2 for index in range(len(run.days))])
    ax.set_xticklabels([f"session {index + 1}\n(day {day})" for index, day in enumerate(run.days)])


def add_shared_session_background(ax: plt.Axes, n_sessions: int, step: int) -> None:
    for index in range(n_sessions):
        start = index * step
        end = start + step
        if index % 2 == 0:
            ax.axvspan(start, end, color="#F8FAFC", alpha=0.65)
        if index < n_sessions - 1:
            ax.axvline(end, color="#D1D5DB", linewidth=1.0, alpha=0.9)
    ax.set_xticks([step * index + step / 2 for index in range(n_sessions)])
    ax.set_xticklabels([f"session {index + 1}" for index in range(n_sessions)])


def save_figure(fig: plt.Figure, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    print(f"Saved: {output_path}")


def plot_pnl_curve_by_round(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    fig, ax = plt.subplots(figsize=(15.4, 5.8))
    shared_run = runs[("round_1", product)]
    add_shared_session_background(ax, n_sessions=3, step=infer_day_step(shared_run))

    for round_name in ROUND_SPECS:
        run = runs[(round_name, product)]
        color = ROUND_COLORS[round_name]
        ax.plot(run.results_df["global_ts"], run.results_df["pnl"], color=color, linewidth=2.5, label=run.round_label)
        ax.scatter(run.results_df["global_ts"].iloc[-1], run.results_df["pnl"].iloc[-1], color=color, s=48, zorder=4)
        ax.text(
            run.results_df["global_ts"].iloc[-1],
            run.results_df["pnl"].iloc[-1],
            f" {run.metrics['total_pnl']:.0f}",
            color=color,
            fontsize=10.5,
            va="center",
        )

    ax.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax.set_title(f"{product_name} — cumulative PnL by round", loc="left", pad=14)
    ax.text(
        0.01,
        0.98,
        "Same model, same product, two different round datasets. This is the cleanest first read of consistency.",
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax.set_xlabel("session chronology")
    ax.set_ylabel("PnL")
    ax.legend(loc="upper left")

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_pnl_curve_by_round.png"
    save_figure(fig, output_path)


def plot_drawdown_curve_by_round(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    fig, ax = plt.subplots(figsize=(15.4, 5.8))
    shared_run = runs[("round_1", product)]
    add_shared_session_background(ax, n_sessions=3, step=infer_day_step(shared_run))

    for round_name in ROUND_SPECS:
        run = runs[(round_name, product)]
        color = ROUND_COLORS[round_name]
        ax.plot(run.results_df["global_ts"], run.results_df["drawdown"], color=color, linewidth=2.4, label=run.round_label)
        ax.text(
            0.99,
            0.93 if round_name == "round_1" else 0.83,
            f"{run.round_label} max DD {run.metrics['max_drawdown']:.0f}",
            transform=ax.transAxes,
            ha="right",
            fontsize=10.5,
            color=color,
        )

    ax.axhline(0, color="#111827", linewidth=1.0)
    ax.set_title(f"{product_name} — drawdown profile by round", loc="left", pad=14)
    ax.text(
        0.01,
        0.98,
        "If one line lives much lower, the model is making money with more pain in that round.",
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax.set_xlabel("session chronology")
    ax.set_ylabel("drawdown")
    ax.legend(loc="lower left")

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_drawdown_curve_by_round.png"
    save_figure(fig, output_path)


def plot_inventory_curve_by_round(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    limit = ag.POSITION_LIMITS[product]
    fig, ax = plt.subplots(figsize=(15.4, 5.8))
    shared_run = runs[("round_1", product)]
    add_shared_session_background(ax, n_sessions=3, step=infer_day_step(shared_run))
    ax.axhspan(-limit, limit, color="#F8FAFC", alpha=0.35)
    ax.axhline(limit, color="#D1D5DB", linewidth=1.0, linestyle="--")
    ax.axhline(-limit, color="#D1D5DB", linewidth=1.0, linestyle="--")
    ax.axhline(0, color="#111827", linewidth=1.0)

    for round_name in ROUND_SPECS:
        run = runs[(round_name, product)]
        color = ROUND_COLORS[round_name]
        ax.plot(run.results_df["global_ts"], run.results_df["position"], color=color, linewidth=2.2, label=run.round_label)

    ax.set_title(f"{product_name} — inventory path by round", loc="left", pad=14)
    ax.text(
        0.01,
        0.98,
        f"Dashed lines mark the ±{limit} position limit. Useful to see whether performance comes with calmer or hotter inventory usage.",
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.88},
    )
    ax.set_xlabel("session chronology")
    ax.set_ylabel("position")
    ax.legend(loc="upper left")

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_inventory_curve_by_round.png"
    save_figure(fig, output_path)


def plot_mid_and_fills_by_round(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    fig, axes = plt.subplots(1, 2, figsize=(18.2, 6.0), sharey=True)

    for ax, round_name in zip(axes, ROUND_SPECS, strict=True):
        run = runs[(round_name, product)]
        results_df = run.results_df
        fills_df = run.fills_df
        add_session_background(ax, run)

        ax.plot(results_df["global_ts"], results_df["mid_price"], color="#111827", linewidth=1.4, alpha=0.95)
        if not fills_df.empty:
            for source, marker in {"MARKET_TRADE": "o", "AGGRESSIVE": "^"}.items():
                source_fills = fills_df[fills_df["source"] == source]
                if source_fills.empty:
                    continue
                for side, color in {"BUY": BUY_COLOR, "SELL": SELL_COLOR}.items():
                    side_fills = source_fills[source_fills["side"] == side]
                    if side_fills.empty:
                        continue
                    ax.scatter(
                        side_fills["global_ts"],
                        side_fills["price"],
                        s=side_fills["quantity"].clip(lower=1) * 7,
                        color=color,
                        marker=marker,
                        alpha=0.30 if source == "MARKET_TRADE" else 0.42,
                        linewidths=0,
                        zorder=3,
                    )

        maker_share = run.metrics.get("maker_share", np.nan)
        ax.set_title(f"{run.round_label}", pad=14)
        ax.text(
            0.01,
            0.98,
            f"fills {int(run.metrics['fill_count'])} · maker {maker_share:.1%}" if pd.notna(maker_share) else f"fills {int(run.metrics['fill_count'])}",
            transform=ax.transAxes,
            va="top",
            fontsize=10.2,
            color="#4B5563",
            bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "none", "alpha": 0.90},
        )
        ax.set_xlabel("chronology")

    axes[0].set_ylabel("price")
    fig.suptitle(f"{product_name} — mid price and fill map", x=0.01, y=0.995, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.958,
        "Black line = market mid. Green/red markers = buys and sells. Circles are passive fills, triangles are aggressive takes.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.82, wspace=0.12)

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_mid_and_fills_by_round.png"
    save_figure(fig, output_path)


def plot_daily_pnl_flow_dashboard(product: str, daily_summary_df: pd.DataFrame) -> None:
    product_name = pretty_product(product)
    product_daily = daily_summary_df[daily_summary_df["product"] == product].copy()
    product_daily["turnover_k"] = product_daily["turnover"] / 1_000

    fig, axes = plt.subplots(2, 2, figsize=(16.8, 10.4))
    ax_pnl, ax_fills, ax_maker, ax_turnover = axes.flatten()

    sns.barplot(
        data=product_daily,
        x="session_label",
        y="day_pnl",
        hue="round_label",
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        ax=ax_pnl,
    )
    ax_pnl.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_pnl.set_title("Daily PnL by session")
    ax_pnl.set_xlabel("")
    ax_pnl.set_ylabel("day PnL")

    sns.barplot(
        data=product_daily,
        x="session_label",
        y="fill_count",
        hue="round_label",
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        ax=ax_fills,
    )
    ax_fills.set_title("Fill count by session")
    ax_fills.set_xlabel("")
    ax_fills.set_ylabel("fills")

    sns.lineplot(
        data=product_daily,
        x="session_index",
        y="maker_share",
        hue="round_label",
        style="round_label",
        markers=True,
        dashes=False,
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        linewidth=2.4,
        ax=ax_maker,
    )
    ax_maker.set_xticks([1, 2, 3])
    ax_maker.set_xticklabels(["session 1", "session 2", "session 3"])
    ax_maker.set_ylim(0, 1)
    ax_maker.set_title("Maker share by session")
    ax_maker.set_xlabel("")
    ax_maker.set_ylabel("maker share")

    sns.barplot(
        data=product_daily,
        x="session_label",
        y="turnover_k",
        hue="round_label",
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        ax=ax_turnover,
    )
    ax_turnover.set_title("Turnover by session")
    ax_turnover.set_xlabel("")
    ax_turnover.set_ylabel("turnover (price·qty / 1k)")

    handles, labels = ax_pnl.get_legend_handles_labels()
    for ax in axes.flatten():
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()
    fig.legend(handles, labels, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 0.92))

    fig.suptitle(f"{product_name} — daily PnL and trading flow", x=0.01, y=0.995, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.958,
        "This dashboard separates consistency, activity, and execution style. Same model, but not necessarily same behavior across rounds.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.83, hspace=0.32, wspace=0.18)

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_daily_pnl_flow_dashboard.png"
    save_figure(fig, output_path)


def sampled_fills_for_scatter(product_fills: pd.DataFrame, max_points: int = 1800) -> pd.DataFrame:
    if len(product_fills) <= max_points:
        return product_fills
    return product_fills.sample(n=max_points, random_state=42)


def plot_execution_edge_dashboard(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    fills_df = pd.concat([runs[(round_name, product)].fills_df for round_name in ROUND_SPECS], ignore_index=True)
    if fills_df.empty:
        return

    scatter_df = sampled_fills_for_scatter(fills_df.dropna(subset=["signed_edge_to_mid", "signed_markout_10"]))
    fig, axes = plt.subplots(2, 2, figsize=(16.8, 10.0))
    ax_edge, ax_markout, ax_hist, ax_scatter = axes.flatten()

    sns.boxenplot(
        data=fills_df.dropna(subset=["signed_edge_to_mid"]),
        x="round_label",
        y="signed_edge_to_mid",
        hue="source_label",
        palette=SOURCE_COLORS,
        ax=ax_edge,
    )
    ax_edge.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_edge.set_title("Signed edge vs contemporaneous mid")
    ax_edge.set_xlabel("")
    ax_edge.set_ylabel("edge (positive = better)")

    sns.boxenplot(
        data=fills_df.dropna(subset=["signed_markout_10"]),
        x="round_label",
        y="signed_markout_10",
        hue="source_label",
        palette=SOURCE_COLORS,
        ax=ax_markout,
    )
    ax_markout.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_markout.set_title("Signed 10-tick markout")
    ax_markout.set_xlabel("")
    ax_markout.set_ylabel("markout (positive = better)")

    sns.histplot(
        data=fills_df.dropna(subset=["signed_markout_10"]),
        x="signed_markout_10",
        hue="round_label",
        kde=True,
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        stat="density",
        common_norm=False,
        ax=ax_hist,
    )
    ax_hist.axvline(0, color="#9CA3AF", linewidth=1.0)
    ax_hist.set_title("Markout distribution by round")
    ax_hist.set_xlabel("signed 10-tick markout")
    ax_hist.set_ylabel("density")

    if not scatter_df.empty:
        sns.scatterplot(
            data=scatter_df,
            x="signed_edge_to_mid",
            y="signed_markout_10",
            hue="round_label",
            style="source_label",
            palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
            alpha=0.35,
            s=52,
            ax=ax_scatter,
        )
    ax_scatter.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax_scatter.axvline(0, color="#9CA3AF", linewidth=1.0)
    ax_scatter.set_title("Edge vs markout")
    ax_scatter.set_xlabel("signed edge vs mid")
    ax_scatter.set_ylabel("signed 10-tick markout")

    handles, labels = ax_edge.get_legend_handles_labels()
    for ax in axes.flatten():
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()
    fig.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 0.92))

    fig.suptitle(f"{product_name} — execution edge dashboard", x=0.01, y=0.995, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.958,
        "Positive values are good. This lets you separate raw fill frequency from actual execution quality.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.83, hspace=0.34, wspace=0.18)

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_execution_edge_dashboard.png"
    save_figure(fig, output_path)


def plot_inventory_utilization_dashboard(product: str, runs: Dict[Tuple[str, str], RunArtifacts], daily_summary_df: pd.DataFrame) -> None:
    product_name = pretty_product(product)
    limit = ag.POSITION_LIMITS[product]
    combined_results = pd.concat([runs[(round_name, product)].results_df for round_name in ROUND_SPECS], ignore_index=True)
    combined_daily = daily_summary_df[daily_summary_df["product"] == product].copy()

    fig, axes = plt.subplots(1, 2, figsize=(16.8, 5.9))
    ax_dist, ax_threshold = axes

    sns.boxenplot(
        data=combined_results,
        x="round_label",
        y="abs_position",
        hue="round_label",
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        dodge=False,
        legend=False,
        ax=ax_dist,
    )
    ax_dist.axhline(limit, color="#D1D5DB", linewidth=1.0, linestyle="--")
    ax_dist.axhline(70, color="#E5E7EB", linewidth=1.0, linestyle=":")
    ax_dist.set_title("Absolute inventory distribution")
    ax_dist.set_xlabel("")
    ax_dist.set_ylabel("|position|")

    threshold_rows: List[dict] = []
    for threshold in (20, 40, 60, 70, 80):
        col = f"pct_abs_ge_{threshold}"
        for round_label, sub in combined_daily.groupby("round_label"):
            threshold_rows.append(
                {
                    "round_label": round_label,
                    "threshold": threshold,
                    "share": float(sub[col].mean()),
                }
            )
    threshold_df = pd.DataFrame(threshold_rows)
    sns.lineplot(
        data=threshold_df,
        x="threshold",
        y="share",
        hue="round_label",
        style="round_label",
        markers=True,
        dashes=False,
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        linewidth=2.6,
        ax=ax_threshold,
    )
    ax_threshold.set_title("How often inventory lives in hot zones")
    ax_threshold.set_xlabel("absolute position threshold")
    ax_threshold.set_ylabel("share of time above threshold")
    ax_threshold.set_ylim(0, 1)
    ax_threshold.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0%}"))

    fig.suptitle(f"{product_name} — inventory utilization dashboard", x=0.01, y=0.98, ha="left", fontsize=20, fontweight="bold")
    ax_threshold.text(
        0.02,
        0.98,
        f"Dashed reference marks the hard limit at {limit}. The line chart shows whether the strategy spends more time in crowded inventory states in one round than the other.",
        transform=ax_threshold.transAxes,
        va="top",
        ha="left",
        fontsize=10.3,
        color="#4B5563",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#E5E7EB"},
    )
    fig.subplots_adjust(top=0.84, wspace=0.16)

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_inventory_utilization_dashboard.png"
    save_figure(fig, output_path)


def build_increment_stats(results_df: pd.DataFrame) -> dict:
    increments = results_df["pnl_increment"].dropna()
    tail_cut = increments.quantile(0.05) if not increments.empty else np.nan
    tail = increments[increments <= tail_cut] if not increments.empty else pd.Series(dtype=float)
    return {
        "mean": float(increments.mean()) if not increments.empty else np.nan,
        "std": float(increments.std()) if len(increments) > 1 else np.nan,
        "p05": float(tail_cut) if not increments.empty else np.nan,
        "cvar05": float(tail.mean()) if not tail.empty else np.nan,
        "win_rate": float((increments > 0).mean()) if not increments.empty else np.nan,
        "max_abs": float(increments.abs().max()) if not increments.empty else np.nan,
    }


def plot_pnl_increment_distribution(product: str, runs: Dict[Tuple[str, str], RunArtifacts]) -> None:
    product_name = pretty_product(product)
    combined = pd.concat([runs[(round_name, product)].results_df for round_name in ROUND_SPECS], ignore_index=True)

    fig, (ax_hist, ax_table) = plt.subplots(1, 2, figsize=(16.8, 5.9), gridspec_kw={"width_ratios": [1.35, 1]})
    sns.histplot(
        data=combined,
        x="pnl_increment",
        hue="round_label",
        palette={spec["label"]: ROUND_COLORS[name] for name, spec in ROUND_SPECS.items()},
        kde=True,
        stat="density",
        common_norm=False,
        ax=ax_hist,
    )
    ax_hist.axvline(0, color="#9CA3AF", linewidth=1.0)
    ax_hist.set_title("Incremental PnL distribution")
    ax_hist.set_xlabel("pnl increment per timestamp")
    ax_hist.set_ylabel("density")

    stat_rows: List[List[str]] = []
    for round_name, spec in ROUND_SPECS.items():
        stats = build_increment_stats(runs[(round_name, product)].results_df)
        stat_rows.append(
            [
                spec["label"],
                f"{stats['mean']:.2f}",
                f"{stats['std']:.2f}",
                f"{stats['p05']:.2f}",
                f"{stats['cvar05']:.2f}",
                f"{stats['win_rate']:.1%}",
                f"{stats['max_abs']:.1f}",
            ]
        )

    ax_table.axis("off")
    table = ax_table.table(
        cellText=stat_rows,
        colLabels=["round", "mean", "std", "p05", "cvar05", "win rate", "max |inc|"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.15, 2.0)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#E5E7EB")
        if row == 0:
            cell.set_facecolor("#EFF6FF")
            cell.set_text_props(weight="bold", color="#111827")
        else:
            cell.set_facecolor("#FFFFFF")

    ax_table.text(
        0.5,
        0.88,
        "Per-round increment stats",
        transform=ax_table.transAxes,
        ha="center",
        fontsize=13,
        color="#111827",
        weight="bold",
    )

    fig.suptitle(f"{product_name} — PnL increment distribution", x=0.01, y=0.995, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.958,
        "This is the small-timestep risk profile: not final PnL, but what the path feels like tick by tick.",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.82, wspace=0.18)

    output_path = PLOTS_DIR / f"{product}_{MODEL_NAME}_pnl_increment_distribution.png"
    save_figure(fig, output_path)


def save_report(round_summary_df: pd.DataFrame, daily_summary_df: pd.DataFrame) -> None:
    product_sections: List[str] = []
    for product in ag.PRODUCTS:
        product_files = [f"`plots/{product}_{MODEL_NAME}_{suffix}.png`" for suffix in PLOT_SUFFIXES]
        product_round = round_summary_df[round_summary_df["product"] == product].copy()
        product_daily = daily_summary_df[daily_summary_df["product"] == product].copy()
        product_sections.extend(
            [
                f"## {pretty_product(product)}",
                "",
                "### Round summary",
                "",
                markdown_table(
                    product_round[
                        [
                            "round_label",
                            "total_pnl",
                            "max_drawdown",
                            "fill_count",
                            "maker_share",
                            "avg_fill_size",
                            "avg_abs_position",
                            "avg_signed_markout_10",
                        ]
                    ],
                    ".2f",
                ),
                "",
                "### Daily summary",
                "",
                markdown_table(
                    product_daily[
                        [
                            "round_label",
                            "day_label",
                            "day_pnl",
                            "fill_count",
                            "maker_share",
                            "avg_abs_position",
                            "pct_at_limit",
                        ]
                    ],
                    ".2f",
                ),
                "",
                "### Plot files",
                "",
                *[f"- {path}" for path in product_files],
                "",
            ]
        )

    lines = [
        "# model_kiko performance plot pack",
        "",
        "- Verified model file used for these charts: "
        f"`{MODEL_PATH}`",
        "- Important verification note: the repo contains **`model_kiko`**, not `model_kike`.",
        "- These plots evaluate the same `round_2/models/model_kiko.py` strategy on both datasets:",
        "  - Round 1 days `-2, -1, 0`",
        "  - Round 2 days `-1, 0, 1`",
        "",
        "## Overall round summary",
        "",
        markdown_table(round_summary_df, ".2f"),
        "",
        *product_sections,
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {REPORT_PATH}")


def main() -> None:
    configure_style()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    cache = load_cache()
    runs, round_summary_df, daily_summary_df = build_runs(cache)

    round_summary_df.to_csv(RESULTS_DIR / "model_kiko_round_summary.csv", index=False)
    daily_summary_df.to_csv(RESULTS_DIR / "model_kiko_daily_summary.csv", index=False)
    print(f"Saved: {RESULTS_DIR / 'model_kiko_round_summary.csv'}")
    print(f"Saved: {RESULTS_DIR / 'model_kiko_daily_summary.csv'}")

    for product in ag.PRODUCTS:
        plot_pnl_curve_by_round(product, runs)
        plot_drawdown_curve_by_round(product, runs)
        plot_inventory_curve_by_round(product, runs)
        plot_mid_and_fills_by_round(product, runs)
        plot_daily_pnl_flow_dashboard(product, daily_summary_df)
        plot_execution_edge_dashboard(product, runs)
        plot_inventory_utilization_dashboard(product, runs, daily_summary_df)
        plot_pnl_increment_distribution(product, runs)

    save_report(round_summary_df, daily_summary_df)


if __name__ == "__main__":
    main()
