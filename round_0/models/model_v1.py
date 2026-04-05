from __future__ import annotations

import json
import math
import statistics
from typing import Dict, List, Optional, Tuple

try:
    from datamodel import OrderDepth, TradingState, Order
except ImportError:  # pragma: no cover - fallback when executed from repo root
    from models_tutorial.datamodel import OrderDepth, TradingState, Order


class Trader:
    # =========================
    # Feature flags (all ON by default)
    # =========================
    # EMERALDS layers
    USE_EMERALDS_AGGRESSIVE = True
    USE_EMERALDS_PASSIVE = True
    USE_EMERALDS_INVENTORY_SKEW = False
    USE_EMERALDS_SIZE_SKEW = False

    # TOMATOES layers
    USE_TOMATOES_EMA = True  # legacy fallback: keep single-EMA behavior when fast/slow mode is off
    USE_TOMATOES_EMA_FAST_SLOW = True
    USE_TOMATOES_MID_BLEND = True
    USE_TOMATOES_IMBALANCE = True
    USE_TOMATOES_INVENTORY_SKEW = True
    USE_TOMATOES_VOL_SPREAD = True
    USE_TOMATOES_VISIBLE_SPREAD_ADJUST = False
    USE_TOMATOES_REGIME_ADAPTATION = False
    USE_TOMATOES_PASSIVE = True
    USE_TOMATOES_AGGRESSIVE = True

    # =========================
    # Product configuration
    # =========================
    POSITION_LIMITS = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    # =========================
    # EMERALDS parameters
    # =========================
    EMERALDS_FAIR = 10000
    EMERALDS_TAKE_EDGE = 1
    EMERALDS_DEFAULT_QUOTE_OFFSET = 1
    EMERALDS_INVENTORY_SKEW = 0.5
    EMERALDS_MAX_PASSIVE_SIZE = 6

    # =========================
    # TOMATOES parameters
    # =========================
    TOMATOES_EMA_ALPHA = 0.22
    TOMATOES_EMA_FAST_ALPHA = 0.32
    TOMATOES_EMA_SLOW_ALPHA = 0.10
    TOMATOES_FAST_WEIGHT = 0.55
    TOMATOES_SLOW_WEIGHT = 0.35
    TOMATOES_MID_WEIGHT = 0.10
    TOMATOES_HISTORY_WINDOW = 30

    TOMATOES_IMBALANCE_BETA = 2.0
    TOMATOES_INVENTORY_SKEW = 0.45
    TOMATOES_BASE_HALF_SPREAD = 2
    TOMATOES_VOL_MULTIPLIER = 1.3
    TOMATOES_MIN_HALF_SPREAD = 2
    TOMATOES_MAX_PASSIVE_SIZE = 5
    TOMATOES_TAKE_EXTRA_EDGE = 0

    TOMATOES_CALM_VOL_THRESHOLD = 0.45
    TOMATOES_VOLATILE_VOL_THRESHOLD = 1.60
    TOMATOES_CALM_GAP_THRESHOLD = 0.35
    TOMATOES_DIRECTIONAL_GAP_THRESHOLD = 0.90
    TOMATOES_WIDE_BOOK_EXTRA = 3

    TOMATOES_REGIME_HALF_SPREAD_ADJUST = {
        "calm": -1,
        "normal": 0,
        "directional": 0,
        "volatile": 1,
    }
    TOMATOES_REGIME_SIZE_MULTIPLIER = {
        "calm": 1.20,
        "normal": 1.00,
        "directional": 0.80,
        "volatile": 0.65,
    }
    TOMATOES_REGIME_TAKE_EDGE_ADJUST = {
        "calm": 0,
        "normal": 0,
        "directional": 1,
        "volatile": 2,
    }
    TOMATOES_REGIME_AGGRESSIVE_CAP = {
        "calm": 6,
        "normal": 5,
        "directional": 3,
        "volatile": 2,
    }

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

    # =========================
    # State persistence
    # =========================
    def load_state(self, trader_data: str) -> Dict:
        default_tomatoes_state = {
            "ema": None,       # legacy single EMA fallback
            "ema_fast": None,
            "ema_slow": None,
            "mids": [],
        }
        if not trader_data:
            return {"TOMATOES": default_tomatoes_state}

        try:
            state = json.loads(trader_data)
            tomatoes = state.setdefault("TOMATOES", {})
            tomatoes.setdefault("ema", None)
            tomatoes.setdefault("ema_fast", None)
            tomatoes.setdefault("ema_slow", None)
            tomatoes.setdefault("mids", [])
            return state
        except Exception:
            return {"TOMATOES": default_tomatoes_state}

    @staticmethod
    def dump_state(state: Dict) -> str:
        return json.dumps(state, separators=(",", ":"))

    # =========================
    # EMERALDS strategy
    # =========================
    def trade_emeralds(self, product: str, order_depth: OrderDepth, position: int) -> List[Order]:
        orders: List[Order] = []

        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        buy_capacity, sell_capacity = self.capacities(product, position)

        # Fixed fair with optional inventory skew
        inv_skew = self.EMERALDS_INVENTORY_SKEW * position if self.USE_EMERALDS_INVENTORY_SKEW else 0.0
        skewed_fair = self.EMERALDS_FAIR - inv_skew

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

        # 3) Passive quotes around skewed fair
        desired_bid = math.floor(skewed_fair - self.EMERALDS_DEFAULT_QUOTE_OFFSET)
        desired_ask = math.ceil(skewed_fair + self.EMERALDS_DEFAULT_QUOTE_OFFSET)

        if best_bid is not None:
            passive_bid = min(desired_bid, best_bid + 1)
        else:
            passive_bid = desired_bid

        if best_ask is not None:
            passive_ask = max(desired_ask, best_ask - 1)
        else:
            passive_ask = desired_ask

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)

        if passive_bid >= passive_ask:
            passive_bid = math.floor(skewed_fair - 1)
            passive_ask = math.ceil(skewed_fair + 1)

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

            if passive_buy_size > 0:
                self.add_order(orders, product, passive_bid, passive_buy_size)
            if passive_sell_size > 0:
                self.add_order(orders, product, passive_ask, -passive_sell_size)

        return orders

    # =========================
    # TOMATOES helpers
    # =========================
    def update_tomatoes_state(
        self,
        product_state: Dict,
        mid: Optional[float],
    ) -> Tuple[Optional[float], Optional[float], Optional[float], List[float]]:
        ema = product_state.get("ema")
        ema_fast = product_state.get("ema_fast")
        ema_slow = product_state.get("ema_slow")
        mids = list(product_state.get("mids", []))

        if mid is not None:
            if ema is None:
                ema = mid
            else:
                ema = self.TOMATOES_EMA_ALPHA * mid + (1.0 - self.TOMATOES_EMA_ALPHA) * ema

            if ema_fast is None:
                ema_fast = mid
            else:
                ema_fast = self.TOMATOES_EMA_FAST_ALPHA * mid + (1.0 - self.TOMATOES_EMA_FAST_ALPHA) * ema_fast

            if ema_slow is None:
                ema_slow = mid
            else:
                ema_slow = self.TOMATOES_EMA_SLOW_ALPHA * mid + (1.0 - self.TOMATOES_EMA_SLOW_ALPHA) * ema_slow

            mids.append(mid)
            if len(mids) > self.TOMATOES_HISTORY_WINDOW:
                mids = mids[-self.TOMATOES_HISTORY_WINDOW:]

            product_state["ema"] = ema
            product_state["ema_fast"] = ema_fast
            product_state["ema_slow"] = ema_slow
            product_state["mids"] = mids

        return ema, ema_fast, ema_slow, mids

    def build_tomatoes_fair_base(
        self,
        mid: Optional[float],
        ema: Optional[float],
        ema_fast: Optional[float],
        ema_slow: Optional[float],
    ) -> Optional[float]:
        if self.USE_TOMATOES_EMA_FAST_SLOW:
            usable = []
            if ema_fast is not None:
                usable.append((self.TOMATOES_FAST_WEIGHT, ema_fast))
            if ema_slow is not None:
                usable.append((self.TOMATOES_SLOW_WEIGHT, ema_slow))

            if not usable:
                return mid if mid is not None else ema

            if self.USE_TOMATOES_MID_BLEND and mid is not None:
                usable.append((self.TOMATOES_MID_WEIGHT, mid))

            weight_sum = sum(weight for weight, _ in usable)
            if weight_sum <= 0:
                return mid if mid is not None else ema

            return sum(weight * value for weight, value in usable) / weight_sum

        if self.USE_TOMATOES_EMA:
            return ema if ema is not None else mid

        return mid if mid is not None else ema

    def detect_tomatoes_regime(
        self,
        vol: float,
        visible_spread: Optional[int],
        base_half_spread: int,
        ema_fast: Optional[float],
        ema_slow: Optional[float],
        mids: List[float],
    ) -> str:
        ema_gap = abs(ema_fast - ema_slow) if ema_fast is not None and ema_slow is not None else 0.0

        slope = 0.0
        if len(mids) >= 4:
            slope = mids[-1] - mids[-4]
        elif len(mids) >= 2:
            slope = mids[-1] - mids[0]

        wide_book = (
            visible_spread is not None
            and visible_spread > 2 * base_half_spread + self.TOMATOES_WIDE_BOOK_EXTRA
        )

        if vol >= self.TOMATOES_VOLATILE_VOL_THRESHOLD or wide_book:
            return "volatile"

        ema_delta = (ema_fast - ema_slow) if ema_fast is not None and ema_slow is not None else 0.0
        if ema_gap >= self.TOMATOES_DIRECTIONAL_GAP_THRESHOLD and slope * ema_delta > 0:
            return "directional"

        if vol <= self.TOMATOES_CALM_VOL_THRESHOLD and ema_gap <= self.TOMATOES_CALM_GAP_THRESHOLD:
            return "calm"

        return "normal"

    def regime_half_spread_adjustment(self, regime: str) -> int:
        if not self.USE_TOMATOES_REGIME_ADAPTATION:
            return 0
        return self.TOMATOES_REGIME_HALF_SPREAD_ADJUST.get(regime, 0)

    def regime_take_edge_adjustment(self, regime: str) -> int:
        if not self.USE_TOMATOES_REGIME_ADAPTATION:
            return 0
        return self.TOMATOES_REGIME_TAKE_EDGE_ADJUST.get(regime, 0)

    def regime_size_multiplier(self, regime: str) -> float:
        if not self.USE_TOMATOES_REGIME_ADAPTATION:
            return 1.0
        return self.TOMATOES_REGIME_SIZE_MULTIPLIER.get(regime, 1.0)

    def regime_aggressive_cap(self, regime: str) -> int:
        if not self.USE_TOMATOES_REGIME_ADAPTATION:
            return 10 ** 9
        return self.TOMATOES_REGIME_AGGRESSIVE_CAP.get(regime, 10 ** 9)

    @staticmethod
    def clamp_passive_quotes(
        reservation: float,
        best_bid: Optional[int],
        best_ask: Optional[int],
        desired_bid: int,
        desired_ask: int,
    ) -> Tuple[int, int]:
        passive_bid = desired_bid
        passive_ask = desired_ask

        if best_bid is not None:
            passive_bid = min(passive_bid, best_bid + 1)
        if best_ask is not None:
            passive_ask = max(passive_ask, best_ask - 1)

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)

        reservation_floor = math.floor(reservation)
        reservation_ceil = math.ceil(reservation)

        if passive_bid >= reservation_floor:
            passive_bid = reservation_floor - 1
        if passive_ask <= reservation_ceil:
            passive_ask = reservation_ceil + 1

        if passive_bid >= passive_ask:
            passive_bid = reservation_floor - 1
            passive_ask = reservation_ceil + 1
            if passive_bid >= passive_ask:
                passive_bid = passive_ask - 1

        return passive_bid, passive_ask

    # =========================
    # TOMATOES strategy
    # =========================
    def trade_tomatoes(self, product: str, order_depth: OrderDepth, position: int, state_store: Dict) -> List[Order]:
        orders: List[Order] = []

        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        mid = self.compute_mid(best_bid, best_ask)
        visible_spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None

        product_state = state_store.setdefault(
            "TOMATOES",
            {
                "ema": None,
                "ema_fast": None,
                "ema_slow": None,
                "mids": [],
            },
        )

        ema, ema_fast, ema_slow, mids = self.update_tomatoes_state(product_state, mid)
        fair_base = self.build_tomatoes_fair_base(mid, ema, ema_fast, ema_slow)

        if fair_base is None:
            return orders

        vol = self.realized_volatility(mids)
        imbalance = self.imbalance(best_bid_volume, best_ask_volume) if self.USE_TOMATOES_IMBALANCE else 0.0

        # Explicit decomposition: fair -> microstructure adjustment -> reservation price -> inventory adjustment.
        fair = fair_base
        imbalance_adjustment = self.TOMATOES_IMBALANCE_BETA * imbalance if self.USE_TOMATOES_IMBALANCE else 0.0
        fair_with_microstructure = fair + imbalance_adjustment

        inventory_adjustment = self.TOMATOES_INVENTORY_SKEW * position if self.USE_TOMATOES_INVENTORY_SKEW else 0.0
        reservation_price = fair_with_microstructure - inventory_adjustment

        buy_capacity, sell_capacity = self.capacities(product, position)

        # Dynamic quoting width.
        if self.USE_TOMATOES_VOL_SPREAD:
            base_half_spread = max(
                self.TOMATOES_MIN_HALF_SPREAD,
                int(round(self.TOMATOES_BASE_HALF_SPREAD + self.TOMATOES_VOL_MULTIPLIER * vol)),
            )
        else:
            base_half_spread = max(self.TOMATOES_MIN_HALF_SPREAD, self.TOMATOES_BASE_HALF_SPREAD)

        half_spread = base_half_spread
        if (
            self.USE_TOMATOES_VISIBLE_SPREAD_ADJUST
            and visible_spread is not None
            and visible_spread > 2 * base_half_spread + self.TOMATOES_WIDE_BOOK_EXTRA
        ):
            half_spread = base_half_spread + 1

        regime = self.detect_tomatoes_regime(
            vol,
            visible_spread,
            base_half_spread,
            ema_fast,
            ema_slow,
            mids,
        )

        if self.USE_TOMATOES_REGIME_ADAPTATION:
            half_spread += self.regime_half_spread_adjustment(regime)
            half_spread = max(self.TOMATOES_MIN_HALF_SPREAD, half_spread)

        # More demanding thresholds when the regime is less favorable.
        take_edge = max(1, self.TOMATOES_TAKE_EXTRA_EDGE)
        if self.USE_TOMATOES_VOL_SPREAD:
            take_edge = max(take_edge, self.TOMATOES_TAKE_EXTRA_EDGE + int(round(0.5 * vol)))
        if self.USE_TOMATOES_REGIME_ADAPTATION:
            take_edge += self.regime_take_edge_adjustment(regime)

        aggressive_buy_threshold = math.floor(reservation_price - take_edge)
        aggressive_sell_threshold = math.ceil(reservation_price + take_edge)

        # 1-2) Optional aggressive trading
        if self.USE_TOMATOES_AGGRESSIVE:
            aggressive_cap = self.regime_aggressive_cap(regime)

            if order_depth.sell_orders and buy_capacity > 0:
                remaining_take = min(buy_capacity, aggressive_cap)
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]
                    if remaining_take <= 0:
                        break
                    if ask_price <= aggressive_buy_threshold:
                        qty = min(ask_volume, remaining_take)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                        remaining_take -= qty
                    else:
                        break

            if order_depth.buy_orders and sell_capacity > 0:
                remaining_take = min(sell_capacity, aggressive_cap)
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]
                    if remaining_take <= 0:
                        break
                    if bid_price >= aggressive_sell_threshold:
                        qty = min(bid_volume, remaining_take)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                        remaining_take -= qty
                    else:
                        break

        # 3) Passive market making around reservation price
        desired_bid = math.floor(reservation_price - half_spread)
        desired_ask = math.ceil(reservation_price + half_spread)
        passive_bid, passive_ask = self.clamp_passive_quotes(
            reservation_price,
            best_bid,
            best_ask,
            desired_bid,
            desired_ask,
        )

        if self.USE_TOMATOES_PASSIVE:
            base_passive_size = self.TOMATOES_MAX_PASSIVE_SIZE
            if self.USE_TOMATOES_VOL_SPREAD:
                base_passive_size = max(1, self.TOMATOES_MAX_PASSIVE_SIZE - int(round(vol)))

            if self.USE_TOMATOES_REGIME_ADAPTATION:
                base_passive_size = max(1, int(round(base_passive_size * self.regime_size_multiplier(regime))))

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
# TOMATOES strategy notes:
# - Default mode is now PnL-first for this dataset:
#   USE_TOMATOES_EMA_FAST_SLOW = True
#   USE_TOMATOES_MID_BLEND = True
#   USE_TOMATOES_VISIBLE_SPREAD_ADJUST = False
#   USE_TOMATOES_REGIME_ADAPTATION = False
#   TOMATOES_TAKE_EXTRA_EDGE = 0
# - Why? The visible spread is structurally wide here, so it should not govern quoting by default.
# - If you want the more prudent / experimental market-making mode, enable:
#   USE_TOMATOES_VISIBLE_SPREAD_ADJUST = True
#   USE_TOMATOES_REGIME_ADAPTATION = True
# - If you want the closest possible behavior to the older single-EMA version, also disable:
#   USE_TOMATOES_EMA_FAST_SLOW = False
#   USE_TOMATOES_MID_BLEND = False
# ------------------------------------------------------------
