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

# This repo's strategy examples use `from datamodel import ...` (no package prefix).
MODELS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODELS_DIR.parent
DATA_DIR = PROJECT_ROOT / "data_tutorial"
BACKTEST_PLOTS_BASE_DIR = MODELS_DIR / "backtest_plots"

sys.path.insert(0, str(MODELS_DIR))

from datamodel import (  # noqa: E402
    Observation,
    Order,
    OrderDepth,
    TradingState,
)


PRODUCTS = ["TOMATOES", "EMERALDS"]
DEFAULT_DAYS = [-2, -1]


@dataclass
class DepthSnapshot:
    # Volumes at price levels for the *external* book only.
    buy_vol_by_price: Dict[int, int]  # positive quantities
    sell_vol_by_price: Dict[int, int]  # positive quantities
    mid_price: float

    def best_bid(self) -> Optional[int]:
        return max(self.buy_vol_by_price.keys()) if self.buy_vol_by_price else None

    def best_ask(self) -> Optional[int]:
        return min(self.sell_vol_by_price.keys()) if self.sell_vol_by_price else None

    def clone_mutable(self) -> "DepthSnapshot":
        return DepthSnapshot(
            buy_vol_by_price=dict(self.buy_vol_by_price),
            sell_vol_by_price=dict(self.sell_vol_by_price),
            mid_price=self.mid_price,
        )


@dataclass
class Fill:
    day: int
    timestamp: int
    product: str
    side: str  # "BUY" or "SELL"
    price: int
    quantity: int
    source: str  # "AGGRESSIVE" (crossing) or "MARKET_TRADE" (external market consuming resting)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest a selected models_tutorial strategy.")
    parser.add_argument(
        "--model",
        type=str,
        default="model_v0",
        help="Model filename under models_tutorial (e.g. model_v0, emerald_only).",
    )
    parser.add_argument("--days", type=int, nargs="*", default=DEFAULT_DAYS, help="Days to backtest (e.g. -2 -1).")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(BACKTEST_PLOTS_BASE_DIR),
        help="Base directory to save plots (model subfolder will be created inside).",
    )
    parser.add_argument(
        "--max-lob-levels",
        type=int,
        default=3,
        help="How many book levels to read from prices_* snapshots.",
    )
    return parser.parse_args()


def load_trader(model_name: str):
    model_path = MODELS_DIR / f"{model_name}.py"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # Ensure `from datamodel import ...` works inside dynamically loaded module.
    if str(MODELS_DIR) not in sys.path:
        sys.path.insert(0, str(MODELS_DIR))

    spec = importlib.util.spec_from_file_location(f"models_tutorial_{model_name}", model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load model module: {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    if not hasattr(module, "Trader"):
        raise AttributeError(f"Model must define class Trader: {model_path}")
    return module.Trader


def build_depth_snapshot_from_prices_row(row: pd.Series, max_levels: int) -> DepthSnapshot:
    # The prices_* files encode up to 3 book levels as bid_price_i / bid_volume_i / ask_price_i / ask_volume_i.
    buy_vol_by_price: Dict[int, int] = {}
    sell_vol_by_price: Dict[int, int] = {}

    mid_price = float(row["mid_price"])

    for i in range(1, max_levels + 1):
        bp = row.get(f"bid_price_{i}")
        bv = row.get(f"bid_volume_{i}")
        ap = row.get(f"ask_price_{i}")
        av = row.get(f"ask_volume_{i}")

        if pd.notna(bp) and pd.notna(bv) and int(bv) > 0:
            buy_vol_by_price[int(bp)] = int(bv)
        if pd.notna(ap) and pd.notna(av) and int(av) > 0:
            sell_vol_by_price[int(ap)] = int(av)

    return DepthSnapshot(buy_vol_by_price=buy_vol_by_price, sell_vol_by_price=sell_vol_by_price, mid_price=mid_price)


def depth_to_order_depth(depth: DepthSnapshot) -> OrderDepth:
    od = OrderDepth()
    od.buy_orders = dict(depth.buy_vol_by_price)
    # In datamodel, sell volumes are stored as negative values.
    od.sell_orders = {p: -q for p, q in depth.sell_vol_by_price.items()}
    return od


def load_day_prices_and_trades(day: int, max_levels: int) -> Tuple[Dict[int, Dict[str, DepthSnapshot]], pd.DataFrame]:
    prices_path = DATA_DIR / f"prices_round_0_day_{day}.csv"
    trades_path = DATA_DIR / f"trades_round_0_day_{day}.csv"

    if not prices_path.exists():
        raise FileNotFoundError(prices_path)
    if not trades_path.exists():
        raise FileNotFoundError(trades_path)

    df_prices = pd.read_csv(prices_path, sep=";")
    df_prices = df_prices[df_prices["product"].isin(PRODUCTS)].copy()
    df_prices["timestamp"] = df_prices["timestamp"].astype(int)
    df_prices["mid_price"] = df_prices["mid_price"].astype(float)

    depth_by_ts_product: Dict[int, Dict[str, DepthSnapshot]] = {}
    for _, r in df_prices.iterrows():
        ts = int(r["timestamp"])
        product = str(r["product"])
        depth_by_ts_product.setdefault(ts, {})[product] = build_depth_snapshot_from_prices_row(r, max_levels=max_levels)

    df_trades = pd.read_csv(trades_path, sep=";")
    df_trades = df_trades[df_trades["symbol"].isin(PRODUCTS)].copy()
    df_trades["timestamp"] = df_trades["timestamp"].astype(int)
    df_trades["price"] = df_trades["price"].astype(float).round().astype(int)
    df_trades["quantity"] = df_trades["quantity"].astype(float).round().astype(int)

    return depth_by_ts_product, df_trades


def compute_drawdown(equity: pd.Series) -> pd.Series:
    running_max = equity.cummax()
    dd = equity - running_max
    return dd


def compute_risk_metrics(
    equity_df: pd.DataFrame,
    *,
    equity_col: str,
    pnl_col: str,
) -> Dict[str, float]:
    # Uses mark-to-market PnL increments between successive snapshots.
    pnl_increments = equity_df[pnl_col].diff().dropna()
    if len(pnl_increments) == 0:
        return {}

    total_pnl = float(equity_df[pnl_col].iloc[-1])
    mean_inc = float(pnl_increments.mean())
    std_inc = float(pnl_increments.std(ddof=1)) if len(pnl_increments) > 1 else 0.0

    # Not a "true" return Sharpe (since no risk-free rate and scale is PnL increments),
    # but useful as a relative stability metric.
    sharpe = float(mean_inc / std_inc * math.sqrt(len(pnl_increments))) if std_inc > 0 else np.nan

    dd = compute_drawdown(equity_df[equity_col])
    max_drawdown = float(dd.min())  # negative number

    var_95 = float(pnl_increments.quantile(0.05))
    cvar_95 = float(pnl_increments[pnl_increments <= var_95].mean()) if (pnl_increments <= var_95).any() else var_95

    win_rate = float((pnl_increments > 0).mean())
    profit_factor = float(pnl_increments[pnl_increments > 0].sum() / abs(pnl_increments[pnl_increments < 0].sum())) if (
        (pnl_increments < 0).any() and (pnl_increments[pnl_increments < 0].sum() != 0)
    ) else np.inf

    max_abs_increment = float(pnl_increments.abs().max())

    return {
        "total_pnl": total_pnl,
        "mean_pnl_increment": mean_inc,
        "pnl_increment_vol": std_inc,
        "sharpe_like": sharpe,
        "max_drawdown": max_drawdown,
        "var_95_pnl_inc": var_95,
        "cvar_95_pnl_inc": cvar_95,
        "win_rate_increment": win_rate,
        "profit_factor_increment": profit_factor,
        "max_abs_pnl_increment": max_abs_increment,
        "n_increments": float(len(pnl_increments)),
    }


def plot_backtest(
    equity_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    model_name: str,
    days: List[int],
    output_dir: Path,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="talk")

    day_str = "_".join(str(d) for d in days)

    # Equity curves (PnL)
    fig, ax = plt.subplots(figsize=(14, 6))
    sns.lineplot(data=equity_df, x="global_ts", y="pnl_TOMATOES", ax=ax, label="TOMATOES PnL")
    sns.lineplot(data=equity_df, x="global_ts", y="pnl_EMERALDS", ax=ax, label="EMERALDS PnL")
    sns.lineplot(data=equity_df, x="global_ts", y="pnl_total", ax=ax, label="Total PnL", linewidth=2.5, color="black")
    ax.set_title(f"{model_name}: Mark-to-market PnL (TOMATOES + EMERALDS) | days {day_str}")
    ax.set_xlabel("chronological timestamp (global_ts)")
    ax.set_ylabel("PnL")
    fig.tight_layout()
    fig.savefig(output_dir / f"backtest_{model_name}_pnl_curves_{day_str}.png", dpi=160)
    plt.close(fig)

    # Drawdown curve
    fig, ax = plt.subplots(figsize=(14, 5))
    drawdown = equity_df["equity_total"] - equity_df["equity_total"].cummax()
    sns.lineplot(data=equity_df, x="global_ts", y=drawdown, ax=ax, color="#d62728")
    ax.set_title(f"{model_name}: Total drawdown | days {day_str}")
    ax.set_xlabel("chronological timestamp (global_ts)")
    ax.set_ylabel("Drawdown (equity - running_max)")
    fig.tight_layout()
    fig.savefig(output_dir / f"backtest_{model_name}_drawdown_{day_str}.png", dpi=160)
    plt.close(fig)

    # Inventory over time
    fig, ax = plt.subplots(figsize=(14, 5))
    sns.lineplot(data=inventory_df, x="global_ts", y="position_TOMATOES", ax=ax, label="TOMATOES position")
    sns.lineplot(data=inventory_df, x="global_ts", y="position_EMERALDS", ax=ax, label="EMERALDS position")
    ax.axhline(0, color="black", linewidth=1)
    ax.set_title(f"{model_name}: Inventory over time | days {day_str}")
    ax.set_xlabel("chronological timestamp (global_ts)")
    ax.set_ylabel("Position")
    fig.tight_layout()
    fig.savefig(output_dir / f"backtest_{model_name}_inventory_{day_str}.png", dpi=160)
    plt.close(fig)

    # PnL increment distribution
    pnl_incs = equity_df["pnl_total"].diff().dropna()
    fig, ax = plt.subplots(figsize=(12, 5))
    sns.histplot(pnl_incs, bins=60, kde=True, ax=ax, color="#1f77b4")
    ax.set_title(f"{model_name}: Total PnL increment distribution | days {day_str}")
    ax.set_xlabel("PnL increment between snapshots")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(output_dir / f"backtest_{model_name}_pnl_increment_dist_{day_str}.png", dpi=160)
    plt.close(fig)

    # Rolling volatility of PnL increments
    window = min(200, max(20, len(pnl_incs) // 10)) if len(pnl_incs) > 5 else 5
    rolling_vol = pnl_incs.rolling(window=window).std()
    # Align with equity_df index (rolling_vol starts after some rows)
    vol_df = equity_df.iloc[1:].copy()
    vol_df["rolling_vol"] = rolling_vol.values

    fig, ax = plt.subplots(figsize=(14, 5))
    sns.lineplot(data=vol_df, x="global_ts", y="rolling_vol", ax=ax, color="#9467bd")
    ax.set_title(f"{model_name}: Rolling volatility of PnL increments (window={window}) | days {day_str}")
    ax.set_xlabel("chronological timestamp (global_ts)")
    ax.set_ylabel("PnL increment volatility")
    fig.tight_layout()
    fig.savefig(output_dir / f"backtest_{model_name}_rolling_vol_{day_str}.png", dpi=160)
    plt.close(fig)


def plot_metrics_table(
    *,
    model_name: str,
    days: List[int],
    output_dir: Path,
    metrics_total: Dict[str, float],
    metrics_by_product: Dict[str, Dict[str, float]],
):
    output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="talk")

    day_str = "_".join(str(d) for d in days)

    # Select a curated set of metrics for visual comparison.
    columns = [
        "total_pnl",
        "mean_pnl_increment",
        "pnl_increment_vol",
        "sharpe_like",
        "max_drawdown",
        "var_95_pnl_inc",
        "cvar_95_pnl_inc",
        "win_rate_increment",
        "profit_factor_increment",
        "max_abs_pnl_increment",
    ]

    row_names = ["TOTAL", "TOMATOES", "EMERALDS"]
    col_labels = {
        "total_pnl": "Total PnL",
        "mean_pnl_increment": "Mean PnL inc",
        "pnl_increment_vol": "PnL inc vol",
        "sharpe_like": "Sharpe-like",
        "max_drawdown": "Max drawdown",
        "var_95_pnl_inc": "VaR 95% (inc)",
        "cvar_95_pnl_inc": "CVaR 95% (inc)",
        "win_rate_increment": "Win rate (inc)",
        "profit_factor_increment": "Profit factor",
        "max_abs_pnl_increment": "Max abs inc",
    }

    def fmt(k: str, v: float) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return str(v)
        if k in {"win_rate_increment"}:
            return f"{v:.3f}"
        if k in {"profit_factor_increment"}:
            return f"{v:.3g}"
        if k in {"total_pnl"}:
            return f"{v:.0f}"
        # Default numeric formatting for remaining metrics.
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    metrics_rows: Dict[str, Dict[str, float]] = {"TOTAL": metrics_total}
    metrics_rows["TOMATOES"] = metrics_by_product["TOMATOES"]
    metrics_rows["EMERALDS"] = metrics_by_product["EMERALDS"]

    cell_text: List[List[str]] = []
    for row in row_names:
        m = metrics_rows[row]
        row_vals: List[str] = []
        for c in columns:
            v = m.get(c, np.nan)  # type: ignore[assignment]
            row_vals.append(fmt(c, float(v)))
        cell_text.append(row_vals)

    fig, ax = plt.subplots(figsize=(16, 5.6))
    ax.axis("off")

    table = ax.table(
        cellText=cell_text,
        rowLabels=row_names,
        colLabels=[col_labels[c] for c in columns],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.5)

    ax.set_title(f"{model_name}: risk metrics table (days {day_str})", fontsize=16, pad=20)

    out_path = output_dir / f"backtest_{model_name}_metrics_table_{day_str}.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def run_backtest(model_name: str, days: List[int], max_levels: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[Fill]]:
    TraderClass = load_trader(model_name)
    trader = TraderClass()

    # Global timestamp scaling for plots / metrics time axis.
    all_max_ts = []
    per_day_depths: Dict[int, Dict[int, Dict[str, DepthSnapshot]]] = {}
    per_day_trades: Dict[int, pd.DataFrame] = {}
    for day in days:
        depth_by_ts_product, df_trades = load_day_prices_and_trades(day, max_levels=max_levels)
        per_day_depths[day] = depth_by_ts_product
        per_day_trades[day] = df_trades
        max_ts = max(depth_by_ts_product.keys()) if depth_by_ts_product else 0
        all_max_ts.append(max_ts)
    day_step = (max(all_max_ts) + 1) if all_max_ts else 1
    min_day = min(days) if days else 0

    # Portfolio state
    cash_by_product: Dict[str, float] = {p: 0.0 for p in PRODUCTS}
    positions: Dict[str, int] = {p: 0 for p in PRODUCTS}
    trader_data = ""  # IMC uses this to persist internal strategy state.

    fills: List[Fill] = []

    equity_rows: List[Dict] = []
    inventory_rows: List[Dict] = []

    # For resting order tracking between snapshot events:
    resting_buy: Dict[str, Dict[int, int]] = {p: {} for p in PRODUCTS}   # product -> price -> remaining qty
    resting_sell: Dict[str, Dict[int, int]] = {p: {} for p in PRODUCTS}  # product -> price -> remaining qty

    for day in sorted(days):
        depth_by_ts_product = per_day_depths[day]
        trades_df = per_day_trades[day]

        # Event timeline: union of snapshot timestamps and trade timestamps.
        snapshot_times = sorted(depth_by_ts_product.keys())
        trade_times = sorted(trades_df["timestamp"].unique().tolist()) if len(trades_df) else []
        all_times = sorted(set(snapshot_times).union(set(trade_times)))

        # Current external depth state (mutates due to our aggressive actions and external trades).
        current_depth: Dict[str, Optional[DepthSnapshot]] = {p: None for p in PRODUCTS}

        # Index trades by (timestamp, product) for fast lookup.
        if len(trades_df):
            grouped_trades = trades_df.groupby(["timestamp", "symbol"], sort=False)
        else:
            grouped_trades = None

        def get_trades_at(t: int, product: str) -> List[Tuple[int, int]]:
            if grouped_trades is None:
                return []
            key = (t, product)
            if key not in grouped_trades.groups:
                return []
            sub = grouped_trades.get_group(key)
            return [(int(r["price"]), int(r["quantity"])) for _, r in sub.iterrows()]

        for ts in all_times:
            # Snapshot event: update order book snapshot + ask model for new orders; cancels previous resting orders.
            if ts in depth_by_ts_product:
                # Reset resting orders (typical "bot updates its desired order set every snapshot").
                resting_buy = {p: {} for p in PRODUCTS}
                resting_sell = {p: {} for p in PRODUCTS}

                order_depths_for_model: Dict[str, OrderDepth] = {}
                mid_prices_for_equity: Dict[str, float] = {}

                for p in PRODUCTS:
                    depth = depth_by_ts_product[ts].get(p)
                    if depth is None:
                        # If a product is missing at this snapshot, skip it (no orders).
                        continue
                    current_depth[p] = depth.clone_mutable()
                    order_depths_for_model[p] = depth_to_order_depth(depth)
                    mid_prices_for_equity[p] = depth.mid_price

                # Build TradingState for the model.
                observations = Observation(plainValueObservations={}, conversionObservations={})
                state = TradingState(
                    traderData=trader_data,
                    timestamp=int(ts),
                    listings={},
                    order_depths=order_depths_for_model,
                    own_trades={p: [] for p in PRODUCTS},
                    market_trades={p: [] for p in PRODUCTS},
                    position=dict(positions),
                    observations=observations,
                )

                # Ask for orders.
                result, _conversions, trader_data = trader.run(state)

                # Execute model orders: aggressive fills immediately against the current external depth,
                # passive remainder becomes resting for future external-market trades.
                for product in PRODUCTS:
                    if product not in result:
                        continue
                    depth = current_depth[product]
                    if depth is None:
                        continue

                    # We'll mutate these external volumes for aggressive actions only.
                    buy_vol_by_price = depth.buy_vol_by_price
                    sell_vol_by_price = depth.sell_vol_by_price

                    # Ensure we start with clean bests after mutations.
                    best_bid = depth.best_bid()
                    best_ask = depth.best_ask()

                    for order in result[product]:
                        qty = int(order.quantity)
                        price = int(order.price)
                        if qty == 0:
                            continue

                        # Buy order (qty>0): fills if price crosses current best ask.
                        if qty > 0:
                            remaining = qty
                            if best_ask is not None and price >= best_ask and sell_vol_by_price:
                                for ask_price in sorted(list(sell_vol_by_price.keys())):
                                    if remaining <= 0:
                                        break
                                    if ask_price > price:
                                        break
                                    avail = sell_vol_by_price.get(ask_price, 0)
                                    if avail <= 0:
                                        continue
                                    exec_qty = min(remaining, avail)
                                    if exec_qty > 0:
                                        cash_by_product[product] -= ask_price * exec_qty
                                        positions[product] += exec_qty
                                        fills.append(
                                            Fill(
                                                day=day,
                                                timestamp=int(ts),
                                                product=product,
                                                side="BUY",
                                                price=int(ask_price),
                                                quantity=int(exec_qty),
                                                source="AGGRESSIVE",
                                            )
                                        )
                                        sell_vol_by_price[ask_price] = avail - exec_qty
                                        remaining -= exec_qty

                                # Cleanup empty levels.
                                sell_vol_by_price = {p: q for p, q in sell_vol_by_price.items() if q > 0}
                                depth.sell_vol_by_price = sell_vol_by_price
                                best_ask = depth.best_ask()
                                best_bid = depth.best_bid()

                            if remaining > 0:
                                resting_buy[product][price] = resting_buy[product].get(price, 0) + remaining

                        # Sell order (qty<0): fills if price crosses current best bid.
                        else:
                            sell_qty = -qty
                            remaining = sell_qty
                            if best_bid is not None and price <= best_bid and buy_vol_by_price:
                                for bid_price in sorted(list(buy_vol_by_price.keys()), reverse=True):
                                    if remaining <= 0:
                                        break
                                    if bid_price < price:
                                        break
                                    avail = buy_vol_by_price.get(bid_price, 0)
                                    if avail <= 0:
                                        continue
                                    exec_qty = min(remaining, avail)
                                    if exec_qty > 0:
                                        cash_by_product[product] += bid_price * exec_qty
                                        positions[product] -= exec_qty
                                        fills.append(
                                            Fill(
                                                day=day,
                                                timestamp=int(ts),
                                                product=product,
                                                side="SELL",
                                                price=int(bid_price),
                                                quantity=int(exec_qty),
                                                source="AGGRESSIVE",
                                            )
                                        )
                                        buy_vol_by_price[bid_price] = avail - exec_qty
                                        remaining -= exec_qty

                                buy_vol_by_price = {p: q for p, q in buy_vol_by_price.items() if q > 0}
                                depth.buy_vol_by_price = buy_vol_by_price
                                best_ask = depth.best_ask()
                                best_bid = depth.best_bid()

                            if remaining > 0:
                                resting_sell[product][price] = resting_sell[product].get(price, 0) + remaining

                # Mark-to-market after fills and before external trades at the same timestamp.
                global_ts = int((day - min_day) * day_step + ts)

                equity_by_product: Dict[str, float] = {p: cash_by_product[p] + positions[p] * mid_prices_for_equity.get(p, 0.0) for p in PRODUCTS}
                equity_total = float(sum(equity_by_product.values()))

                pnl_total = equity_total  # initial equity assumed 0
                pnl_T = equity_by_product["TOMATOES"]
                pnl_E = equity_by_product["EMERALDS"]

                equity_rows.append(
                    {
                        "day": day,
                        "timestamp": int(ts),
                        "global_ts": global_ts,
                        "equity_total": equity_total,
                        "pnl_total": pnl_total,
                        "pnl_TOMATOES": pnl_T,
                        "pnl_EMERALDS": pnl_E,
                    }
                )
                inventory_rows.append(
                    {
                        "day": day,
                        "timestamp": int(ts),
                        "global_ts": global_ts,
                        "position_TOMATOES": positions["TOMATOES"],
                        "position_EMERALDS": positions["EMERALDS"],
                    }
                )

            # Trade event: external market consumes liquidity, including our resting orders at matching prices.
            trades_at_time = []
            for product in PRODUCTS:
                for price, qty in get_trades_at(ts, product):
                    if qty <= 0:
                        continue
                    trades_at_time.append((product, price, qty))

            if trades_at_time:
                for product, trade_price, trade_qty in trades_at_time:
                    if current_depth[product] is None:
                        continue
                    depth = current_depth[product]
                    assert depth is not None

                    remaining = int(trade_qty)
                    trade_price = int(trade_price)

                    best_bid = depth.best_bid()
                    best_ask = depth.best_ask()

                    # Infer "side" as whether this trade hit bids or asks in the external book.
                    side: Optional[str] = None
                    if best_bid is not None and trade_price == best_bid:
                        side = "MARKET_SELL_HIT_BIDS"
                    elif best_ask is not None and trade_price == best_ask:
                        side = "MARKET_BUY_HIT_ASKS"
                    else:
                        # Fallback: try membership in the external depth.
                        if trade_price in depth.buy_vol_by_price and remaining > 0:
                            side = "MARKET_SELL_HIT_BIDS"
                        elif trade_price in depth.sell_vol_by_price and remaining > 0:
                            side = "MARKET_BUY_HIT_ASKS"
                        else:
                            # If we can't infer, skip our resting match and just update nothing.
                            side = None

                    if side == "MARKET_SELL_HIT_BIDS":
                        # Consumes bid liquidity -> can fill our resting BUYs at this price.
                        avail_external = depth.buy_vol_by_price.get(trade_price, 0)
                        trade_take = min(remaining, avail_external) if avail_external is not None else remaining

                        # If the external market trades at price P and consumes bids,
                        # our resting limit buys with limit >= P would also execute (at price P).
                        candidate_prices = sorted((p for p in resting_buy[product].keys() if p >= trade_price), reverse=True)
                        remaining_to_fill = int(trade_take)
                        for candidate_price in candidate_prices:
                            if remaining_to_fill <= 0:
                                break
                            resting_qty = resting_buy[product].get(candidate_price, 0)
                            if resting_qty <= 0:
                                resting_buy[product].pop(candidate_price, None)
                                continue
                            exec_qty = min(remaining_to_fill, resting_qty)
                            if exec_qty > 0:
                                cash_by_product[product] -= trade_price * exec_qty
                                positions[product] += exec_qty
                                fills.append(
                                    Fill(
                                        day=day,
                                        timestamp=int(ts),
                                        product=product,
                                        side="BUY",
                                        price=trade_price,
                                        quantity=int(exec_qty),
                                        source="MARKET_TRADE",
                                    )
                                )
                                new_qty = resting_qty - exec_qty
                                if new_qty <= 0:
                                    resting_buy[product].pop(candidate_price, None)
                                else:
                                    resting_buy[product][candidate_price] = new_qty
                                remaining_to_fill -= exec_qty

                        # Update external depth volume at that level.
                        if avail_external > 0:
                            depth.buy_vol_by_price[trade_price] = max(0, avail_external - trade_take)
                            if depth.buy_vol_by_price[trade_price] == 0:
                                depth.buy_vol_by_price.pop(trade_price, None)

                    elif side == "MARKET_BUY_HIT_ASKS":
                        # Consumes ask liquidity -> can fill our resting SELLs at this price.
                        avail_external = depth.sell_vol_by_price.get(trade_price, 0)
                        trade_take = min(remaining, avail_external) if avail_external is not None else remaining

                        # If external trades consume asks at price P,
                        # our resting limit sells with limit <= P would execute (at price P).
                        candidate_prices = sorted((p for p in resting_sell[product].keys() if p <= trade_price))
                        remaining_to_fill = int(trade_take)
                        for candidate_price in candidate_prices:
                            if remaining_to_fill <= 0:
                                break
                            resting_qty = resting_sell[product].get(candidate_price, 0)
                            if resting_qty <= 0:
                                resting_sell[product].pop(candidate_price, None)
                                continue
                            exec_qty = min(remaining_to_fill, resting_qty)
                            if exec_qty > 0:
                                cash_by_product[product] += trade_price * exec_qty
                                positions[product] -= exec_qty
                                fills.append(
                                    Fill(
                                        day=day,
                                        timestamp=int(ts),
                                        product=product,
                                        side="SELL",
                                        price=trade_price,
                                        quantity=int(exec_qty),
                                        source="MARKET_TRADE",
                                    )
                                )
                                new_qty = resting_qty - exec_qty
                                if new_qty <= 0:
                                    resting_sell[product].pop(candidate_price, None)
                                else:
                                    resting_sell[product][candidate_price] = new_qty
                                remaining_to_fill -= exec_qty

                        if avail_external > 0:
                            depth.sell_vol_by_price[trade_price] = max(0, avail_external - trade_take)
                            if depth.sell_vol_by_price[trade_price] == 0:
                                depth.sell_vol_by_price.pop(trade_price, None)

                    remaining = 0  # consume entire trade qty in this simplified model

    equity_df = pd.DataFrame(equity_rows).sort_values("global_ts").reset_index(drop=True)
    inventory_df = pd.DataFrame(inventory_rows).sort_values("global_ts").reset_index(drop=True)
    fills_df = pd.DataFrame([f.__dict__ for f in fills])

    return equity_df, inventory_df, fills_df, fills


def main() -> None:
    args = parse_args()

    equity_df, inventory_df, fills_df, _fills = run_backtest(
        model_name=args.model,
        days=args.days,
        max_levels=args.max_lob_levels,
    )

    if equity_df.empty:
        print("No equity points produced; check input CSVs and model.")
        return

    metrics_total = compute_risk_metrics(equity_df, equity_col="equity_total", pnl_col="pnl_total")
    print("\nRisk metrics (TOTAL equity / total PnL increments):")
    for k, v in metrics_total.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v:.6g}" if isinstance(v, float) else f"  {k}: {v}")

    metrics_by_product: Dict[str, Dict[str, float]] = {}
    for product in ["TOMATOES", "EMERALDS"]:
        pnl_col = "pnl_TOMATOES" if product == "TOMATOES" else "pnl_EMERALDS"
        metrics_prod = compute_risk_metrics(equity_df, equity_col=pnl_col, pnl_col=pnl_col)
        metrics_by_product[product] = metrics_prod
        print(f"\nRisk metrics ({product} only):")
        for k, v in metrics_prod.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v:.6g}" if isinstance(v, float) else f"  {k}: {v}")

    # Max inventory stats
    max_pos_t = int(inventory_df["position_TOMATOES"].abs().max())
    max_pos_e = int(inventory_df["position_EMERALDS"].abs().max())
    print("\nInventory stats (max absolute position):")
    print(f"  TOMATOES: {max_pos_t}")
    print(f"  EMERALDS: {max_pos_e}")

    output_dir_base = Path(args.output_dir)
    # Create a per-model "repo" folder inside the base dir.
    output_dir = output_dir_base / args.model
    plot_backtest(
        equity_df=equity_df,
        inventory_df=inventory_df,
        model_name=args.model,
        days=list(args.days),
        output_dir=output_dir,
    )

    plot_metrics_table(
        model_name=args.model,
        days=list(args.days),
        output_dir=output_dir,
        metrics_total=metrics_total,
        metrics_by_product=metrics_by_product,
    )

    # Save a compact results CSV for later inspection.
    results_df = equity_df.copy()
    results_df["pnl_total"] = results_df["pnl_total"].astype(float)
    results_out_path = output_dir / f"backtest_{args.model}_results_{'_'.join(str(d) for d in args.days)}.csv"
    results_df.to_csv(results_out_path, index=False)

    fills_out_path = output_dir / f"backtest_{args.model}_fills_{'_'.join(str(d) for d in args.days)}.csv"
    fills_df.to_csv(fills_out_path, index=False)

    print(f"\nSaved plots to: {output_dir}")
    print(f"Saved results CSV: {results_out_path}")
    print(f"Saved fills CSV: {fills_out_path}")


if __name__ == "__main__":
    main()

