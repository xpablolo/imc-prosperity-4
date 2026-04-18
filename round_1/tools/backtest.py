from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
DATA_DIR = PROJECT_ROOT / "data" / "round_1"
RESULTS_BASE_DIR = ROUND_DIR / "results"

sys.path.insert(0, str(MODELS_DIR))

from datamodel import Observation, Order, OrderDepth, TradingState  # noqa: E402

DEFAULT_PRODUCT = "ASH_COATED_OSMIUM"
DEFAULT_DAYS = [-2, -1, 0]


@dataclass
class DepthSnapshot:
    buy_vol_by_price: Dict[int, int]
    sell_vol_by_price: Dict[int, int]
    mid_price: float

    def best_bid(self) -> Optional[int]:
        return max(self.buy_vol_by_price.keys()) if self.buy_vol_by_price else None

    def best_ask(self) -> Optional[int]:
        return min(self.sell_vol_by_price.keys()) if self.sell_vol_by_price else None

    def clone_mutable(self) -> "DepthSnapshot":
        return DepthSnapshot(dict(self.buy_vol_by_price), dict(self.sell_vol_by_price), self.mid_price)


@dataclass
class Fill:
    day: int
    timestamp: int
    global_ts: int
    product: str
    side: str
    price: int
    quantity: int
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Custom backtest for round_1 single-product strategies.")
    parser.add_argument("--model", type=str, default="ash_mm_v0", help="Model filename under round_1/models.")
    parser.add_argument("--product", type=str, default=DEFAULT_PRODUCT, help="Product to backtest.")
    parser.add_argument("--days", type=int, nargs="*", default=DEFAULT_DAYS, help="Days to backtest.")
    parser.add_argument("--max-lob-levels", type=int, default=3, help="How many LOB levels to read from CSV snapshots.")
    parser.add_argument(
        "--reset-between-days",
        action="store_true",
        help="Reset cash/position/trader state at each day boundary and sum daily PnL, matching replay semantics.",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Optional suffix appended to output filenames (useful when validating multiple products with one model).",
    )
    parser.add_argument("--output-dir", type=str, default=str(RESULTS_BASE_DIR), help="Base results directory.")
    return parser.parse_args()


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
        }
    )


def load_trader(model_name: str):
    model_path = MODELS_DIR / f"{model_name}.py"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    spec = importlib.util.spec_from_file_location(f"round1_{model_name}", model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load model module: {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    if not hasattr(module, "Trader"):
        raise AttributeError(f"Model must define class Trader: {model_path}")
    return module.Trader


def build_depth_snapshot_from_prices_row(row: pd.Series, max_levels: int) -> DepthSnapshot:
    buy_vol_by_price: Dict[int, int] = {}
    sell_vol_by_price: Dict[int, int] = {}
    mid_price = float(row["mid_price"])

    for level in range(1, max_levels + 1):
        bp = row.get(f"bid_price_{level}")
        bv = row.get(f"bid_volume_{level}")
        ap = row.get(f"ask_price_{level}")
        av = row.get(f"ask_volume_{level}")

        if pd.notna(bp) and pd.notna(bv) and int(bv) > 0:
            buy_vol_by_price[int(bp)] = int(bv)
        if pd.notna(ap) and pd.notna(av) and int(av) > 0:
            sell_vol_by_price[int(ap)] = int(av)

    return DepthSnapshot(buy_vol_by_price=buy_vol_by_price, sell_vol_by_price=sell_vol_by_price, mid_price=mid_price)


def depth_to_order_depth(depth: DepthSnapshot) -> OrderDepth:
    order_depth = OrderDepth()
    order_depth.buy_orders = dict(depth.buy_vol_by_price)
    order_depth.sell_orders = {price: -qty for price, qty in depth.sell_vol_by_price.items()}
    return order_depth


def load_day_prices_and_trades(day: int, product: str, max_levels: int) -> Tuple[Dict[int, DepthSnapshot], pd.DataFrame]:
    prices_path = DATA_DIR / f"prices_round_1_day_{day}.csv"
    trades_path = DATA_DIR / f"trades_round_1_day_{day}.csv"
    if not prices_path.exists() or not trades_path.exists():
        raise FileNotFoundError(f"Missing CSVs for day {day}")

    prices_df = pd.read_csv(prices_path, sep=";")
    prices_df = prices_df[prices_df["product"] == product].copy()
    for column in prices_df.columns:
        if column != "product":
            prices_df[column] = pd.to_numeric(prices_df[column], errors="coerce")
    empty_book = prices_df["bid_price_1"].isna() & prices_df["ask_price_1"].isna()
    prices_df.loc[empty_book, "mid_price"] = np.nan
    prices_df = prices_df.dropna(subset=["mid_price"]).copy()
    prices_df["timestamp"] = prices_df["timestamp"].astype(int)

    depth_by_ts: Dict[int, DepthSnapshot] = {}
    for _, row in prices_df.iterrows():
        depth_by_ts[int(row["timestamp"])] = build_depth_snapshot_from_prices_row(row, max_levels=max_levels)

    trades_df = pd.read_csv(trades_path, sep=";")
    trades_df = trades_df[trades_df["symbol"] == product].copy()
    if not trades_df.empty:
        trades_df["timestamp"] = pd.to_numeric(trades_df["timestamp"], errors="coerce").astype(int)
        trades_df["price"] = pd.to_numeric(trades_df["price"], errors="coerce").round().astype(int)
        trades_df["quantity"] = pd.to_numeric(trades_df["quantity"], errors="coerce").round().astype(int)
    return depth_by_ts, trades_df


def compute_drawdown(equity: pd.Series) -> pd.Series:
    return equity - equity.cummax()


def compute_risk_metrics(results_df: pd.DataFrame, *, pnl_col: str) -> Dict[str, float]:
    pnl = results_df[pnl_col]
    pnl_increments = pnl.diff().dropna()
    if pnl_increments.empty:
        return {}

    mean_inc = float(pnl_increments.mean())
    std_inc = float(pnl_increments.std(ddof=1)) if len(pnl_increments) > 1 else 0.0
    sharpe_like = float(mean_inc / std_inc * math.sqrt(len(pnl_increments))) if std_inc > 0 else np.nan
    drawdown = compute_drawdown(results_df[pnl_col])
    var_95 = float(pnl_increments.quantile(0.05))
    tail = pnl_increments[pnl_increments <= var_95]
    cvar_95 = float(tail.mean()) if not tail.empty else var_95
    positive = pnl_increments[pnl_increments > 0].sum()
    negative = pnl_increments[pnl_increments < 0].sum()

    return {
        "total_pnl": float(pnl.iloc[-1]),
        "mean_pnl_increment": mean_inc,
        "pnl_increment_vol": std_inc,
        "sharpe_like": sharpe_like,
        "max_drawdown": float(drawdown.min()),
        "var_95_pnl_inc": var_95,
        "cvar_95_pnl_inc": cvar_95,
        "win_rate_increment": float((pnl_increments > 0).mean()),
        "profit_factor_increment": float(positive / abs(negative)) if negative != 0 else np.inf,
        "max_abs_pnl_increment": float(pnl_increments.abs().max()),
        "n_increments": float(len(pnl_increments)),
    }


def compute_fill_metrics(fills_df: pd.DataFrame, results_df: pd.DataFrame) -> Dict[str, float]:
    if fills_df.empty:
        return {
            "fill_count": 0.0,
            "aggressive_fill_share": np.nan,
            "avg_fill_size": np.nan,
            "maker_share": np.nan,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
        }
    qty = fills_df["quantity"].astype(float)
    aggressive_share = float((fills_df["source"] == "AGGRESSIVE").mean())
    maker_share = float((fills_df["source"] == "MARKET_TRADE").mean())
    buy_volume = float(fills_df.loc[fills_df["side"] == "BUY", "quantity"].sum())
    sell_volume = float(fills_df.loc[fills_df["side"] == "SELL", "quantity"].sum())
    return {
        "fill_count": float(len(fills_df)),
        "aggressive_fill_share": aggressive_share,
        "avg_fill_size": float(qty.mean()),
        "maker_share": maker_share,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "max_abs_position": float(results_df["position"].abs().max()),
    }


def merge_metric_dicts(*dicts: Dict[str, float]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for data in dicts:
        merged.update(data)
    return merged


def run_backtest_on_loaded_data(
    trader,
    product: str,
    days: List[int],
    day_data: Dict[int, Tuple[Dict[int, DepthSnapshot], pd.DataFrame]],
    *,
    reset_between_days: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    max_timestamp = 0
    for depth_by_ts, _trades_df in day_data.values():
        if depth_by_ts:
            max_timestamp = max(max_timestamp, max(depth_by_ts.keys()))
    day_step = max_timestamp + 100
    min_day = min(days)

    cash = 0.0
    position = 0
    trader_data = ""
    cumulative_pnl_offset = 0.0
    fills: List[Fill] = []
    result_rows: List[Dict[str, float | int]] = []

    resting_buy: Dict[int, int] = {}
    resting_sell: Dict[int, int] = {}
    current_depth: Optional[DepthSnapshot] = None

    for day in sorted(days):
        if reset_between_days:
            cash = 0.0
            position = 0
            trader_data = ""
            resting_buy = {}
            resting_sell = {}
            current_depth = None

        depth_by_ts, trades_df = day_data[day]
        snapshot_times = sorted(depth_by_ts.keys())
        trade_times = sorted(trades_df["timestamp"].unique().tolist()) if not trades_df.empty else []
        all_times = sorted(set(snapshot_times).union(set(trade_times)))

        grouped_trades = trades_df.groupby("timestamp", sort=False) if not trades_df.empty else None

        def get_trades_at(timestamp: int) -> List[Tuple[int, int]]:
            if grouped_trades is None or timestamp not in grouped_trades.groups:
                return []
            sub = grouped_trades.get_group(timestamp)
            return [(int(row["price"]), int(row["quantity"])) for _, row in sub.iterrows() if int(row["quantity"]) > 0]

        for ts in all_times:
            if ts in depth_by_ts:
                resting_buy = {}
                resting_sell = {}
                current_depth = depth_by_ts[ts].clone_mutable()
                order_depth = depth_to_order_depth(current_depth)
                state = TradingState(
                    traderData=trader_data,
                    timestamp=int(ts),
                    listings={},
                    order_depths={product: order_depth},
                    own_trades={product: []},
                    market_trades={product: []},
                    position={product: int(position)},
                    observations=Observation({}, {}),
                )
                submitted_orders, _conversions, trader_data = trader.run(state)
                for order in submitted_orders.get(product, []):
                    qty = int(order.quantity)
                    price = int(order.price)
                    if qty == 0 or current_depth is None:
                        continue

                    if qty > 0:
                        remaining = qty
                        best_ask = current_depth.best_ask()
                        if best_ask is not None and price >= best_ask and current_depth.sell_vol_by_price:
                            for ask_price in sorted(list(current_depth.sell_vol_by_price.keys())):
                                if remaining <= 0 or ask_price > price:
                                    break
                                available = current_depth.sell_vol_by_price.get(ask_price, 0)
                                if available <= 0:
                                    continue
                                executed = min(remaining, available)
                                cash -= ask_price * executed
                                position += executed
                                global_ts = int((day - min_day) * day_step + ts)
                                fills.append(Fill(day, int(ts), global_ts, product, "BUY", int(ask_price), int(executed), "AGGRESSIVE"))
                                current_depth.sell_vol_by_price[ask_price] = available - executed
                                if current_depth.sell_vol_by_price[ask_price] <= 0:
                                    current_depth.sell_vol_by_price.pop(ask_price, None)
                                remaining -= executed
                        if remaining > 0:
                            resting_buy[price] = resting_buy.get(price, 0) + remaining
                    else:
                        remaining = -qty
                        best_bid = current_depth.best_bid()
                        if best_bid is not None and price <= best_bid and current_depth.buy_vol_by_price:
                            for bid_price in sorted(list(current_depth.buy_vol_by_price.keys()), reverse=True):
                                if remaining <= 0 or bid_price < price:
                                    break
                                available = current_depth.buy_vol_by_price.get(bid_price, 0)
                                if available <= 0:
                                    continue
                                executed = min(remaining, available)
                                cash += bid_price * executed
                                position -= executed
                                global_ts = int((day - min_day) * day_step + ts)
                                fills.append(Fill(day, int(ts), global_ts, product, "SELL", int(bid_price), int(executed), "AGGRESSIVE"))
                                current_depth.buy_vol_by_price[bid_price] = available - executed
                                if current_depth.buy_vol_by_price[bid_price] <= 0:
                                    current_depth.buy_vol_by_price.pop(bid_price, None)
                                remaining -= executed
                        if remaining > 0:
                            resting_sell[price] = resting_sell.get(price, 0) + remaining

                if current_depth is not None:
                    global_ts = int((day - min_day) * day_step + ts)
                    mid_price = float(current_depth.mid_price)
                    equity = cash + position * mid_price
                    result_rows.append(
                        {
                            "day": int(day),
                            "timestamp": int(ts),
                            "global_ts": global_ts,
                            "mid_price": mid_price,
                            "cash": float(cash),
                            "position": int(position),
                            "equity": float(equity),
                            "pnl": float(cumulative_pnl_offset + equity),
                        }
                    )

            trades_at_time = get_trades_at(ts)
            if trades_at_time and current_depth is not None:
                for trade_price, trade_qty in trades_at_time:
                    remaining = int(trade_qty)
                    best_bid = current_depth.best_bid()
                    best_ask = current_depth.best_ask()
                    side: Optional[str] = None
                    if best_bid is not None and trade_price == best_bid:
                        side = "MARKET_SELL_HIT_BIDS"
                    elif best_ask is not None and trade_price == best_ask:
                        side = "MARKET_BUY_HIT_ASKS"
                    elif trade_price in current_depth.buy_vol_by_price:
                        side = "MARKET_SELL_HIT_BIDS"
                    elif trade_price in current_depth.sell_vol_by_price:
                        side = "MARKET_BUY_HIT_ASKS"

                    if side == "MARKET_SELL_HIT_BIDS":
                        available_external = current_depth.buy_vol_by_price.get(trade_price, 0)
                        trade_take = min(remaining, available_external)
                        candidate_prices = sorted((p for p in resting_buy if p >= trade_price), reverse=True)
                        remaining_to_fill = int(trade_take)
                        for candidate_price in candidate_prices:
                            if remaining_to_fill <= 0:
                                break
                            resting_qty = resting_buy.get(candidate_price, 0)
                            executed = min(remaining_to_fill, resting_qty)
                            if executed > 0:
                                cash -= trade_price * executed
                                position += executed
                                global_ts = int((day - min_day) * day_step + ts)
                                fills.append(Fill(day, int(ts), global_ts, product, "BUY", int(trade_price), int(executed), "MARKET_TRADE"))
                                new_qty = resting_qty - executed
                                if new_qty <= 0:
                                    resting_buy.pop(candidate_price, None)
                                else:
                                    resting_buy[candidate_price] = new_qty
                                remaining_to_fill -= executed
                        if available_external > 0:
                            current_depth.buy_vol_by_price[trade_price] = max(0, available_external - trade_take)
                            if current_depth.buy_vol_by_price[trade_price] == 0:
                                current_depth.buy_vol_by_price.pop(trade_price, None)

                    elif side == "MARKET_BUY_HIT_ASKS":
                        available_external = current_depth.sell_vol_by_price.get(trade_price, 0)
                        trade_take = min(remaining, available_external)
                        candidate_prices = sorted((p for p in resting_sell if p <= trade_price))
                        remaining_to_fill = int(trade_take)
                        for candidate_price in candidate_prices:
                            if remaining_to_fill <= 0:
                                break
                            resting_qty = resting_sell.get(candidate_price, 0)
                            executed = min(remaining_to_fill, resting_qty)
                            if executed > 0:
                                cash += trade_price * executed
                                position -= executed
                                global_ts = int((day - min_day) * day_step + ts)
                                fills.append(Fill(day, int(ts), global_ts, product, "SELL", int(trade_price), int(executed), "MARKET_TRADE"))
                                new_qty = resting_qty - executed
                                if new_qty <= 0:
                                    resting_sell.pop(candidate_price, None)
                                else:
                                    resting_sell[candidate_price] = new_qty
                                remaining_to_fill -= executed
                        if available_external > 0:
                            current_depth.sell_vol_by_price[trade_price] = max(0, available_external - trade_take)
                            if current_depth.sell_vol_by_price[trade_price] == 0:
                                current_depth.sell_vol_by_price.pop(trade_price, None)

        if reset_between_days and current_depth is not None:
            cumulative_pnl_offset += float(cash + position * current_depth.mid_price)

    results_df = pd.DataFrame(result_rows).sort_values("global_ts").reset_index(drop=True)
    fills_df = pd.DataFrame([fill.__dict__ for fill in fills]).sort_values("global_ts").reset_index(drop=True) if fills else pd.DataFrame(
        columns=["day", "timestamp", "global_ts", "product", "side", "price", "quantity", "source"]
    )

    metrics = merge_metric_dicts(compute_risk_metrics(results_df, pnl_col="pnl"), compute_fill_metrics(fills_df, results_df))
    return results_df, fills_df, metrics


def run_backtest(
    model_name: str,
    product: str,
    days: List[int],
    max_levels: int,
    *,
    reset_between_days: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    TraderClass = load_trader(model_name)
    trader = TraderClass()

    day_data: Dict[int, Tuple[Dict[int, DepthSnapshot], pd.DataFrame]] = {}
    for day in days:
        day_data[day] = load_day_prices_and_trades(day, product, max_levels=max_levels)

    return run_backtest_on_loaded_data(trader, product, days, day_data, reset_between_days=reset_between_days)


def plot_backtest_dashboard(
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    metrics: Dict[str, float],
    model_name: str,
    product: str,
    days: List[int],
    output_dir: Path,
    filename_suffix: str = "",
) -> None:
    configure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    day_tag = "_".join(str(day) for day in days)
    suffix_tag = f"_{filename_suffix}" if filename_suffix else ""

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax_pnl, ax_inventory, ax_drawdown, ax_fills = axes.flatten()

    sns.lineplot(data=results_df, x="global_ts", y="pnl", ax=ax_pnl, color="#2563EB", linewidth=2.4)
    ax_pnl.set_title("Mark-to-market PnL")
    ax_pnl.set_xlabel("chronological time")
    ax_pnl.set_ylabel("PnL")
    ax_pnl.text(0.02, 0.95, f"final PnL {metrics['total_pnl']:.0f}", transform=ax_pnl.transAxes, va="top", fontsize=10)

    sns.lineplot(data=results_df, x="global_ts", y="position", ax=ax_inventory, color="#F97316", linewidth=2.0)
    ax_inventory.axhline(0, color="#111827", linewidth=1.0)
    ax_inventory.set_title("Inventory path")
    ax_inventory.set_xlabel("chronological time")
    ax_inventory.set_ylabel("position")
    ax_inventory.text(0.02, 0.95, f"max |pos| {metrics['max_abs_position']:.0f}", transform=ax_inventory.transAxes, va="top", fontsize=10)

    drawdown_df = results_df.copy()
    drawdown_df["drawdown"] = compute_drawdown(drawdown_df["pnl"])
    sns.lineplot(data=drawdown_df, x="global_ts", y="drawdown", ax=ax_drawdown, color="#DC2626", linewidth=2.0)
    ax_drawdown.set_title("Drawdown")
    ax_drawdown.set_xlabel("chronological time")
    ax_drawdown.set_ylabel("drawdown")
    ax_drawdown.text(0.02, 0.95, f"max DD {metrics['max_drawdown']:.0f}", transform=ax_drawdown.transAxes, va="top", fontsize=10)

    if not fills_df.empty:
        fills_plot = fills_df.copy()
        fills_plot["size"] = fills_plot["quantity"].clip(lower=1) * 10
        fills_plot["color"] = fills_plot["side"].map({"BUY": "#10B981", "SELL": "#EF4444"})
        ax_fills.scatter(fills_plot["global_ts"], fills_plot["price"], s=fills_plot["size"], c=fills_plot["color"], alpha=0.35, linewidths=0)
    sns.lineplot(data=results_df, x="global_ts", y="mid_price", ax=ax_fills, color="#111827", linewidth=1.2)
    ax_fills.set_title("Mid price + fills")
    ax_fills.set_xlabel("chronological time")
    ax_fills.set_ylabel("price")

    fig.suptitle(f"{model_name} — {product} backtest dashboard", x=0.01, y=1.02, ha="left", fontsize=20, fontweight="bold")
    fig.text(
        0.01,
        0.985,
        f"Days {day_tag} · maker share {metrics.get('maker_share', np.nan):.2%} · aggressive fill share {metrics.get('aggressive_fill_share', np.nan):.2%}",
        fontsize=11,
        color="#4B5563",
    )
    fig.subplots_adjust(top=0.88, hspace=0.30, wspace=0.18)
    fig.savefig(output_dir / f"backtest_{model_name}_dashboard_{day_tag}{suffix_tag}.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 4.8))
    pnl_inc = results_df["pnl"].diff().dropna()
    sns.histplot(pnl_inc, bins=60, kde=True, ax=ax, color="#7C3AED")
    ax.set_title("PnL increment distribution")
    ax.set_xlabel("PnL increment")
    ax.set_ylabel("count")
    fig.savefig(output_dir / f"backtest_{model_name}_pnl_increment_dist_{day_tag}{suffix_tag}.png", dpi=180)
    plt.close(fig)


def plot_metrics_table(
    metrics: Dict[str, float],
    model_name: str,
    product: str,
    days: List[int],
    output_dir: Path,
    filename_suffix: str = "",
) -> None:
    configure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    day_tag = "_".join(str(day) for day in days)
    suffix_tag = f"_{filename_suffix}" if filename_suffix else ""

    rows = [
        ("Total PnL", metrics.get("total_pnl")),
        ("Sharpe-like", metrics.get("sharpe_like")),
        ("Max drawdown", metrics.get("max_drawdown")),
        ("Win rate (inc)", metrics.get("win_rate_increment")),
        ("Profit factor", metrics.get("profit_factor_increment")),
        ("PnL inc vol", metrics.get("pnl_increment_vol")),
        ("VaR 95% inc", metrics.get("var_95_pnl_inc")),
        ("CVaR 95% inc", metrics.get("cvar_95_pnl_inc")),
        ("Fill count", metrics.get("fill_count")),
        ("Maker share", metrics.get("maker_share")),
        ("Aggressive fill share", metrics.get("aggressive_fill_share")),
        ("Avg fill size", metrics.get("avg_fill_size")),
        ("Max |position|", metrics.get("max_abs_position")),
    ]

    fig, ax = plt.subplots(figsize=(8.2, 6.0))
    ax.axis("off")
    cell_text = [[name, "" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:.4g}" if isinstance(value, (int, float)) else str(value)] for name, value in rows]
    table = ax.table(cellText=cell_text, colLabels=["Metric", "Value"], loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.6)
    ax.set_title(f"{model_name} — {product} metrics (days {day_tag})", fontsize=16, pad=18)
    fig.savefig(output_dir / f"backtest_{model_name}_metrics_table_{day_tag}{suffix_tag}.png", dpi=180)
    plt.close(fig)


def write_summary(
    results_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    metrics: Dict[str, float],
    model_name: str,
    product: str,
    days: List[int],
    output_dir: Path,
    filename_suffix: str = "",
) -> None:
    day_tag = "_".join(str(day) for day in days)
    suffix_tag = f"_{filename_suffix}" if filename_suffix else ""
    by_day_cumulative = results_df.groupby("day", sort=True)["pnl"].last()
    by_day = by_day_cumulative.diff().fillna(by_day_cumulative).to_dict()
    lines = [
        f"# {model_name} — {product} backtest summary",
        "",
        f"- Days: {days}",
        f"- Final PnL: {metrics['total_pnl']:.1f}",
        f"- Sharpe-like: {metrics['sharpe_like']:.3f}",
        f"- Max drawdown: {metrics['max_drawdown']:.1f}",
        f"- Maker share: {metrics.get('maker_share', np.nan):.2%}",
        f"- Max |position|: {metrics.get('max_abs_position', np.nan):.0f}",
        "",
        "## PnL by day",
    ]
    for day in days:
        lines.append(f"- day {day}: {by_day.get(day, np.nan):.1f}")
    output_path = output_dir / f"backtest_{model_name}_summary_{day_tag}{suffix_tag}.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    results_df, fills_df, metrics = run_backtest(
        args.model,
        args.product,
        list(args.days),
        args.max_lob_levels,
        reset_between_days=args.reset_between_days,
    )
    output_dir = Path(args.output_dir) / args.model
    output_dir.mkdir(parents=True, exist_ok=True)
    day_tag = "_".join(str(day) for day in args.days)
    suffix_tag = f"_{args.output_suffix}" if args.output_suffix else ""

    results_df.to_csv(output_dir / f"backtest_{args.model}_results_{day_tag}{suffix_tag}.csv", index=False)
    fills_df.to_csv(output_dir / f"backtest_{args.model}_fills_{day_tag}{suffix_tag}.csv", index=False)
    plot_backtest_dashboard(
        results_df,
        fills_df,
        metrics,
        args.model,
        args.product,
        list(args.days),
        output_dir,
        filename_suffix=args.output_suffix,
    )
    plot_metrics_table(metrics, args.model, args.product, list(args.days), output_dir, filename_suffix=args.output_suffix)
    write_summary(
        results_df,
        fills_df,
        metrics,
        args.model,
        args.product,
        list(args.days),
        output_dir,
        filename_suffix=args.output_suffix,
    )

    print(f"Backtest complete for {args.model} on {args.product}")
    for key, value in metrics.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            print(f"  {key}: {value}")
        else:
            print(f"  {key}: {value:.6g}" if isinstance(value, float) else f"  {key}: {value}")
    print(f"Saved results to {output_dir}")


if __name__ == "__main__":
    main()
