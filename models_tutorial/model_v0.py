from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple
import json
import math
import statistics


class Trader:
    # =========================
    # Feature flags (all ON by default)
    # =========================
    # EMERALDS layers
    USE_EMERALDS_AGGRESSIVE = True
    USE_EMERALDS_PASSIVE = True
    USE_EMERALDS_INVENTORY_SKEW = False
    USE_EMERALDS_SIZE_SKEW = False
    USE_EMERALDS_FLATTENING = False
    USE_EMERALDS_AGGRESSIVE_FLATTENING = False

    # TOMATOES layers
    USE_TOMATOES_EMA = True
    USE_TOMATOES_IMBALANCE = True
    USE_TOMATOES_INVENTORY_SKEW = True
    USE_TOMATOES_VOL_SPREAD = True
    USE_TOMATOES_PASSIVE = True
    USE_TOMATOES_AGGRESSIVE = True

    # =========================
    # Product configuration
    # =========================
    POSITION_LIMITS = {
        "EMERALDS": 80,
        "TOMATOES": 80,   # change this if the round uses a different limit
    }

    # =========================
    # EMERALDS parameters
    # =========================
    EMERALDS_FAIR = 10000
    EMERALDS_TAKE_EDGE = 1
    EMERALDS_DEFAULT_QUOTE_OFFSET = 1
    EMERALDS_INVENTORY_SKEW = 0.5
    EMERALDS_MAX_PASSIVE_SIZE = 6
    EMERALDS_FLATTEN_THRESHOLD = 30
    EMERALDS_FLATTEN_SIZE = 15

    # =========================
    # TOMATOES parameters
    # =========================
    TOMATOES_EMA_ALPHA = 0.22
    TOMATOES_HISTORY_WINDOW = 30

    TOMATOES_IMBALANCE_BETA = 2.0     # imbalance adjustment in ticks
    TOMATOES_INVENTORY_SKEW = 0.45    # reservation-price shift by inventory
    TOMATOES_BASE_HALF_SPREAD = 2     # minimum quoting width
    TOMATOES_VOL_MULTIPLIER = 1.3     # wider quotes when realized vol rises
    TOMATOES_MIN_HALF_SPREAD = 2
    TOMATOES_MAX_PASSIVE_SIZE = 5
    TOMATOES_TAKE_EXTRA_EDGE = 1       # require extra edge before crossing the spread

    # =========================
    # Generic helpers
    # =========================
    def bid(self):
        # Only used in Round 2; ignored otherwise
        return 15

    @staticmethod
    def add_order(orders: List[Order], product: str, price: int, quantity: int) -> None:
        if quantity != 0:
            orders.append(Order(product, int(price), int(quantity)))

    @staticmethod
    def best_levels(order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        best_bid_volume = order_depth.buy_orders[best_bid] if best_bid is not None else None
        best_ask_volume = -order_depth.sell_orders[best_ask] if best_ask is not None else None

        return best_bid, best_bid_volume, best_ask, best_ask_volume

    @staticmethod
    def compute_mid(best_bid: Optional[int], best_ask: Optional[int]) -> Optional[float]:
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2.0
        if best_bid is not None:
            return float(best_bid)
        if best_ask is not None:
            return float(best_ask)
        return None

    @staticmethod
    def realized_volatility(mids: List[float]) -> float:
        if len(mids) < 3:
            return 0.0
        diffs = [mids[i] - mids[i - 1] for i in range(1, len(mids))]
        if len(diffs) < 2:
            return 0.0
        return statistics.pstdev(diffs)

    @staticmethod
    def imbalance(best_bid_volume: Optional[int], best_ask_volume: Optional[int]) -> float:
        if best_bid_volume is None or best_ask_volume is None:
            return 0.0
        denom = best_bid_volume + best_ask_volume
        if denom <= 0:
            return 0.0
        return (best_bid_volume - best_ask_volume) / denom

    def get_limit(self, product: str) -> int:
        return self.POSITION_LIMITS.get(product, 20)

    def capacities(self, product: str, position: int) -> Tuple[int, int]:
        limit = self.get_limit(product)
        buy_capacity = limit - position
        sell_capacity = limit + position
        return max(0, buy_capacity), max(0, sell_capacity)

    def apply_flattening(
        self,
        orders: List[Order],
        product: str,
        position: int,
        buy_capacity: int,
        sell_capacity: int,
    ) -> Tuple[int, int, Optional[str]]:
        """
        Add optional inventory-flattening order at the fixed EMERALDS fair and
        return updated capacities.
        flatten_side:
          - "LONG"  -> flattening sell was placed
          - "SHORT" -> flattening buy was placed
          - None    -> no flattening order
        """
        if not self.USE_EMERALDS_FLATTENING:
            return buy_capacity, sell_capacity, None

        if position >= self.EMERALDS_FLATTEN_THRESHOLD and sell_capacity > 0:
            qty = min(self.EMERALDS_FLATTEN_SIZE, position, sell_capacity)
            self.add_order(orders, product, self.EMERALDS_FAIR, -qty)
            sell_capacity -= qty
            return buy_capacity, sell_capacity, "LONG"

        if position <= -self.EMERALDS_FLATTEN_THRESHOLD and buy_capacity > 0:
            qty = min(self.EMERALDS_FLATTEN_SIZE, -position, buy_capacity)
            self.add_order(orders, product, self.EMERALDS_FAIR, qty)
            buy_capacity -= qty
            return buy_capacity, sell_capacity, "SHORT"

        return buy_capacity, sell_capacity, None

    # =========================
    # State persistence
    # =========================
    def load_state(self, trader_data: str) -> Dict:
        if not trader_data:
            return {"TOMATOES": {"ema": None, "mids": []}}
        try:
            state = json.loads(trader_data)
            if "TOMATOES" not in state:
                state["TOMATOES"] = {"ema": None, "mids": []}
            if "ema" not in state["TOMATOES"]:
                state["TOMATOES"]["ema"] = None
            if "mids" not in state["TOMATOES"]:
                state["TOMATOES"]["mids"] = []
            return state
        except Exception:
            return {"TOMATOES": {"ema": None, "mids": []}}

    @staticmethod
    def dump_state(state: Dict) -> str:
        return json.dumps(state, separators=(",", ":"))

    # =========================
    # EMERALDS strategy
    # =========================
    def trade_emeralds(self, product: str, order_depth: OrderDepth, position: int) -> List[Order]:
        orders: List[Order] = []

        best_bid, _best_bid_volume, best_ask, _best_ask_volume = self.best_levels(order_depth)
        buy_capacity, sell_capacity = self.capacities(product, position)

        # Fixed fair with optional inventory skew
        inv_skew = self.EMERALDS_INVENTORY_SKEW * position if self.USE_EMERALDS_INVENTORY_SKEW else 0.0
        skewed_fair = self.EMERALDS_FAIR - int(round(inv_skew))

        aggressive_buy_threshold = math.floor(skewed_fair - self.EMERALDS_TAKE_EDGE)
        aggressive_sell_threshold = math.ceil(skewed_fair + self.EMERALDS_TAKE_EDGE)

        # 1-2) Optional aggressive liquidity taking
        if self.USE_EMERALDS_AGGRESSIVE:
            if order_depth.sell_orders and buy_capacity > 0:
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]
                    if ask_price <= aggressive_buy_threshold and buy_capacity > 0:
                        qty = min(ask_volume, buy_capacity)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                    else:
                        break

            if order_depth.buy_orders and sell_capacity > 0:
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]
                    if bid_price >= aggressive_sell_threshold and sell_capacity > 0:
                        qty = min(bid_volume, sell_capacity)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                    else:
                        break

        quote_offset = self.EMERALDS_DEFAULT_QUOTE_OFFSET

        if best_bid is not None:
            passive_bid = min(best_bid + 1, skewed_fair - quote_offset)
        else:
            passive_bid = skewed_fair - quote_offset

        if best_ask is not None:
            passive_ask = max(best_ask - 1, skewed_fair + quote_offset)
        else:
            passive_ask = skewed_fair + quote_offset

        if passive_bid >= passive_ask:
            passive_bid = skewed_fair - 1
            passive_ask = skewed_fair + 1

        flatten_side: Optional[str] = None
        if self.USE_EMERALDS_FLATTENING and self.USE_EMERALDS_AGGRESSIVE_FLATTENING:
            buy_capacity, sell_capacity, flatten_side = self.apply_flattening(
                orders,
                product,
                position,
                buy_capacity,
                sell_capacity,
            )

        if self.USE_EMERALDS_PASSIVE:
            passive_buy_size = min(self.EMERALDS_MAX_PASSIVE_SIZE, buy_capacity)
            passive_sell_size = min(self.EMERALDS_MAX_PASSIVE_SIZE, sell_capacity)

            # Optional size skew by inventory
            if self.USE_EMERALDS_SIZE_SKEW:
                if position > 0:
                    passive_buy_size = max(0, passive_buy_size - position // 4)
                    passive_sell_size = min(sell_capacity, passive_sell_size + position // 4)
                elif position < 0:
                    passive_sell_size = max(0, passive_sell_size - (-position) // 4)
                    passive_buy_size = min(buy_capacity, passive_buy_size + (-position) // 4)

            allow_passive_bid = not (flatten_side == "LONG")
            allow_passive_ask = not (flatten_side == "SHORT")

            if allow_passive_bid and passive_buy_size > 0:
                self.add_order(orders, product, passive_bid, passive_buy_size)
                buy_capacity -= passive_buy_size
            if allow_passive_ask and passive_sell_size > 0:
                self.add_order(orders, product, passive_ask, -passive_sell_size)
                sell_capacity -= passive_sell_size

        if self.USE_EMERALDS_FLATTENING and not self.USE_EMERALDS_AGGRESSIVE_FLATTENING:
            buy_capacity, sell_capacity, _ = self.apply_flattening(
                orders,
                product,
                position,
                buy_capacity,
                sell_capacity,
            )

        return orders

    # =========================
    # TOMATOES strategy
    # =========================
    def trade_tomatoes(self, product: str, order_depth: OrderDepth, position: int, state_store: Dict) -> List[Order]:
        orders: List[Order] = []

        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        mid = self.compute_mid(best_bid, best_ask)

        product_state = state_store.setdefault("TOMATOES", {"ema": None, "mids": []})

        # Update EMA/history state store
        if mid is not None:
            prev_ema = product_state.get("ema")
            if prev_ema is None:
                ema = mid
            else:
                ema = self.TOMATOES_EMA_ALPHA * mid + (1.0 - self.TOMATOES_EMA_ALPHA) * prev_ema
            product_state["ema"] = ema

            mids = product_state.get("mids", [])
            mids.append(mid)
            mids = mids[-self.TOMATOES_HISTORY_WINDOW:]
            product_state["mids"] = mids
        else:
            ema = product_state.get("ema")
            mids = product_state.get("mids", [])

        # Fair base: EMA or raw mid depending on flag
        if self.USE_TOMATOES_EMA:
            fair_base = ema
        else:
            fair_base = mid if mid is not None else ema

        # If we still have no fair estimate, do nothing
        if fair_base is None:
            return orders

        vol = self.realized_volatility(mids)
        imb = self.imbalance(best_bid_volume, best_ask_volume) if self.USE_TOMATOES_IMBALANCE else 0.0

        # Moving fair value:
        # filtered fair + book-pressure adjustment
        fair = fair_base + self.TOMATOES_IMBALANCE_BETA * imb

        # Reservation price shifts with inventory
        inv_shift = self.TOMATOES_INVENTORY_SKEW * position if self.USE_TOMATOES_INVENTORY_SKEW else 0.0
        reservation = fair - inv_shift

        buy_capacity, sell_capacity = self.capacities(product, position)

        # Dynamic quoting width
        if self.USE_TOMATOES_VOL_SPREAD:
            half_spread = max(
                self.TOMATOES_MIN_HALF_SPREAD,
                int(round(self.TOMATOES_BASE_HALF_SPREAD + self.TOMATOES_VOL_MULTIPLIER * vol))
            )
            take_edge = max(1, self.TOMATOES_TAKE_EXTRA_EDGE + int(round(0.5 * vol)))
        else:
            half_spread = max(self.TOMATOES_MIN_HALF_SPREAD, self.TOMATOES_BASE_HALF_SPREAD)
            take_edge = max(1, self.TOMATOES_TAKE_EXTRA_EDGE)

        # Require more edge when crossing aggressively (vol-adjusted if enabled)

        aggressive_buy_threshold = math.floor(reservation - take_edge)
        aggressive_sell_threshold = math.ceil(reservation + take_edge)

        # 1-2) Optional aggressive trading
        if self.USE_TOMATOES_AGGRESSIVE:
            if order_depth.sell_orders and buy_capacity > 0:
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]
                    if ask_price <= aggressive_buy_threshold and buy_capacity > 0:
                        qty = min(ask_volume, buy_capacity)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                    else:
                        break

            if order_depth.buy_orders and sell_capacity > 0:
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]
                    if bid_price >= aggressive_sell_threshold and sell_capacity > 0:
                        qty = min(bid_volume, sell_capacity)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                    else:
                        break

        # 3) Passive market making around reservation price
        desired_bid = math.floor(reservation - half_spread)
        desired_ask = math.ceil(reservation + half_spread)

        if best_bid is not None:
            passive_bid = min(desired_bid, best_bid + 1)
        else:
            passive_bid = desired_bid

        if best_ask is not None:
            passive_ask = max(desired_ask, best_ask - 1)
        else:
            passive_ask = desired_ask

        # Avoid crossing the current market
        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)

        if passive_bid >= passive_ask:
            passive_bid = math.floor(reservation - 1)
            passive_ask = math.ceil(reservation + 1)
            if passive_bid >= passive_ask:
                passive_bid = passive_ask - 1

        if self.USE_TOMATOES_PASSIVE:
            # Passive sizes shrink when vol rises only if vol-spread flag is enabled.
            if self.USE_TOMATOES_VOL_SPREAD:
                base_passive_size = max(1, self.TOMATOES_MAX_PASSIVE_SIZE - int(round(vol)))
            else:
                base_passive_size = self.TOMATOES_MAX_PASSIVE_SIZE

            passive_buy_size = min(base_passive_size, buy_capacity)
            passive_sell_size = min(base_passive_size, sell_capacity)

            # Inventory-aware size skew controlled by inventory-skew flag.
            if self.USE_TOMATOES_INVENTORY_SKEW:
                if position > 0:
                    passive_buy_size = max(0, passive_buy_size - position // 4)
                    passive_sell_size = min(sell_capacity, passive_sell_size + position // 4)
                elif position < 0:
                    passive_sell_size = max(0, passive_sell_size - (-position) // 4)
                    passive_buy_size = min(buy_capacity, passive_buy_size + (-position) // 4)

            if passive_buy_size > 0:
                self.add_order(orders, product, passive_bid, passive_buy_size)

            if passive_sell_size > 0:
                self.add_order(orders, product, passive_ask, -passive_sell_size)

        return orders

    # =========================
    # Main run
    # =========================
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        state_store = self.load_state(state.traderData)

        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)

            if product == "EMERALDS":
                result[product] = self.trade_emeralds(product, order_depth, position)

            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(product, order_depth, position, state_store)

            else:
                result[product] = []

        trader_data = self.dump_state(state_store)
        conversions = 0
        return result, conversions, trader_data


# ------------------------------------------------------------
# Flag usage guide (quick):
# - Keep all flags True for baseline behavior (current strategy).
# - Disable one flag at a time to isolate impact in backtests.
# - Example: turn off USE_TOMATOES_IMBALANCE to compare fair-value
#   with vs without order-book pressure adjustment.
# - EMERALDS flattening options mirror `emerald_only`:
#   USE_EMERALDS_FLATTENING = True
#   USE_EMERALDS_AGGRESSIVE_FLATTENING = True / False
# ------------------------------------------------------------
