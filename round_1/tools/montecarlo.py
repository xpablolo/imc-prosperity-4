#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from backtest import (  # noqa: E402
    DATA_DIR,
    DEFAULT_PRODUCT,
    DepthSnapshot,
    configure_style,
    load_day_prices_and_trades,
    load_trader,
    run_backtest_on_loaded_data,
)

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
RESULTS_BASE_DIR = ROUND_DIR / "results" / "montecarlo"
HISTORICAL_DAYS = [-2, -1, 0]
TIMESTEP = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Custom Monte Carlo for round_1 Ash Coated Osmium market making.")
    parser.add_argument("--model", type=str, default="ash_mm_v0")
    parser.add_argument("--product", type=str, default=DEFAULT_PRODUCT)
    parser.add_argument("--sessions", type=int, default=120)
    parser.add_argument("--block-length", type=int, default=75, help="Average bootstrap block length in ticks.")
    parser.add_argument("--sample-sessions", type=int, default=20, help="How many paths to retain for plotting.")
    parser.add_argument("--seed", type=int, default=20260414)
    parser.add_argument(
        "--reset-between-days",
        action="store_true",
        help="Reset cash/position/trader state between synthetic days, matching replay semantics.",
    )
    return parser.parse_args()


def build_historical_records(product: str, max_levels: int = 3) -> Dict[int, List[dict]]:
    records_by_day: Dict[int, List[dict]] = {}
    for day in HISTORICAL_DAYS:
        depth_by_ts, trades_df = load_day_prices_and_trades(day, product, max_levels=max_levels)
        grouped_trades = trades_df.groupby("timestamp", sort=False) if not trades_df.empty else None
        records: List[dict] = []
        for timestamp in sorted(depth_by_ts.keys()):
            if grouped_trades is not None and timestamp in grouped_trades.groups:
                sub = grouped_trades.get_group(timestamp)
                trades = [(int(row["price"]), int(row["quantity"])) for _, row in sub.iterrows() if int(row["quantity"]) > 0]
            else:
                trades = []
            depth = depth_by_ts[timestamp]
            records.append(
                {
                    "timestamp": int(timestamp),
                    "depth": DepthSnapshot(dict(depth.buy_vol_by_price), dict(depth.sell_vol_by_price), float(depth.mid_price)),
                    "trades": trades,
                }
            )
        records_by_day[day] = records
    return records_by_day


def sample_block_length(rng: np.random.Generator, mean_block_length: int) -> int:
    probability = 1.0 / max(mean_block_length, 1)
    return max(1, int(rng.geometric(probability)))


def shift_depth(depth: DepthSnapshot, price_shift: int) -> DepthSnapshot:
    if price_shift == 0:
        return DepthSnapshot(dict(depth.buy_vol_by_price), dict(depth.sell_vol_by_price), float(depth.mid_price))
    return DepthSnapshot(
        {int(price + price_shift): int(volume) for price, volume in depth.buy_vol_by_price.items()},
        {int(price + price_shift): int(volume) for price, volume in depth.sell_vol_by_price.items()},
        float(depth.mid_price + price_shift),
    )


def generate_synthetic_day(
    historical_records: Dict[int, List[dict]],
    rng: np.random.Generator,
    mean_block_length: int,
    target_length: int,
) -> Tuple[Dict[int, DepthSnapshot], pd.DataFrame]:
    all_days = list(historical_records.keys())
    chosen_records: List[dict] = []

    while len(chosen_records) < target_length:
        source_day = int(rng.choice(all_days))
        source_records = historical_records[source_day]
        if not source_records:
            continue
        block_length = sample_block_length(rng, mean_block_length)
        start = int(rng.integers(0, max(1, len(source_records) - block_length + 1)))
        stop = min(len(source_records), start + block_length)
        raw_block = source_records[start:stop]
        if not raw_block:
            continue

        if chosen_records:
            prior_mid = float(chosen_records[-1]["depth"].mid_price)
            block_start_mid = float(raw_block[0]["depth"].mid_price)
            price_shift = int(round(prior_mid - block_start_mid))
        else:
            price_shift = 0

        shifted_block: List[dict] = []
        for record in raw_block:
            shifted_depth = shift_depth(record["depth"], price_shift)
            shifted_trades = [(int(price + price_shift), int(quantity)) for price, quantity in record["trades"]]
            shifted_block.append(
                {
                    "timestamp": int(record["timestamp"]),
                    "depth": shifted_depth,
                    "trades": shifted_trades,
                }
            )
        chosen_records.extend(shifted_block)

    chosen_records = chosen_records[:target_length]
    depth_by_ts: Dict[int, DepthSnapshot] = {}
    trade_rows: List[dict] = []
    for index, record in enumerate(chosen_records):
        timestamp = index * TIMESTEP
        depth = record["depth"]
        depth_by_ts[timestamp] = DepthSnapshot(dict(depth.buy_vol_by_price), dict(depth.sell_vol_by_price), float(depth.mid_price))
        for price, quantity in record["trades"]:
            trade_rows.append({"timestamp": timestamp, "price": int(price), "quantity": int(quantity)})

    trades_df = pd.DataFrame(trade_rows, columns=["timestamp", "price", "quantity"])
    return depth_by_ts, trades_df


def summarize_distribution(values: List[float]) -> Dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "count": float(len(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(np.min(arr)),
        "p05": float(np.quantile(arr, 0.05)),
        "p25": float(np.quantile(arr, 0.25)),
        "p50": float(np.quantile(arr, 0.50)),
        "p75": float(np.quantile(arr, 0.75)),
        "p95": float(np.quantile(arr, 0.95)),
        "max": float(np.max(arr)),
        "positiveRate": float(np.mean(arr > 0)),
    }


def plot_distribution(session_df: pd.DataFrame, output_dir: Path, model_name: str, product: str) -> None:
    configure_style()
    fig, ax = plt.subplots(figsize=(11, 5.8))
    sns.histplot(session_df["total_pnl"], bins=min(50, max(15, len(session_df) // 4)), kde=True, ax=ax, color="#2563EB")
    stats = summarize_distribution(session_df["total_pnl"].tolist())
    for label, key, color in [("P05", "p05", "#DC2626"), ("Median", "p50", "#111827"), ("P95", "p95", "#10B981")]:
        value = stats[key]
        ax.axvline(value, color=color, linestyle="--", linewidth=1.5)
        ax.text(value, ax.get_ylim()[1] * 0.92, f" {label}\n {value:,.0f}", color=color, fontsize=9)
    ax.set_title(f"{model_name} — Monte Carlo PnL distribution")
    ax.set_xlabel(f"{product} total PnL across 3 synthetic days")
    ax.set_ylabel("sessions")
    fig.savefig(output_dir / "pnl_distribution.png", dpi=180)
    plt.close(fig)


def plot_path_bands(sample_paths: List[pd.DataFrame], output_dir: Path, model_name: str) -> None:
    configure_style()
    if not sample_paths:
        return
    base_ts = sample_paths[0]["global_ts"].to_numpy()
    matrix = np.vstack([path["pnl"].to_numpy() for path in sample_paths])
    p10 = np.quantile(matrix, 0.10, axis=0)
    p25 = np.quantile(matrix, 0.25, axis=0)
    p50 = np.quantile(matrix, 0.50, axis=0)
    p75 = np.quantile(matrix, 0.75, axis=0)
    p90 = np.quantile(matrix, 0.90, axis=0)

    fig, ax = plt.subplots(figsize=(13.5, 5.8))
    ax.fill_between(base_ts, p10, p90, color="#93C5FD", alpha=0.25, label="10–90% band")
    ax.fill_between(base_ts, p25, p75, color="#2563EB", alpha=0.30, label="25–75% band")
    ax.plot(base_ts, p50, color="#111827", linewidth=2.2, label="median path")
    for path in sample_paths[:8]:
        ax.plot(path["global_ts"], path["pnl"], color="#10B981", linewidth=0.8, alpha=0.18)
    ax.axhline(0, color="#9CA3AF", linewidth=1.0)
    ax.set_title(f"{model_name} — Monte Carlo PnL path bands")
    ax.set_xlabel("chronological time")
    ax.set_ylabel("PnL")
    ax.legend(loc="upper left")
    fig.savefig(output_dir / "pnl_path_bands.png", dpi=180)
    plt.close(fig)


def plot_scatter(session_df: pd.DataFrame, output_dir: Path, model_name: str) -> None:
    configure_style()
    fig, ax = plt.subplots(figsize=(9, 6.5))
    scatter = ax.scatter(
        session_df["max_drawdown"].abs(),
        session_df["total_pnl"],
        s=40 + 220 * session_df["maker_share"].fillna(0.0),
        c=session_df["sharpe_like"],
        cmap="viridis",
        alpha=0.8,
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_title(f"{model_name} — PnL vs drawdown across Monte Carlo sessions")
    ax.set_xlabel("absolute max drawdown")
    ax.set_ylabel("total PnL")
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("sharpe-like")
    fig.savefig(output_dir / "pnl_vs_drawdown.png", dpi=180)
    plt.close(fig)


def plot_metrics_table(session_df: pd.DataFrame, output_dir: Path, model_name: str, product: str) -> Dict[str, Dict[str, float]]:
    total_stats = summarize_distribution(session_df["total_pnl"].tolist())
    dd_stats = summarize_distribution(session_df["max_drawdown"].tolist())
    sharpe_stats = summarize_distribution(session_df["sharpe_like"].tolist())
    maker_stats = summarize_distribution(session_df["maker_share"].fillna(0.0).tolist())

    rows = [
        ["Metric", "Mean", "P05", "Median", "P95"],
        ["Total PnL", f"{total_stats['mean']:,.0f}", f"{total_stats['p05']:,.0f}", f"{total_stats['p50']:,.0f}", f"{total_stats['p95']:,.0f}"],
        ["Max drawdown", f"{dd_stats['mean']:,.0f}", f"{dd_stats['p05']:,.0f}", f"{dd_stats['p50']:,.0f}", f"{dd_stats['p95']:,.0f}"],
        ["Sharpe-like", f"{sharpe_stats['mean']:.2f}", f"{sharpe_stats['p05']:.2f}", f"{sharpe_stats['p50']:.2f}", f"{sharpe_stats['p95']:.2f}"],
        ["Maker share", f"{maker_stats['mean']:.2%}", f"{maker_stats['p05']:.2%}", f"{maker_stats['p50']:.2%}", f"{maker_stats['p95']:.2%}"],
        ["Win rate", f"{total_stats['positiveRate']:.2%}", "—", "—", "—"],
    ]

    configure_style()
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.axis("off")
    table = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1.0, 1.5)
    ax.set_title(f"{model_name} — {product} Monte Carlo summary", fontsize=16, pad=18)
    fig.savefig(output_dir / "metrics_table.png", dpi=180)
    plt.close(fig)

    return {
        "totalPnl": total_stats,
        "maxDrawdown": dd_stats,
        "sharpeLike": sharpe_stats,
        "makerShare": maker_stats,
    }


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    historical_records = build_historical_records(args.product)
    target_length = min(len(records) for records in historical_records.values())

    TraderClass = load_trader(args.model)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_BASE_DIR / args.model / timestamp
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    session_rows: List[dict] = []
    sample_paths: List[pd.DataFrame] = []

    for session_id in range(args.sessions):
        day_data: Dict[int, Tuple[Dict[int, DepthSnapshot], pd.DataFrame]] = {}
        for synthetic_day in HISTORICAL_DAYS:
            depth_by_ts, trades_df = generate_synthetic_day(historical_records, rng, args.block_length, target_length)
            day_data[synthetic_day] = (depth_by_ts, trades_df)

        trader = TraderClass()
        results_df, _fills_df, metrics = run_backtest_on_loaded_data(
            trader,
            args.product,
            HISTORICAL_DAYS,
            day_data,
            reset_between_days=args.reset_between_days,
        )
        session_rows.append(
            {
                "session_id": session_id,
                "total_pnl": metrics["total_pnl"],
                "max_drawdown": metrics["max_drawdown"],
                "sharpe_like": metrics["sharpe_like"],
                "maker_share": metrics.get("maker_share", np.nan),
                "fill_count": metrics.get("fill_count", np.nan),
                "max_abs_position": metrics.get("max_abs_position", np.nan),
            }
        )
        if len(sample_paths) < args.sample_sessions:
            sample_paths.append(results_df[["global_ts", "pnl"]].copy())

    session_df = pd.DataFrame(session_rows)
    session_df.to_csv(output_dir / "session_summary.csv", index=False)

    overview = plot_metrics_table(session_df, plots_dir, args.model, args.product)
    plot_distribution(session_df, plots_dir, args.model, args.product)
    plot_path_bands(sample_paths, plots_dir, args.model)
    plot_scatter(session_df, plots_dir, args.model)

    dashboard = {
        "meta": {
            "model": args.model,
            "product": args.product,
            "sessions": args.sessions,
            "blockLength": args.block_length,
            "seed": args.seed,
            "sourceDays": HISTORICAL_DAYS,
            "method": "stationary block bootstrap on synchronized book+trade records",
            "resetBetweenDays": args.reset_between_days,
        },
        "overall": overview,
    }
    (output_dir / "dashboard.json").write_text(json.dumps(dashboard, indent=2), encoding="utf-8")

    print(f"Monte Carlo complete: {args.model} on {args.product}")
    print(f"  sessions: {args.sessions}")
    print(f"  mean pnl: {overview['totalPnl']['mean']:,.1f}")
    print(f"  p05-p95: {overview['totalPnl']['p05']:,.1f} to {overview['totalPnl']['p95']:,.1f}")
    print(f"  win rate: {overview['totalPnl']['positiveRate']:.2%}")
    print(f"Saved to {output_dir}")


if __name__ == "__main__":
    main()
