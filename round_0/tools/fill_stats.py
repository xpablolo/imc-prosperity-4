#!/usr/bin/env python3
"""
Fill analytics on top of the prosperity3bt historical replay.

Patches the matching engine to tag every fill as maker (crossing the order book)
or taker (matching against an incoming market trade), then prints a breakdown
per product at the end of the run.

Usage:
    python round_0/tools/fill_stats.py <model>           # both days (default)
    python round_0/tools/fill_stats.py <model> 0--2      # single day
    python round_0/tools/fill_stats.py <model> 0--2 0--1 # explicit both days
"""

import sys
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
ROUND_DIR = TOOLS_DIR.parent
PROJECT_ROOT = ROUND_DIR.parent
MODELS_DIR = ROUND_DIR / "models"
DATA_DIR = PROJECT_ROOT / "data" / "round_0"

sys.path.insert(0, str(MODELS_DIR))

from prosperity3bt.file_reader import FileReader
from prosperity3bt import runner
from prosperity3bt.datamodel import Trade
from prosperity3bt.models import MarketTrade, TradeMatchingMode, TradeRow


# ── Custom FileReader: maps round0/ → data/round_0/ ────────────────────────

class Round0Reader(FileReader):
    def __init__(self, root: Path):
        self._root = root  # data/

    @contextmanager
    def file(self, path_parts: list[str]):
        mapped = ["round_0" if p == "round0" else p for p in path_parts]
        path = self._root
        for part in mapped:
            path = path / part
        yield path if path.is_file() else None


# ── Stats accumulator ──────────────────────────────────────────────────────

stats: dict = defaultdict(lambda: {
    "maker_buys": 0,    "maker_sells": 0,
    "taker_buys": 0,    "taker_sells": 0,
    "maker_buy_vol": 0, "maker_sell_vol": 0,
    "taker_buy_vol": 0, "taker_sell_vol": 0,
    "maker_buy_cost": 0,"maker_sell_cost": 0,
    "taker_buy_cost": 0,"taker_sell_cost": 0,
    "steps_with_fills": 0,
    "total_steps": 0,
    "orders_submitted": 0,
    "orders_unfilled": 0,
})


# ── Patched matching functions ─────────────────────────────────────────────

def _tagged_match_buy(state, data, order, market_trades, mode):
    product = order.symbol
    order_depth = state.order_depths[product]
    price_matches = sorted(p for p in order_depth.sell_orders if p <= order.price)
    trades = []
    for price in price_matches:
        volume = min(order.quantity, abs(order_depth.sell_orders[price]))
        trades.append(Trade(order.symbol, price, volume, "SUBMISSION", "", state.timestamp))
        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= price * volume
        order_depth.sell_orders[price] += volume
        if order_depth.sell_orders[price] == 0:
            order_depth.sell_orders.pop(price)
        order.quantity -= volume
        s = stats[product]
        s["maker_buys"] += 1
        s["maker_buy_vol"] += volume
        s["maker_buy_cost"] += price * volume
        if order.quantity == 0:
            return trades
    if mode == TradeMatchingMode.none:
        return trades
    for mt in market_trades:
        if (mt.sell_quantity == 0 or mt.trade.price > order.price or
                (mt.trade.price == order.price and mode == TradeMatchingMode.worse)):
            continue
        volume = min(order.quantity, mt.sell_quantity)
        trades.append(Trade(order.symbol, order.price, volume, "SUBMISSION", mt.trade.seller, state.timestamp))
        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= order.price * volume
        mt.sell_quantity -= volume
        order.quantity -= volume
        s = stats[product]
        s["taker_buys"] += 1
        s["taker_buy_vol"] += volume
        s["taker_buy_cost"] += order.price * volume
        if order.quantity == 0:
            return trades
    return trades


def _tagged_match_sell(state, data, order, market_trades, mode):
    product = order.symbol
    order_depth = state.order_depths[product]
    price_matches = sorted((p for p in order_depth.buy_orders if p >= order.price), reverse=True)
    trades = []
    for price in price_matches:
        volume = min(abs(order.quantity), order_depth.buy_orders[price])
        trades.append(Trade(order.symbol, price, volume, "", "SUBMISSION", state.timestamp))
        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += price * volume
        order_depth.buy_orders[price] -= volume
        if order_depth.buy_orders[price] == 0:
            order_depth.buy_orders.pop(price)
        order.quantity += volume
        s = stats[product]
        s["maker_sells"] += 1
        s["maker_sell_vol"] += volume
        s["maker_sell_cost"] += price * volume
        if order.quantity == 0:
            return trades
    if mode == TradeMatchingMode.none:
        return trades
    for mt in market_trades:
        if (mt.buy_quantity == 0 or mt.trade.price < order.price or
                (mt.trade.price == order.price and mode == TradeMatchingMode.worse)):
            continue
        volume = min(abs(order.quantity), mt.buy_quantity)
        trades.append(Trade(order.symbol, order.price, volume, mt.trade.buyer, "SUBMISSION", state.timestamp))
        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += order.price * volume
        mt.buy_quantity -= volume
        order.quantity += volume
        s = stats[product]
        s["taker_sells"] += 1
        s["taker_sell_vol"] += volume
        s["taker_sell_cost"] += order.price * volume
        if order.quantity == 0:
            return trades
    return trades


def _tagged_match_orders(state, data, orders, result, mode):
    market_trades = {
        product: [MarketTrade(t, t.quantity, t.quantity) for t in trades]
        for product, trades in data.trades[state.timestamp].items()
    }
    for product in data.products:
        s = stats[product]
        s["total_steps"] += 1
        product_orders = orders.get(product, [])
        s["orders_submitted"] += len(product_orders)
        new_trades = []
        for order in product_orders:
            if order.quantity > 0:
                fills = _tagged_match_buy(state, data, order, market_trades.get(product, []), mode)
            elif order.quantity < 0:
                fills = _tagged_match_sell(state, data, order, market_trades.get(product, []), mode)
            else:
                fills = []
            new_trades.extend(fills)
            if abs(order.quantity) > 0:
                s["orders_unfilled"] += 1
        if new_trades:
            state.own_trades[product] = new_trades
            result.trades.extend([TradeRow(trade) for trade in new_trades])
            s["steps_with_fills"] += 1
        else:
            state.own_trades[product] = []
    for product, trades in market_trades.items():
        for trade in trades:
            trade.trade.quantity = min(trade.buy_quantity, trade.sell_quantity)
        remaining = [t.trade for t in trades if t.trade.quantity > 0]
        state.market_trades[product] = remaining
        result.trades.extend([TradeRow(trade) for trade in remaining])


runner.match_buy_order = _tagged_match_buy
runner.match_sell_order = _tagged_match_sell
runner.match_orders = _tagged_match_orders


# ── Report ─────────────────────────────────────────────────────────────────

def print_fill_report() -> None:
    if not stats:
        print("\nNo fills recorded.")
        return
    print("\n" + "=" * 68)
    print("  FILL ANALYTICS")
    print("=" * 68)
    for product in sorted(stats):
        s = stats[product]
        total_steps = s["total_steps"]
        maker_fills = s["maker_buys"] + s["maker_sells"]
        taker_fills = s["taker_buys"] + s["taker_sells"]
        total_fills = maker_fills + taker_fills
        maker_vol = s["maker_buy_vol"] + s["maker_sell_vol"]
        taker_vol = s["taker_buy_vol"] + s["taker_sell_vol"]
        total_vol = maker_vol + taker_vol
        maker_cost = s["maker_buy_cost"] + s["maker_sell_cost"]
        taker_cost = s["taker_buy_cost"] + s["taker_sell_vol"]
        if total_fills == 0:
            print(f"\n  {product}  — no fills")
            continue
        print(f"\n  {product}")
        print(f"  {'─' * 56}")
        pct_m = maker_fills / total_fills * 100
        pct_t = taker_fills / total_fills * 100
        print(f"  Fills:   {total_fills:>6}  │  maker {maker_fills:>5} ({pct_m:5.1f}%)  │  taker {taker_fills:>5} ({pct_t:5.1f}%)")
        if total_vol > 0:
            vpct_m = maker_vol / total_vol * 100
            vpct_t = taker_vol / total_vol * 100
            print(f"  Volume:  {total_vol:>6}  │  maker {maker_vol:>5} ({vpct_m:5.1f}%)  │  taker {taker_vol:>5} ({vpct_t:5.1f}%)")
            avg_all = total_vol / total_fills
            avg_maker = maker_vol / maker_fills if maker_fills else 0
            avg_taker = taker_vol / taker_fills if taker_fills else 0
            print(f"  Avg qty: {avg_all:>6.1f}  │  maker {avg_maker:>5.1f}       │  taker {avg_taker:>5.1f}")
            avg_all_px = (maker_cost + taker_cost) / total_vol
            avg_maker_px = maker_cost / maker_vol if maker_vol else 0
            avg_taker_px = taker_cost / taker_vol if taker_vol else 0
            print(f"  Avg px:  {avg_all_px:>8.1f}│  maker {avg_maker_px:>8.1f}   │  taker {avg_taker_px:>8.1f}")
        print(f"  ┌─ Buys:  maker {s['maker_buys']:>4} ({s['maker_buy_vol']:>5} vol)  │  taker {s['taker_buys']:>4} ({s['taker_buy_vol']:>5} vol)")
        print(f"  └─ Sells: maker {s['maker_sells']:>4} ({s['maker_sell_vol']:>5} vol)  │  taker {s['taker_sells']:>4} ({s['taker_sell_vol']:>5} vol)")
        fill_rate = s["steps_with_fills"] / total_steps * 100 if total_steps else 0
        print(f"  Steps:   {total_steps:>6}  │  with fills {s['steps_with_fills']:>5} ({fill_rate:5.1f}%)")
        submitted = s["orders_submitted"]
        unfilled = s["orders_unfilled"]
        fully_filled = submitted - unfilled
        fill_pct = fully_filled / submitted * 100 if submitted else 0
        print(f"  Orders:  {submitted:>6} submitted  │  {fully_filled:>5} fully filled ({fill_pct:5.1f}%)")
    print("\n" + "=" * 68)


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    model_name = args[0]
    model_path = MODELS_DIR / f"{model_name}.py"
    if not model_path.exists():
        available = sorted(p.stem for p in MODELS_DIR.glob("*.py") if p.stem != "datamodel")
        print(f"Model '{model_name}' not found. Available: {', '.join(available)}")
        sys.exit(1)

    remaining = args[1:]
    day_args = [a for a in remaining if not a.startswith("-") and ("--" in a or a.lstrip("-").isdigit())]
    if not day_args:
        day_args = ["0--2", "0--1"]

    reader = Round0Reader(DATA_DIR.parent)

    import importlib.util
    spec = importlib.util.spec_from_file_location("trader_module", model_path)
    trader_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trader_module)

    from prosperity3bt.runner import run_backtest
    from prosperity3bt.data import has_day_data

    for arg in day_args:
        if "--" in arg:
            round_str, day_str = arg.split("--", 1)
            round_num, day_num = int(round_str), int(f"-{day_str}")
            days = [(round_num, day_num)]
        else:
            round_num = int(arg)
            days = [(round_num, d) for d in range(-5, 10) if has_day_data(reader, round_num, d)]

        for rn, dn in days:
            print(f"Backtesting {model_name} on round {rn} day {dn}")
            run_backtest(
                trader_module.Trader(),
                reader,
                rn,
                dn,
                print_output=False,
                trade_matching_mode=TradeMatchingMode.all,
                no_names=True,
                show_progress_bar=True,
            )

    print_fill_report()


if __name__ == "__main__":
    main()
