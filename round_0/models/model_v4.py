from __future__ import annotations

import json
import math
import statistics
from typing import Dict, List, Optional, Tuple

try:
    from datamodel import OrderDepth, TradingState, Order, Trade
except ImportError:  # pragma: no cover - fallback when executed from repo root
    from round_0.models.datamodel import OrderDepth, TradingState, Order, Trade


# =============================================================================
# model_v4 — builds on model_v3 with four targeted improvements derived from
# empirical analysis of the round-0 TOMATOES LOB:
#
#   1. L2 EXTREME STATE DETECTION (Idea 1)
#      L2 volumes are bimodal: normally 15-25 on both sides; in ~7% of ticks
#      one side drops to 5-10 while the other stays large. This "extreme" state
#      predicts the next 3-tick direction with 93-99% accuracy and a ~3.3-tick
#      average move. Detected as a separate binary signal rather than blended
#      into the continuous imbalance term.
#
#   2. FULL ADVERSE QUOTE CANCELLATION on L2 extreme (Idea 2)
#      When L2 is extreme, the passive quote on the side about to be picked off
#      is completely eliminated (not just scaled down 40% as in v3's toxicity
#      filter). Avoids adverse selection on the ~460 ticks/day where the signal
#      fires with near-certainty.
#
#   3. LAG-1 RETURN CORRECTION (Idea 3)
#      Empirical lag-1 autocorrelation of mid returns = -0.43 (stable across
#      both days). After a tick move of size R, the EMA-based fair is adjusted
#      by -BETA * R to anticipate partial mean reversion. Beta is set
#      conservatively at 0.32 to avoid over-fitting.
#
#   4. L2-DIRECTIONAL SIZING IN WIDE SPREAD (Idea 4)
#      When L2 is extreme and the visible spread is wide (>=13), passive sizes
#      are tilted toward the predicted direction. The prior code only ran
#      directional sizing in the compressed-spread regime (<=10).
#
#   5. EMA OF RETURNS as supplementary continuation signal (Idea 5)
#      A fast EMA of the signed mid-price return provides a dense tick-level
#      momentum signal to complement the sparse market-trade flow. Used only
#      as a soft modifier on the continuation adjustment.
#
# EMERALDS: unchanged from v3.
# =============================================================================


class Trader:
    # =========================
    # Feature flags
    # =========================
    USE_EMERALDS_AGGRESSIVE = True
    USE_EMERALDS_PASSIVE = True
    USE_EMERALDS_INVENTORY_SKEW = True
    USE_EMERALDS_SIZE_SKEW = True

    USE_TOMATOES_EMA = True
    USE_TOMATOES_EMA_FAST_SLOW = True
    USE_TOMATOES_MID_BLEND = True
    USE_TOMATOES_IMBALANCE = True
    USE_TOMATOES_INVENTORY_SKEW = True
    USE_TOMATOES_VOL_SPREAD = True
    USE_TOMATOES_PASSIVE = True
    USE_TOMATOES_AGGRESSIVE = True
    USE_TOMATOES_L2_MICRO = True
    USE_TOMATOES_REGIME_OVERLAY = True
    USE_TOMATOES_DIRECTIONAL_QUOTES = True
    USE_TOMATOES_COMPRESSED_TAKE_FILTER = True

    # v4 feature flags
    # Ablation results (backtest, both days):
    #   L2 extreme (Ideas 1+2):           -64  → off  (signal exists but fill rate too low)
    #   Lag-1 passive-only (Idea 3):      +52  → ON   (small passive placement improvement)
    #   Wide directional (Idea 4):          0  → off  (neutral, adds complexity for nothing)
    #   Return EMA (Idea 5):              -22  → off  (marginal noise on continuation signal)
    USE_TOMATOES_L2_EXTREME = False      # Idea 1+2: binary L2 extreme detection + cancellation
    USE_TOMATOES_LAG1_CORRECTION = True  # Idea 3: lag-1 passive-only correction (the only winner)
    USE_TOMATOES_WIDE_DIRECTIONAL = False # Idea 4: directional sizing in wide spread
    USE_TOMATOES_RETURN_EMA = False      # Idea 5: EMA of returns signal

    # =========================
    # Product configuration
    # =========================
    POSITION_LIMITS = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    # =========================
    # EMERALDS parameters (unchanged from v3)
    # =========================
    EMERALDS_FAIR = 10000
    EMERALDS_TAKE_EDGE = 0
    EMERALDS_MARGINAL_TAKE_TOLERANCE = 0.25
    EMERALDS_FAIR_REPAIR_MIN_POSITION = 4
    EMERALDS_FAIR_UNWIND_SAME_PRICE_VOLUME = 18
    EMERALDS_DEFAULT_QUOTE_OFFSET = 1
    EMERALDS_INVENTORY_SKEW_TICKS = 1.5
    EMERALDS_MAX_PASSIVE_SIZE = 20
    EMERALDS_SIZE_PRESSURE = 1.15

    # =========================
    # TOMATOES parameters (inherited from v3)
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
    TOMATOES_MAX_PASSIVE_SIZE = 12
    TOMATOES_TAKE_EXTRA_EDGE = 0
    TOMATOES_AGGRESSIVE_CAP = 16

    TOMATOES_SOFT_POSITION_LIMIT = 60
    TOMATOES_HARD_POSITION_LIMIT = 72
    TOMATOES_PASSIVE_REDUCTION_STEP = 4

    TOMATOES_L2_LEVEL_WEIGHT = 0.65
    TOMATOES_L1_IMBALANCE_BETA = 1.15
    TOMATOES_L2_IMBALANCE_BETA = 3.10
    TOMATOES_MICROPRICE_BETA = 0.90

    TOMATOES_FLOW_HISTORY_WINDOW = 8
    TOMATOES_FLOW_CONFIRM_SCALE = 12.0
    TOMATOES_CONTINUATION_IMBALANCE = 0.18
    TOMATOES_CONTINUATION_STRONG_IMBALANCE = 0.24
    TOMATOES_CONTINUATION_BONUS = 0.85

    TOMATOES_STRETCH_WINDOW = 20
    TOMATOES_STRETCH_Z_THRESHOLD = 1.40
    TOMATOES_STRETCH_STD_FLOOR = 1.50
    TOMATOES_REVERSION_L2_CONFIRM_MAX = 0.10
    TOMATOES_REVERSION_BONUS = 0.70

    TOMATOES_COMPRESSED_SPREAD_LOW = 8
    TOMATOES_COMPRESSED_SPREAD_HIGH = 10
    TOMATOES_DIRECTIONAL_SIGNAL = 1.35
    TOMATOES_STRONG_SIGNAL = 2.05
    TOMATOES_DIRECTIONAL_STEP_IN = 1
    TOMATOES_OPPOSITE_WIDEN_TICKS = 1
    TOMATOES_DIRECTIONAL_SIZE_BONUS = 2
    TOMATOES_DIRECTIONAL_OPPOSITE_SIZE_SCALE = 0.45
    TOMATOES_TOXIC_OPPOSITE_SIZE_SCALE = 0.60
    TOMATOES_COMPRESSED_TAKE_EDGE_ADD = 1
    TOMATOES_COMPRESSED_TAKE_CAP = 10

    # =========================
    # v4 new parameters
    # =========================
    # Idea 1+2: L2 extreme state
    # A side is "small" when its volume is <= this threshold.
    # The other side must be >= LARGE to confirm the extreme state.
    TOMATOES_L2_SMALL_VOLUME = 12
    TOMATOES_L2_LARGE_VOLUME = 14
    # Ratio of large/small required to call it "extreme"
    TOMATOES_L2_EXTREME_RATIO = 2.0

    # Idea 3: lag-1 autocorrelation correction (passive-only).
    # Applied only to passive quote reservation, NOT to fair_with_micro, so it
    # never lowers the aggressive threshold. That avoids triggering harmful
    # aggressive crosses of the wide 13-tick spread.
    # Empirical lag-1 autocorr ≈ -0.43; using 0.22 conservatively.
    TOMATOES_LAG1_BETA = 0.22

    # Idea 4: wide-spread directional sizing when L2 is extreme
    TOMATOES_WIDE_SPREAD_THRESHOLD = 12   # spread >= this → "wide"
    TOMATOES_WIDE_DIR_SIZE_BONUS = 3      # extra units on favoured side
    TOMATOES_WIDE_DIR_OPPOSITE_SCALE = 0.35  # scale on adverse side

    # Idea 5: EMA of returns
    TOMATOES_RETURN_EMA_ALPHA = 0.45      # fast decay (~1-tick half-life)
    TOMATOES_RETURN_EMA_SCALE = 0.20      # contribution to continuation signal

    # =========================
    # Generic helpers
    # =========================
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

    @staticmethod
    def clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def sign(value: float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    @staticmethod
    def top_levels(order_depth: OrderDepth, side: str, depth: int = 2) -> List[Tuple[int, int]]:
        if side == "buy":
            return [(price, volume) for price, volume in sorted(order_depth.buy_orders.items(), reverse=True)[:depth] if volume > 0]
        return [(price, -volume) for price, volume in sorted(order_depth.sell_orders.items())[:depth] if -volume > 0]

    def get_limit(self, product: str) -> int:
        return self.POSITION_LIMITS.get(product, 20)

    def capacities(self, product: str, position: int) -> Tuple[int, int]:
        limit = self.get_limit(product)
        return max(0, limit - position), max(0, limit + position)

    # =========================
    # State persistence
    # =========================
    def load_state(self, trader_data: str) -> Dict:
        default = {
            "ema": None, "ema_fast": None, "ema_slow": None,
            "mids": [], "flows": [],
            "ema_return": None,  # v4: Idea 5
            "last_mid": None,    # v4: Idea 3 (lag-1 return)
        }
        if not trader_data:
            return {"TOMATOES": default}
        try:
            state = json.loads(trader_data)
            t = state.setdefault("TOMATOES", {})
            for k in ("ema", "ema_fast", "ema_slow"):
                t.setdefault(k, None)
            t.setdefault("mids", [])
            t.setdefault("flows", [])
            t.setdefault("ema_return", None)
            t.setdefault("last_mid", None)
            return state
        except Exception:
            return {"TOMATOES": default}

    @staticmethod
    def dump_state(state: Dict) -> str:
        return json.dumps(state, separators=(",", ":"))

    # =========================
    # EMERALDS helpers / strategy (unchanged from v3)
    # =========================
    def emeralds_reservation_price(self, position: int) -> float:
        if not self.USE_EMERALDS_INVENTORY_SKEW:
            return float(self.EMERALDS_FAIR)
        limit = self.get_limit("EMERALDS")
        inventory_ratio = position / limit if limit > 0 else 0.0
        inventory_ratio = self.clamp(inventory_ratio, -1.0, 1.0)
        return self.EMERALDS_FAIR - self.EMERALDS_INVENTORY_SKEW_TICKS * inventory_ratio

    def should_take_emeralds_at_fair(
        self,
        side: str,
        price: int,
        position: int,
        best_bid: Optional[int],
        best_bid_volume: Optional[int],
        best_ask: Optional[int],
        best_ask_volume: Optional[int],
    ) -> bool:
        if price != self.EMERALDS_FAIR:
            return False

        if side == "BUY":
            if position >= 0:
                return False
            strong_inventory_repair = abs(position) >= self.EMERALDS_FAIR_REPAIR_MIN_POSITION
            strong_same_price_unwind = (
                best_bid == self.EMERALDS_FAIR
                and best_bid_volume is not None
                and best_bid_volume >= self.EMERALDS_FAIR_UNWIND_SAME_PRICE_VOLUME
            )
            return strong_inventory_repair or strong_same_price_unwind

        if position <= 0:
            return False
        strong_inventory_repair = abs(position) >= self.EMERALDS_FAIR_REPAIR_MIN_POSITION
        strong_same_price_unwind = (
            best_ask == self.EMERALDS_FAIR
            and best_ask_volume is not None
            and best_ask_volume >= self.EMERALDS_FAIR_UNWIND_SAME_PRICE_VOLUME
        )
        return strong_inventory_repair or strong_same_price_unwind

    @staticmethod
    def emeralds_fair_repair_quantity(side: str, position: int) -> int:
        if side == "BUY" and position < 0:
            return abs(position)
        if side == "SELL" and position > 0:
            return abs(position)
        return 0

    def emeralds_passive_sizes(self, position: int, buy_capacity: int, sell_capacity: int) -> Tuple[int, int]:
        passive_buy_size = min(self.EMERALDS_MAX_PASSIVE_SIZE, buy_capacity)
        passive_sell_size = min(self.EMERALDS_MAX_PASSIVE_SIZE, sell_capacity)

        if not self.USE_EMERALDS_SIZE_SKEW:
            return passive_buy_size, passive_sell_size

        limit = self.get_limit("EMERALDS")
        long_pressure = max(0.0, position / limit) if limit > 0 else 0.0
        short_pressure = max(0.0, -position / limit) if limit > 0 else 0.0

        buy_scale = self.clamp(1.0 - self.EMERALDS_SIZE_PRESSURE * long_pressure, 0.0, 1.0)
        sell_scale = self.clamp(1.0 - self.EMERALDS_SIZE_PRESSURE * short_pressure, 0.0, 1.0)

        passive_buy_size = min(passive_buy_size, int(round(self.EMERALDS_MAX_PASSIVE_SIZE * buy_scale)))
        passive_sell_size = min(passive_sell_size, int(round(self.EMERALDS_MAX_PASSIVE_SIZE * sell_scale)))
        return max(0, passive_buy_size), max(0, passive_sell_size)

    def trade_emeralds(self, product: str, order_depth: OrderDepth, position: int) -> List[Order]:
        orders: List[Order] = []
        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        buy_capacity, sell_capacity = self.capacities(product, position)
        projected_position = position

        # 1) Aggressive taking
        if self.USE_EMERALDS_AGGRESSIVE:
            if order_depth.sell_orders and buy_capacity > 0:
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]
                    reservation_price = self.emeralds_reservation_price(projected_position)
                    edge = reservation_price - ask_price - self.EMERALDS_TAKE_EDGE
                    if edge > 0:
                        qty = min(ask_volume, buy_capacity)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                        projected_position += qty
                        continue
                    if (
                        edge >= -self.EMERALDS_MARGINAL_TAKE_TOLERANCE
                        and self.should_take_emeralds_at_fair(
                            "BUY", ask_price, projected_position,
                            best_bid, best_bid_volume, best_ask, best_ask_volume,
                        )
                        and buy_capacity > 0
                    ):
                        fair_repair_limit = self.emeralds_fair_repair_quantity("BUY", projected_position)
                        qty = min(ask_volume, buy_capacity, fair_repair_limit)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                        projected_position += qty
                        continue
                    break

            if order_depth.buy_orders and sell_capacity > 0:
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]
                    reservation_price = self.emeralds_reservation_price(projected_position)
                    edge = bid_price - reservation_price - self.EMERALDS_TAKE_EDGE
                    if edge > 0:
                        qty = min(bid_volume, sell_capacity)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                        projected_position -= qty
                        continue
                    if (
                        edge >= -self.EMERALDS_MARGINAL_TAKE_TOLERANCE
                        and self.should_take_emeralds_at_fair(
                            "SELL", bid_price, projected_position,
                            best_bid, best_bid_volume, best_ask, best_ask_volume,
                        )
                        and sell_capacity > 0
                    ):
                        fair_repair_limit = self.emeralds_fair_repair_quantity("SELL", projected_position)
                        qty = min(bid_volume, sell_capacity, fair_repair_limit)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                        projected_position -= qty
                        continue
                    break

        # 2) Passive quotes
        reservation_price = self.emeralds_reservation_price(projected_position)
        desired_bid = math.floor(reservation_price - self.EMERALDS_DEFAULT_QUOTE_OFFSET)
        desired_ask = math.ceil(reservation_price + self.EMERALDS_DEFAULT_QUOTE_OFFSET)

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
            passive_bid = math.floor(reservation_price - 1)
            passive_ask = math.ceil(reservation_price + 1)

        if self.USE_EMERALDS_PASSIVE:
            passive_buy_size, passive_sell_size = self.emeralds_passive_sizes(projected_position, buy_capacity, sell_capacity)
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
    ) -> Tuple[Optional[float], Optional[float], Optional[float], List[float], Optional[float], Optional[float]]:
        ema = product_state.get("ema")
        ema_fast = product_state.get("ema_fast")
        ema_slow = product_state.get("ema_slow")
        mids = list(product_state.get("mids", []))
        ema_return = product_state.get("ema_return")  # v4: Idea 5
        last_mid = product_state.get("last_mid")      # v4: Idea 3

        if mid is not None:
            # Lag-1 return for Idea 3 and Idea 5
            current_return = (mid - last_mid) if last_mid is not None else 0.0

            ema = mid if ema is None else self.TOMATOES_EMA_ALPHA * mid + (1.0 - self.TOMATOES_EMA_ALPHA) * ema
            ema_fast = mid if ema_fast is None else self.TOMATOES_EMA_FAST_ALPHA * mid + (1.0 - self.TOMATOES_EMA_FAST_ALPHA) * ema_fast
            ema_slow = mid if ema_slow is None else self.TOMATOES_EMA_SLOW_ALPHA * mid + (1.0 - self.TOMATOES_EMA_SLOW_ALPHA) * ema_slow

            # Idea 5: EMA of returns
            if self.USE_TOMATOES_RETURN_EMA:
                ema_return = (
                    current_return if ema_return is None
                    else self.TOMATOES_RETURN_EMA_ALPHA * current_return + (1.0 - self.TOMATOES_RETURN_EMA_ALPHA) * ema_return
                )

            mids.append(mid)
            if len(mids) > self.TOMATOES_HISTORY_WINDOW:
                mids = mids[-self.TOMATOES_HISTORY_WINDOW:]

            product_state["ema"] = ema
            product_state["ema_fast"] = ema_fast
            product_state["ema_slow"] = ema_slow
            product_state["mids"] = mids
            product_state["ema_return"] = ema_return
            product_state["last_mid"] = mid

        return ema, ema_fast, ema_slow, mids, ema_return, last_mid

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
            weight_sum = sum(w for w, _ in usable)
            if weight_sum <= 0:
                return mid if mid is not None else ema
            return sum(w * v for w, v in usable) / weight_sum
        if self.USE_TOMATOES_EMA:
            return ema if ema is not None else mid
        return mid if mid is not None else ema

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

        r_floor = math.floor(reservation)
        r_ceil = math.ceil(reservation)
        if passive_bid >= r_floor:
            passive_bid = r_floor - 1
        if passive_ask <= r_ceil:
            passive_ask = r_ceil + 1
        if passive_bid >= passive_ask:
            passive_bid = r_floor - 1
            passive_ask = r_ceil + 1
            if passive_bid >= passive_ask:
                passive_bid = passive_ask - 1

        return passive_bid, passive_ask

    def tomatoes_hard_capacities(self, product: str, position: int) -> Tuple[int, int]:
        buy_capacity, sell_capacity = self.capacities(product, position)
        hard_limit = min(self.get_limit(product), self.TOMATOES_HARD_POSITION_LIMIT)
        buy_hard_capacity = min(buy_capacity, max(0, hard_limit - position))
        sell_hard_capacity = min(sell_capacity, max(0, hard_limit + position))
        return buy_hard_capacity, sell_hard_capacity

    def tomatoes_soft_pressure(self, position: int) -> float:
        soft_limit = max(1, min(self.get_limit("TOMATOES"), self.TOMATOES_SOFT_POSITION_LIMIT))
        hard_limit = max(soft_limit + 1, min(self.get_limit("TOMATOES"), self.TOMATOES_HARD_POSITION_LIMIT))
        if abs(position) <= soft_limit:
            return 0.0
        return self.clamp((abs(position) - soft_limit) / (hard_limit - soft_limit), 0.0, 1.0)

    def tomatoes_passive_sizes(self, position: int, buy_capacity: int, sell_capacity: int, vol: float) -> Tuple[int, int]:
        base_passive_size = max(1, self.TOMATOES_MAX_PASSIVE_SIZE - int(round(vol)))
        passive_buy_size = min(base_passive_size, buy_capacity)
        passive_sell_size = min(base_passive_size, sell_capacity)

        if self.USE_TOMATOES_INVENTORY_SKEW:
            if position > 0:
                pressure_units = int(position // self.TOMATOES_PASSIVE_REDUCTION_STEP)
                passive_buy_size = max(0, passive_buy_size - pressure_units)
                passive_sell_size = min(sell_capacity, passive_sell_size + pressure_units)
            elif position < 0:
                pressure_units = int((-position) // self.TOMATOES_PASSIVE_REDUCTION_STEP)
                passive_sell_size = max(0, passive_sell_size - pressure_units)
                passive_buy_size = min(buy_capacity, passive_buy_size + pressure_units)

        soft_pressure = self.tomatoes_soft_pressure(position)
        if position >= self.TOMATOES_SOFT_POSITION_LIMIT:
            passive_buy_size = int(math.floor(passive_buy_size * (1.0 - soft_pressure)))
        elif position <= -self.TOMATOES_SOFT_POSITION_LIMIT:
            passive_sell_size = int(math.floor(passive_sell_size * (1.0 - soft_pressure)))

        return passive_buy_size, passive_sell_size

    def tomatoes_depth_features(
        self,
        order_depth: OrderDepth,
        mid: Optional[float],
        best_bid_volume: Optional[int],
        best_ask_volume: Optional[int],
    ) -> Tuple[float, float, float]:
        l1_imbalance = self.imbalance(best_bid_volume, best_ask_volume)
        if not self.USE_TOMATOES_L2_MICRO or mid is None:
            return l1_imbalance, l1_imbalance, 0.0

        bid_levels = self.top_levels(order_depth, "buy", depth=2)
        ask_levels = self.top_levels(order_depth, "sell", depth=2)
        weights = (1.0, self.TOMATOES_L2_LEVEL_WEIGHT)

        weighted_bid_volume = 0.0
        weighted_ask_volume = 0.0
        weighted_price_sum = 0.0
        weighted_volume_sum = 0.0

        for weight, level in zip(weights, bid_levels):
            price, volume = level
            weighted_bid_volume += weight * volume
            weighted_price_sum += weight * price * volume
            weighted_volume_sum += weight * volume

        for weight, level in zip(weights, ask_levels):
            price, volume = level
            weighted_ask_volume += weight * volume
            weighted_price_sum += weight * price * volume
            weighted_volume_sum += weight * volume

        denom = weighted_bid_volume + weighted_ask_volume
        l2_imbalance = (weighted_bid_volume - weighted_ask_volume) / denom if denom > 0 else l1_imbalance
        microprice = weighted_price_sum / weighted_volume_sum if weighted_volume_sum > 0 else mid
        micro_shift = microprice - mid
        return l1_imbalance, l2_imbalance, micro_shift

    def detect_l2_extreme(
        self,
        order_depth: OrderDepth,
    ) -> Tuple[bool, int]:
        """Idea 1: Detect the bimodal L2 extreme state.

        Returns (is_extreme, direction) where direction is +1 (price going up),
        -1 (price going down), or 0 (no extreme signal).

        The extreme state occurs when one side has a "small" L2 volume (5-10)
        and the other has a "large" L2 volume (15-25). Empirically this predicts
        the next 3-tick move with 93-99% accuracy.
        """
        if not self.USE_TOMATOES_L2_EXTREME:
            return False, 0

        bid_levels = self.top_levels(order_depth, "buy", depth=2)
        ask_levels = self.top_levels(order_depth, "sell", depth=2)

        if len(bid_levels) < 2 or len(ask_levels) < 2:
            return False, 0

        bv2 = bid_levels[1][1]  # L2 bid volume
        av2 = ask_levels[1][1]  # L2 ask volume

        if bv2 <= 0 or av2 <= 0:
            return False, 0

        small_thresh = self.TOMATOES_L2_SMALL_VOLUME
        large_thresh = self.TOMATOES_L2_LARGE_VOLUME
        ratio_thresh = self.TOMATOES_L2_EXTREME_RATIO

        bid_small = bv2 <= small_thresh
        ask_small = av2 <= small_thresh
        bid_large = bv2 >= large_thresh
        ask_large = av2 >= large_thresh

        # Extreme buy: bid side large, ask side small → price going UP
        if bid_large and ask_small and bv2 >= av2 * ratio_thresh:
            return True, +1

        # Extreme sell: ask side large, bid side small → price going DOWN
        if ask_large and bid_small and av2 >= bv2 * ratio_thresh:
            return True, -1

        return False, 0

    def tomatoes_signed_trade_flow(
        self,
        trades: List[Trade],
        best_bid: Optional[int],
        best_ask: Optional[int],
        mid: Optional[float],
    ) -> int:
        signed_flow = 0
        for trade in trades:
            qty = int(trade.quantity)
            if best_ask is not None and trade.price >= best_ask:
                signed_flow += qty
            elif best_bid is not None and trade.price <= best_bid:
                signed_flow -= qty
            elif mid is not None:
                if trade.price > mid:
                    signed_flow += qty
                elif trade.price < mid:
                    signed_flow -= qty
        return signed_flow

    def update_tomatoes_flow_state(self, product_state: Dict, current_flow: int) -> List[int]:
        flows = list(product_state.get("flows", []))
        flows.append(int(current_flow))
        if len(flows) > self.TOMATOES_FLOW_HISTORY_WINDOW:
            flows = flows[-self.TOMATOES_FLOW_HISTORY_WINDOW:]
        product_state["flows"] = flows
        return flows

    def tomatoes_continuation_adjustment(
        self,
        l2_imbalance: float,
        flow_recent: float,
        ema_fast: Optional[float],
        ema_slow: Optional[float],
        ema_return: Optional[float],  # v4: Idea 5
    ) -> float:
        if not self.USE_TOMATOES_REGIME_OVERLAY:
            return 0.0
        if abs(l2_imbalance) < self.TOMATOES_CONTINUATION_IMBALANCE:
            return 0.0

        ema_gap = (ema_fast - ema_slow) if ema_fast is not None and ema_slow is not None else 0.0

        # Idea 5: supplement flow with EMA of returns
        return_signal = 0.0
        if self.USE_TOMATOES_RETURN_EMA and ema_return is not None:
            return_signal = self.clamp(ema_return * self.TOMATOES_RETURN_EMA_SCALE, -1.0, 1.0)

        effective_flow = flow_recent + return_signal
        aligned_flow = effective_flow * l2_imbalance > 0.02
        aligned_trend = ema_gap * l2_imbalance > 0.0 and abs(l2_imbalance) >= self.TOMATOES_CONTINUATION_STRONG_IMBALANCE
        if not (aligned_flow or aligned_trend):
            return 0.0

        strength = self.clamp(abs(l2_imbalance) / 0.35 + 0.35 * abs(effective_flow), 0.0, 1.0)
        return self.sign(l2_imbalance) * self.TOMATOES_CONTINUATION_BONUS * strength

    def tomatoes_reversion_adjustment(
        self,
        mid: Optional[float],
        mids: List[float],
        l2_imbalance: float,
    ) -> float:
        if not self.USE_TOMATOES_REGIME_OVERLAY or mid is None:
            return 0.0
        if len(mids) < max(8, self.TOMATOES_STRETCH_WINDOW // 2):
            return 0.0

        window = mids[-min(len(mids), self.TOMATOES_STRETCH_WINDOW):]
        mean_mid = statistics.mean(window)
        std_mid = max(statistics.pstdev(window), self.TOMATOES_STRETCH_STD_FLOOR)
        stretch_z = (mid - mean_mid) / std_mid

        if abs(stretch_z) < self.TOMATOES_STRETCH_Z_THRESHOLD:
            return 0.0
        if abs(l2_imbalance) > self.TOMATOES_REVERSION_L2_CONFIRM_MAX and self.sign(stretch_z) == self.sign(l2_imbalance):
            return 0.0

        strength = self.clamp((abs(stretch_z) - self.TOMATOES_STRETCH_Z_THRESHOLD) / 1.25 + 0.40, 0.0, 1.0)
        return -self.sign(stretch_z) * self.TOMATOES_REVERSION_BONUS * strength

    def tomatoes_signal_confirmed(
        self,
        signal_ticks: float,
        l2_imbalance: float,
        micro_shift: float,
        continuation_adj: float,
    ) -> bool:
        return (
            abs(signal_ticks) >= self.TOMATOES_STRONG_SIGNAL
            and (
                abs(l2_imbalance) >= self.TOMATOES_CONTINUATION_IMBALANCE
                or abs(micro_shift) >= 0.25
                or abs(continuation_adj) >= 0.45
            )
        )

    def adjust_tomatoes_directional_quotes(
        self,
        passive_bid: int,
        passive_ask: int,
        passive_buy_size: int,
        passive_sell_size: int,
        best_bid: Optional[int],
        best_ask: Optional[int],
        visible_spread: Optional[int],
        signal_ticks: float,
        l2_imbalance: float,
        micro_shift: float,
        continuation_adj: float,
        buy_capacity: int,
        sell_capacity: int,
        buy_hard_capacity: int,
        sell_hard_capacity: int,
        l2_extreme: bool,       # v4: Idea 1+2+4
        l2_extreme_dir: int,    # v4: Idea 1+2+4
    ) -> Tuple[int, int, int, int]:
        direction = self.sign(signal_ticks)

        # ------------------------------------------------------------------ #
        # Idea 2: FULL adverse-side cancellation when L2 is in extreme state.
        # 93-99% accuracy means being passively filled on the wrong side is
        # almost always a losing trade — completely suspend that quote.
        # ------------------------------------------------------------------ #
        if self.USE_TOMATOES_L2_EXTREME and l2_extreme:
            if l2_extreme_dir > 0:
                # Price going UP → never want to be filled selling passively
                passive_sell_size = 0
            elif l2_extreme_dir < 0:
                # Price going DOWN → never want to be filled buying passively
                passive_buy_size = 0
        else:
            # v3 toxicity filter (kept when L2 extreme not triggered)
            if abs(continuation_adj) >= 0.40 and abs(l2_imbalance) >= self.TOMATOES_CONTINUATION_IMBALANCE:
                if continuation_adj > 0:
                    passive_sell_size = int(math.floor(passive_sell_size * self.TOMATOES_TOXIC_OPPOSITE_SIZE_SCALE))
                elif continuation_adj < 0:
                    passive_buy_size = int(math.floor(passive_buy_size * self.TOMATOES_TOXIC_OPPOSITE_SIZE_SCALE))

        # ------------------------------------------------------------------ #
        # Idea 4: directional sizing in WIDE spread when L2 is extreme.
        # The prior logic only ran in compressed spread (<=10). L2 extreme
        # occurs uniformly across both spread regimes.
        # ------------------------------------------------------------------ #
        if (
            self.USE_TOMATOES_WIDE_DIRECTIONAL
            and l2_extreme
            and visible_spread is not None
            and visible_spread >= self.TOMATOES_WIDE_SPREAD_THRESHOLD
        ):
            if l2_extreme_dir > 0:
                passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + self.TOMATOES_WIDE_DIR_SIZE_BONUS)
                passive_sell_size = int(math.floor(passive_sell_size * self.TOMATOES_WIDE_DIR_OPPOSITE_SCALE))
            elif l2_extreme_dir < 0:
                passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + self.TOMATOES_WIDE_DIR_SIZE_BONUS)
                passive_buy_size = int(math.floor(passive_buy_size * self.TOMATOES_WIDE_DIR_OPPOSITE_SCALE))

        # ------------------------------------------------------------------ #
        # Compressed-spread directional quote logic (unchanged from v3).
        # ------------------------------------------------------------------ #
        compressed = (
            self.USE_TOMATOES_DIRECTIONAL_QUOTES
            and visible_spread is not None
            and self.TOMATOES_COMPRESSED_SPREAD_LOW <= visible_spread <= self.TOMATOES_COMPRESSED_SPREAD_HIGH
            and abs(signal_ticks) >= self.TOMATOES_DIRECTIONAL_SIGNAL
            and (abs(l2_imbalance) >= 0.12 or abs(micro_shift) >= 0.18 or abs(continuation_adj) >= 0.30)
        )
        if compressed:
            if direction > 0:
                if best_bid is not None and best_ask is not None:
                    target_bid = min(best_ask - 1, best_bid + 1 + self.TOMATOES_DIRECTIONAL_STEP_IN)
                    passive_bid = max(passive_bid, target_bid)
                elif best_bid is not None:
                    passive_bid = max(passive_bid, best_bid + 1)
                passive_ask += self.TOMATOES_OPPOSITE_WIDEN_TICKS
                passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + self.TOMATOES_DIRECTIONAL_SIZE_BONUS)
                passive_sell_size = int(math.floor(passive_sell_size * self.TOMATOES_DIRECTIONAL_OPPOSITE_SIZE_SCALE))
            elif direction < 0:
                if best_bid is not None and best_ask is not None:
                    target_ask = max(best_bid + 1, best_ask - 1 - self.TOMATOES_DIRECTIONAL_STEP_IN)
                    passive_ask = min(passive_ask, target_ask)
                elif best_ask is not None:
                    passive_ask = min(passive_ask, best_ask - 1)
                passive_bid -= self.TOMATOES_OPPOSITE_WIDEN_TICKS
                passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + self.TOMATOES_DIRECTIONAL_SIZE_BONUS)
                passive_buy_size = int(math.floor(passive_buy_size * self.TOMATOES_DIRECTIONAL_OPPOSITE_SIZE_SCALE))

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)
        if passive_bid >= passive_ask:
            passive_bid = passive_ask - 1

        return passive_bid, passive_ask, max(0, passive_buy_size), max(0, passive_sell_size)

    # =========================
    # TOMATOES strategy
    # =========================
    def trade_tomatoes(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        state_store: Dict,
        market_trades: List[Trade],
    ) -> List[Order]:
        orders: List[Order] = []

        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        mid = self.compute_mid(best_bid, best_ask)
        visible_spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None

        product_state = state_store.setdefault(
            "TOMATOES",
            {"ema": None, "ema_fast": None, "ema_slow": None, "mids": [], "flows": [],
             "ema_return": None, "last_mid": None},
        )

        ema, ema_fast, ema_slow, mids, ema_return, last_mid = self.update_tomatoes_state(product_state, mid)
        fair_base = self.build_tomatoes_fair_base(mid, ema, ema_fast, ema_slow)
        if fair_base is None:
            return orders

        vol = self.realized_volatility(mids)
        l1_imbalance, l2_imbalance, micro_shift = self.tomatoes_depth_features(
            order_depth, mid, best_bid_volume, best_ask_volume,
        )

        # Idea 1: detect L2 extreme binary state
        l2_extreme, l2_extreme_dir = self.detect_l2_extreme(order_depth)

        current_flow = self.tomatoes_signed_trade_flow(market_trades, best_bid, best_ask, mid)
        flows = self.update_tomatoes_flow_state(product_state, current_flow)
        flow_recent = self.clamp(sum(flows[-3:]) / self.TOMATOES_FLOW_CONFIRM_SCALE, -1.0, 1.0) if flows else 0.0

        l1_adj = self.TOMATOES_L1_IMBALANCE_BETA * l1_imbalance if self.USE_TOMATOES_IMBALANCE else 0.0
        l2_adj = self.TOMATOES_L2_IMBALANCE_BETA * l2_imbalance if self.USE_TOMATOES_L2_MICRO else 0.0
        micro_adj = self.TOMATOES_MICROPRICE_BETA * micro_shift if self.USE_TOMATOES_L2_MICRO else 0.0
        continuation_adj = self.tomatoes_continuation_adjustment(
            l2_imbalance, flow_recent, ema_fast, ema_slow, ema_return,
        )
        reversion_adj = self.tomatoes_reversion_adjustment(mid, mids, l2_imbalance)

        fair_with_micro = fair_base + l1_adj + l2_adj + micro_adj + continuation_adj + reversion_adj

        # Idea 3: lag-1 passive-only bias.
        # Computed here but applied ONLY to passive quote placement — never to
        # fair_with_micro — so the aggressive take threshold is unaffected and
        # the model does NOT cross the wide spread on a mean-reversion hunch.
        lag1_passive_bias = 0.0
        if self.USE_TOMATOES_LAG1_CORRECTION and last_mid is not None and mid is not None:
            last_return = mid - last_mid
            lag1_passive_bias = -self.TOMATOES_LAG1_BETA * last_return

        if self.USE_TOMATOES_VOL_SPREAD:
            half_spread = max(
                self.TOMATOES_MIN_HALF_SPREAD,
                int(round(self.TOMATOES_BASE_HALF_SPREAD + self.TOMATOES_VOL_MULTIPLIER * vol)),
            )
        else:
            half_spread = max(self.TOMATOES_MIN_HALF_SPREAD, self.TOMATOES_BASE_HALF_SPREAD)

        buy_capacity, sell_capacity = self.capacities(product, position)
        buy_hard_capacity, sell_hard_capacity = self.tomatoes_hard_capacities(product, position)
        projected_position = position

        inv_adj = self.TOMATOES_INVENTORY_SKEW * position if self.USE_TOMATOES_INVENTORY_SKEW else 0.0
        reservation_price = fair_with_micro - inv_adj
        signal_ticks = reservation_price - mid if mid is not None else reservation_price - fair_base

        take_edge = max(1, self.TOMATOES_TAKE_EXTRA_EDGE)
        if self.USE_TOMATOES_VOL_SPREAD:
            take_edge = max(take_edge, self.TOMATOES_TAKE_EXTRA_EDGE + int(round(0.5 * vol)))
        aggressive_cap = self.TOMATOES_AGGRESSIVE_CAP

        if (
            self.USE_TOMATOES_COMPRESSED_TAKE_FILTER
            and visible_spread is not None
            and self.TOMATOES_COMPRESSED_SPREAD_LOW <= visible_spread <= self.TOMATOES_COMPRESSED_SPREAD_HIGH
            and not self.tomatoes_signal_confirmed(signal_ticks, l2_imbalance, micro_shift, continuation_adj)
        ):
            take_edge += self.TOMATOES_COMPRESSED_TAKE_EDGE_ADD
            aggressive_cap = min(aggressive_cap, self.TOMATOES_COMPRESSED_TAKE_CAP)

        aggressive_buy_threshold = math.floor(reservation_price - take_edge)
        aggressive_sell_threshold = math.ceil(reservation_price + take_edge)

        # 1) Aggressive taking
        if self.USE_TOMATOES_AGGRESSIVE:
            if order_depth.sell_orders and buy_capacity > 0 and buy_hard_capacity > 0:
                remaining_take = min(buy_capacity, buy_hard_capacity, aggressive_cap)
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]
                    if remaining_take <= 0:
                        break
                    if ask_price <= aggressive_buy_threshold:
                        qty = min(ask_volume, remaining_take)
                        self.add_order(orders, product, ask_price, qty)
                        buy_capacity -= qty
                        buy_hard_capacity -= qty
                        remaining_take -= qty
                        projected_position += qty
                    else:
                        break

            if order_depth.buy_orders and sell_capacity > 0 and sell_hard_capacity > 0:
                remaining_take = min(sell_capacity, sell_hard_capacity, aggressive_cap)
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]
                    if remaining_take <= 0:
                        break
                    if bid_price >= aggressive_sell_threshold:
                        qty = min(bid_volume, remaining_take)
                        self.add_order(orders, product, bid_price, -qty)
                        sell_capacity -= qty
                        sell_hard_capacity -= qty
                        remaining_take -= qty
                        projected_position -= qty
                    else:
                        break

        # 2) Passive quotes
        reservation_price = fair_with_micro - (
            self.TOMATOES_INVENTORY_SKEW * projected_position if self.USE_TOMATOES_INVENTORY_SKEW else 0.0
        )
        # Idea 3 applied here only: passive reservation includes the lag-1 bias.
        # Clamp to ±1 tick so it never radically relocates the quote.
        passive_reservation = reservation_price + self.clamp(lag1_passive_bias, -1.0, 1.0)
        signal_ticks = reservation_price - mid if mid is not None else reservation_price - fair_base
        buy_hard_capacity, sell_hard_capacity = self.tomatoes_hard_capacities(product, projected_position)
        buy_hard_capacity = min(buy_capacity, buy_hard_capacity)
        sell_hard_capacity = min(sell_capacity, sell_hard_capacity)

        desired_bid = math.floor(passive_reservation - half_spread)
        desired_ask = math.ceil(passive_reservation + half_spread)
        passive_bid, passive_ask = self.clamp_passive_quotes(
            passive_reservation, best_bid, best_ask, desired_bid, desired_ask,
        )

        if self.USE_TOMATOES_PASSIVE:
            passive_buy_size, passive_sell_size = self.tomatoes_passive_sizes(
                projected_position, buy_capacity, sell_capacity, vol,
            )
            passive_buy_size = min(passive_buy_size, buy_hard_capacity)
            passive_sell_size = min(passive_sell_size, sell_hard_capacity)

            passive_bid, passive_ask, passive_buy_size, passive_sell_size = self.adjust_tomatoes_directional_quotes(
                passive_bid, passive_ask, passive_buy_size, passive_sell_size,
                best_bid, best_ask, visible_spread,
                signal_ticks, l2_imbalance, micro_shift, continuation_adj,
                buy_capacity, sell_capacity, buy_hard_capacity, sell_hard_capacity,
                l2_extreme, l2_extreme_dir,
            )

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
                result[product] = self.trade_tomatoes(
                    product, order_depth, position, state_store,
                    state.market_trades.get(product, []),
                )
            else:
                result[product] = []

        trader_data = self.dump_state(state_store)
        conversions = 0
        return result, conversions, trader_data
