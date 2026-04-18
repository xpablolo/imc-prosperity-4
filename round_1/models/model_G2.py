from __future__ import annotations

import json
import math
import statistics
from typing import Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, Trade, TradingState


# ═══════════════════════════════════════════════════════════════════════════════
# ASH_COATED_OSMIUM — stationary market maker
# ═══════════════════════════════════════════════════════════════════════════════

class _AshTrader:
    """
    Market maker for ASH_COATED_OSMIUM.
    Stationary / mean-reverting around ~10_000 with slow anchor adaptation.
    """

    PRODUCT = "ASH_COATED_OSMIUM"
    POSITION_LIMIT = 80

    BASE_FAIR = 10_000.0
    USE_SLOW_ANCHOR = True
    ANCHOR_ALPHA = 0.03
    ANCHOR_CLIP_TICKS = 6.0

    TAKE_EDGE = 0.0
    MARGINAL_TAKE_TOLERANCE = 0.40
    FAIR_REPAIR_MIN_POSITION = 6
    FAIR_UNWIND_SAME_PRICE_VOLUME = 20

    DEFAULT_QUOTE_OFFSET = 1
    INVENTORY_SKEW_TICKS = 3.5
    MAX_PASSIVE_SIZE = 20
    SIZE_PRESSURE = 1.20

    # Microstructure overlay (new in v4)
    L2_LEVEL_WEIGHT = 0.65
    L1_IMBALANCE_BETA = 0.45
    L2_IMBALANCE_BETA = 0.95
    MICROPRICE_BETA = 0.30
    SIGNAL_CLIP_TICKS = 1.60

    DIRECTIONAL_SIGNAL = 1.20
    STRONG_DIRECTIONAL_SIGNAL = 2.20
    DIRECTIONAL_STEP_IN = 1
    OPPOSITE_WIDEN_TICKS = 1
    DIRECTIONAL_SIZE_BONUS = 2
    DIRECTIONAL_OPPOSITE_SIZE_SCALE = 0.78
    TOXIC_OPPOSITE_SIZE_SCALE = 0.82

    @staticmethod
    def add_order(orders: List[Order], product: str, price: int, quantity: int) -> None:
        if quantity != 0:
            orders.append(Order(product, int(price), int(quantity)))

    @staticmethod
    def best_levels(
        order_depth: OrderDepth,
    ) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        best_bid_volume = order_depth.buy_orders[best_bid] if best_bid is not None else None
        best_ask_volume = -order_depth.sell_orders[best_ask] if best_ask is not None else None
        return best_bid, best_bid_volume, best_ask, best_ask_volume

    @staticmethod
    def top_levels(order_depth: OrderDepth, side: str, depth: int = 2) -> List[Tuple[int, int]]:
        if side == "buy":
            return [
                (price, volume)
                for price, volume in sorted(order_depth.buy_orders.items(), reverse=True)[:depth]
                if volume > 0
            ]
        return [
            (price, -volume)
            for price, volume in sorted(order_depth.sell_orders.items())[:depth]
            if -volume > 0
        ]

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
    def clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def imbalance(best_bid_volume: Optional[int], best_ask_volume: Optional[int]) -> float:
        if best_bid_volume is None or best_ask_volume is None:
            return 0.0
        denom = best_bid_volume + best_ask_volume
        if denom <= 0:
            return 0.0
        return (best_bid_volume - best_ask_volume) / denom

    def capacities(self, position: int) -> Tuple[int, int]:
        return max(0, self.POSITION_LIMIT - position), max(0, self.POSITION_LIMIT + position)

    def update_anchor(self, product_state: Dict, mid: Optional[float]) -> float:
        anchor = product_state.get("anchor")
        if anchor is None:
            anchor = self.BASE_FAIR

        if self.USE_SLOW_ANCHOR and mid is not None:
            # Adaptive alpha: fast warmup for first ~20 ticks, then settles to ANCHOR_ALPHA.
            tick = int(product_state.get("tick", 0))
            alpha = max(self.ANCHOR_ALPHA, min(0.25, 3.0 / (tick + 1))) if tick < 20 else self.ANCHOR_ALPHA
            anchor = alpha * mid + (1.0 - alpha) * float(anchor)

        tick = int(product_state.get("tick", 0))
        product_state["tick"] = tick + 1

        clipped_anchor = self.clamp(
            float(anchor),
            self.BASE_FAIR - self.ANCHOR_CLIP_TICKS,
            self.BASE_FAIR + self.ANCHOR_CLIP_TICKS,
        )
        product_state["anchor"] = clipped_anchor
        return clipped_anchor

    def reservation_price(self, anchor_fair: float, position: int) -> float:
        inventory_ratio = self.clamp(position / self.POSITION_LIMIT, -1.0, 1.0)
        return anchor_fair - self.INVENTORY_SKEW_TICKS * inventory_ratio

    def depth_features(
        self,
        order_depth: OrderDepth,
        mid: Optional[float],
        best_bid_volume: Optional[int],
        best_ask_volume: Optional[int],
    ) -> Tuple[float, float, float]:
        l1_imbalance = self.imbalance(best_bid_volume, best_ask_volume)
        if mid is None:
            return l1_imbalance, l1_imbalance, 0.0

        bid_levels = self.top_levels(order_depth, "buy", depth=2)
        ask_levels = self.top_levels(order_depth, "sell", depth=2)
        weights = (1.0, self.L2_LEVEL_WEIGHT)

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

    def alpha_shift(
        self,
        l1_imbalance: float,
        l2_imbalance: float,
        micro_shift: float,
    ) -> float:
        alpha = (
            self.L1_IMBALANCE_BETA * l1_imbalance
            + self.L2_IMBALANCE_BETA * l2_imbalance
            + self.MICROPRICE_BETA * micro_shift
        )
        if l1_imbalance * l2_imbalance < 0:
            alpha *= 0.75
        return self.clamp(alpha, -self.SIGNAL_CLIP_TICKS, self.SIGNAL_CLIP_TICKS)

    def should_take_at_anchor(
        self,
        side: str,
        price: int,
        anchor_fair: float,
        position: int,
        best_bid: Optional[int],
        best_bid_volume: Optional[int],
        best_ask: Optional[int],
        best_ask_volume: Optional[int],
    ) -> bool:
        anchor_price = int(round(anchor_fair))
        if price != anchor_price:
            return False
        strong_inventory_repair = abs(position) >= self.FAIR_REPAIR_MIN_POSITION
        if side == "BUY":
            if position >= 0:
                return False
            strong_same_price_unwind = (
                best_bid == anchor_price
                and best_bid_volume is not None
                and best_bid_volume >= self.FAIR_UNWIND_SAME_PRICE_VOLUME
            )
            return strong_inventory_repair or strong_same_price_unwind
        if position <= 0:
            return False
        strong_same_price_unwind = (
            best_ask == anchor_price
            and best_ask_volume is not None
            and best_ask_volume >= self.FAIR_UNWIND_SAME_PRICE_VOLUME
        )
        return strong_inventory_repair or strong_same_price_unwind

    @staticmethod
    def fair_repair_quantity(side: str, position: int) -> int:
        if side == "BUY" and position < 0:
            return abs(position)
        if side == "SELL" and position > 0:
            return abs(position)
        return 0

    def passive_sizes(
        self, position: int, buy_capacity: int, sell_capacity: int
    ) -> Tuple[int, int]:
        passive_buy_size = min(self.MAX_PASSIVE_SIZE, buy_capacity)
        passive_sell_size = min(self.MAX_PASSIVE_SIZE, sell_capacity)
        long_pressure = max(0.0, position / self.POSITION_LIMIT) if self.POSITION_LIMIT > 0 else 0.0
        short_pressure = max(0.0, -position / self.POSITION_LIMIT) if self.POSITION_LIMIT > 0 else 0.0
        buy_scale = self.clamp(1.0 - self.SIZE_PRESSURE * long_pressure, 0.0, 1.0)
        sell_scale = self.clamp(1.0 - self.SIZE_PRESSURE * short_pressure, 0.0, 1.0)
        passive_buy_size = min(passive_buy_size, int(round(self.MAX_PASSIVE_SIZE * buy_scale)))
        passive_sell_size = min(passive_sell_size, int(round(self.MAX_PASSIVE_SIZE * sell_scale)))
        return max(0, passive_buy_size), max(0, passive_sell_size)

    def trade_ash(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
        anchor_fair: float,
    ) -> List[Order]:
        orders: List[Order] = []
        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        mid = self.compute_mid(best_bid, best_ask)
        l1_imbalance, l2_imbalance, micro_shift = self.depth_features(
            order_depth, mid, best_bid_volume, best_ask_volume
        )
        fair_signal = anchor_fair + self.alpha_shift(l1_imbalance, l2_imbalance, micro_shift)
        buy_capacity, sell_capacity = self.capacities(position)
        projected_position = position

        if order_depth.sell_orders and buy_capacity > 0:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                ask_volume = -order_depth.sell_orders[ask_price]
                reservation = self.reservation_price(fair_signal, projected_position)
                edge = reservation - ask_price - self.TAKE_EDGE
                if edge > 0:
                    qty = min(ask_volume, buy_capacity)
                    self.add_order(orders, product, ask_price, qty)
                    buy_capacity -= qty
                    projected_position += qty
                    continue
                if (
                    edge >= -self.MARGINAL_TAKE_TOLERANCE
                    and self.should_take_at_anchor(
                        "BUY", ask_price, anchor_fair, projected_position,
                        best_bid, best_bid_volume, best_ask, best_ask_volume,
                    )
                    and buy_capacity > 0
                ):
                    qty = min(ask_volume, buy_capacity, self.fair_repair_quantity("BUY", projected_position))
                    self.add_order(orders, product, ask_price, qty)
                    buy_capacity -= qty
                    projected_position += qty
                    continue
                break

        if order_depth.buy_orders and sell_capacity > 0:
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                bid_volume = order_depth.buy_orders[bid_price]
                reservation = self.reservation_price(fair_signal, projected_position)
                edge = bid_price - reservation - self.TAKE_EDGE
                if edge > 0:
                    qty = min(bid_volume, sell_capacity)
                    self.add_order(orders, product, bid_price, -qty)
                    sell_capacity -= qty
                    projected_position -= qty
                    continue
                if (
                    edge >= -self.MARGINAL_TAKE_TOLERANCE
                    and self.should_take_at_anchor(
                        "SELL", bid_price, anchor_fair, projected_position,
                        best_bid, best_bid_volume, best_ask, best_ask_volume,
                    )
                    and sell_capacity > 0
                ):
                    qty = min(bid_volume, sell_capacity, self.fair_repair_quantity("SELL", projected_position))
                    self.add_order(orders, product, bid_price, -qty)
                    sell_capacity -= qty
                    projected_position -= qty
                    continue
                break

        reservation = self.reservation_price(fair_signal, projected_position)
        desired_bid = math.floor(reservation - self.DEFAULT_QUOTE_OFFSET)
        desired_ask = math.ceil(reservation + self.DEFAULT_QUOTE_OFFSET)

        passive_bid = min(desired_bid, best_bid + 1) if best_bid is not None else desired_bid
        passive_ask = max(desired_ask, best_ask - 1) if best_ask is not None else desired_ask

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)

        if passive_bid >= passive_ask:
            passive_bid = math.floor(reservation - 1)
            passive_ask = math.ceil(reservation + 1)

        passive_buy_size, passive_sell_size = self.passive_sizes(projected_position, buy_capacity, sell_capacity)

        signal_ticks = fair_signal - anchor_fair
        directional = abs(signal_ticks) >= self.DIRECTIONAL_SIGNAL and abs(l2_imbalance) >= 0.18
        toxic = abs(signal_ticks) >= self.STRONG_DIRECTIONAL_SIGNAL and abs(l2_imbalance) >= 0.28
        if directional and signal_ticks > 0:
            if best_bid is not None and best_ask is not None:
                passive_bid = max(passive_bid, min(best_ask - 1, best_bid + 1 + self.DIRECTIONAL_STEP_IN))
            passive_ask += self.OPPOSITE_WIDEN_TICKS
            passive_buy_size = min(buy_capacity, passive_buy_size + self.DIRECTIONAL_SIZE_BONUS)
            passive_sell_size = int(math.floor(passive_sell_size * self.DIRECTIONAL_OPPOSITE_SIZE_SCALE))
        elif directional and signal_ticks < 0:
            if best_bid is not None and best_ask is not None:
                passive_ask = min(passive_ask, max(best_bid + 1, best_ask - 1 - self.DIRECTIONAL_STEP_IN))
            passive_bid -= self.OPPOSITE_WIDEN_TICKS
            passive_sell_size = min(sell_capacity, passive_sell_size + self.DIRECTIONAL_SIZE_BONUS)
            passive_buy_size = int(math.floor(passive_buy_size * self.DIRECTIONAL_OPPOSITE_SIZE_SCALE))

        if toxic:
            if signal_ticks > 0:
                passive_sell_size = int(math.floor(passive_sell_size * self.TOXIC_OPPOSITE_SIZE_SCALE))
            else:
                passive_buy_size = int(math.floor(passive_buy_size * self.TOXIC_OPPOSITE_SIZE_SCALE))

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)
        if passive_bid >= passive_ask:
            passive_bid = passive_ask - 1

        if passive_buy_size > 0:
            self.add_order(orders, product, passive_bid, passive_buy_size)
        if passive_sell_size > 0:
            self.add_order(orders, product, passive_ask, -passive_sell_size)

        return orders


# ═══════════════════════════════════════════════════════════════════════════════
# INTARIAN_PEPPER_ROOT — trend + pullback strategy
# ═══════════════════════════════════════════════════════════════════════════════

class _PepperTraderBase:
    """
    INTARIAN_PEPPER_ROOT: EMA trend anchor + microstructure overlay +
    pullback trading + asymmetric inventory-aware quoting.
    """

    PRODUCT = "INTARIAN_PEPPER_ROOT"
    POSITION_LIMIT = 80

    EMA_FAST_ALPHA = 0.32
    EMA_SLOW_ALPHA = 0.10
    FAST_WEIGHT = 0.55
    SLOW_WEIGHT = 0.30
    MID_WEIGHT = 0.15
    HISTORY_WINDOW = 64
    TREND_WINDOW = 64
    TREND_FORECAST_HORIZON = 24
    TREND_SLOPE_CLIP = 0.18
    WARMUP_TICKS = 15
    TREND_PRIOR_STRENGTH = 10.0
    TREND_PRIOR_MAG = 0.12

    L2_LEVEL_WEIGHT = 0.70
    L1_IMBALANCE_BETA = 1.10
    L2_IMBALANCE_BETA = 4.40
    MICROPRICE_BETA = 1.00

    FLOW_HISTORY_WINDOW = 8
    FLOW_CONFIRM_SCALE = 14.0
    CONTINUATION_IMBALANCE = 0.18
    CONTINUATION_STRONG_IMBALANCE = 0.26
    CONTINUATION_BONUS = 1.05

    PULLBACK_Z_THRESHOLD = 0.90
    PULLBACK_BONUS = 1.55
    PULLBACK_IMBALANCE_BLOCK = -0.18
    STRETCH_Z_THRESHOLD = 1.55
    STRETCH_TRIM_BONUS = 0.55
    STRETCH_IMBALANCE_CONFIRM = 0.18

    BASE_HALF_SPREAD = 2
    VOL_MULTIPLIER = 0.45
    MIN_HALF_SPREAD = 2
    TAKE_EDGE = 1
    STRONG_SIGNAL_EXTRA_TAKE = 1
    AGGRESSIVE_CAP = 18

    TARGET_INVENTORY_MAX = 52
    INVENTORY_SKEW = 0.11
    SOFT_POSITION_LIMIT = 58
    HARD_POSITION_LIMIT = 78
    MAX_PASSIVE_SIZE = 20
    PASSIVE_REDUCTION_STEP = 6

    WEAK_TREND_SIGNAL = 0.90
    STRONG_TREND_SIGNAL = 2.40
    WIDE_SPREAD_THRESHOLD = 16
    VOLATILE_VOL_THRESHOLD = 4.40
    WEAK_TARGET_SCALE = 0.55
    WIDE_TARGET_SCALE = 0.75
    STRONG_TREND_TARGET_BONUS = 1.10
    WEAK_SIGNAL_SPREAD_ADD = 1
    WIDE_BOOK_SPREAD_ADD = 1
    WEAK_SIGNAL_TAKE_ADD = 1
    ADVERSE_SELECTION_TAKE_ADD = 1
    MIN_AGGRESSIVE_CAP = 4
    TREND_PROTECTION_IMBALANCE = 0.18
    TREND_PROTECTION_FLOW = 0.10
    TREND_PROTECTION_CAP_FRACTION = 0.35

    CARRY_MODE_SIGNAL = 1.55
    CARRY_MODE_IMBALANCE = 0.08
    CARRY_MODE_FLOW_FLOOR = -0.08
    CARRY_FLOOR_FRACTION = 0.58
    CARRY_OPPOSITE_SIZE_SCALE = 0.30
    CARRY_EXTRA_QUOTE_WIDEN = 1
    CARRY_SIZE_BONUS = 2

    BUDGET_MIN_UNITS = 32
    BUDGET_MAX_UNITS = 80
    BUDGET_BASE_RISK = 620.0
    BUDGET_TREND_BONUS = 0.82
    BUDGET_ADVERSE_VOL = 1.55
    BUDGET_ADVERSE_RESID = 2.00
    BUDGET_ADVERSE_SPREAD = 0.18

    WAREHOUSE_MODE_SIGNAL = 2.35
    WAREHOUSE_MODE_IMBALANCE = 0.12
    WAREHOUSE_MODE_FLOW = -0.04
    WAREHOUSE_TARGET_FRACTION = 0.68
    WAREHOUSE_FLOOR_FRACTION = 0.82
    WAREHOUSE_THRESHOLD_SHIFT = 1
    WAREHOUSE_SIZE_BONUS = 2
    WAREHOUSE_OPPOSITE_SCALE = 0.32

    DIRECTIONAL_SIGNAL = 1.15
    STRONG_SIGNAL = 2.15
    DIRECTIONAL_STEP_IN = 1
    OPPOSITE_WIDEN_TICKS = 1
    DIRECTIONAL_SIZE_BONUS = 3
    DIRECTIONAL_OPPOSITE_SIZE_SCALE = 0.45
    TOXIC_OPPOSITE_SIZE_SCALE = 0.55

    @staticmethod
    def add_order(orders: List[Order], product: str, price: int, quantity: int) -> None:
        if quantity != 0:
            orders.append(Order(product, int(price), int(quantity)))

    @staticmethod
    def best_levels(
        order_depth: OrderDepth,
    ) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        best_bid_volume = order_depth.buy_orders[best_bid] if best_bid is not None else None
        best_ask_volume = -order_depth.sell_orders[best_ask] if best_ask is not None else None
        return best_bid, best_bid_volume, best_ask, best_ask_volume

    @staticmethod
    def top_levels(order_depth: OrderDepth, side: str, depth: int = 2) -> List[Tuple[int, int]]:
        if side == "buy":
            return [
                (price, volume)
                for price, volume in sorted(order_depth.buy_orders.items(), reverse=True)[:depth]
                if volume > 0
            ]
        return [
            (price, -volume)
            for price, volume in sorted(order_depth.sell_orders.items())[:depth]
            if -volume > 0
        ]

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

    def capacities(self, position: int) -> Tuple[int, int]:
        return max(0, self.POSITION_LIMIT - position), max(0, self.POSITION_LIMIT + position)

    def hard_capacities(self, position: int) -> Tuple[int, int]:
        buy_capacity, sell_capacity = self.capacities(position)
        hard_limit = min(self.POSITION_LIMIT, self.HARD_POSITION_LIMIT)
        buy_hard_capacity = min(buy_capacity, max(0, hard_limit - position))
        sell_hard_capacity = min(sell_capacity, max(0, hard_limit + position))
        return buy_hard_capacity, sell_hard_capacity

    def soft_pressure(self, position: int) -> float:
        soft_limit = max(1, min(self.POSITION_LIMIT, self.SOFT_POSITION_LIMIT))
        hard_limit = max(soft_limit + 1, min(self.POSITION_LIMIT, self.HARD_POSITION_LIMIT))
        if abs(position) <= soft_limit:
            return 0.0
        return self.clamp((abs(position) - soft_limit) / (hard_limit - soft_limit), 0.0, 1.0)

    def update_state(
        self,
        product_state: Dict,
        mid: Optional[float],
        current_flow: int,
    ) -> Tuple[Optional[float], Optional[float], List[float], List[int]]:
        ema_fast = product_state.get("ema_fast")
        ema_slow = product_state.get("ema_slow")
        mids = list(product_state.get("mids", []))
        flows = list(product_state.get("flows", []))

        if mid is not None:
            ema_fast = mid if ema_fast is None else self.EMA_FAST_ALPHA * mid + (1.0 - self.EMA_FAST_ALPHA) * ema_fast
            ema_slow = mid if ema_slow is None else self.EMA_SLOW_ALPHA * mid + (1.0 - self.EMA_SLOW_ALPHA) * ema_slow
            mids.append(mid)
            if len(mids) > self.HISTORY_WINDOW:
                mids = mids[-self.HISTORY_WINDOW:]

        flows.append(int(current_flow))
        if len(flows) > self.FLOW_HISTORY_WINDOW:
            flows = flows[-self.FLOW_HISTORY_WINDOW:]

        product_state["ema_fast"] = ema_fast
        product_state["ema_slow"] = ema_slow
        product_state["mids"] = mids
        product_state["flows"] = flows
        return ema_fast, ema_slow, mids, flows

    def estimate_trend(self, mids: List[float]) -> Tuple[float, Optional[float], float]:
        if not mids:
            return 0.0, None, 0.0
        window = mids[-min(len(mids), self.TREND_WINDOW):]
        n = len(window)
        if n < 5:
            return 0.0, window[-1], 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        denom = sum((i - x_mean) ** 2 for i in range(n))
        if denom <= 0:
            return 0.0, window[-1], 0.0
        raw_slope = sum((i - x_mean) * (window[i] - y_mean) for i in range(n)) / denom
        endpoint_slope = (window[-1] - window[0]) / max(1, n - 1)
        prior_slope = self.clamp(endpoint_slope, -self.TREND_PRIOR_MAG, self.TREND_PRIOR_MAG)
        weight = n / (n + self.TREND_PRIOR_STRENGTH)
        slope = weight * raw_slope + (1.0 - weight) * prior_slope
        slope = self.clamp(slope, -self.TREND_SLOPE_CLIP, self.TREND_SLOPE_CLIP)
        intercept = y_mean - slope * x_mean
        fitted = [intercept + slope * i for i in range(n)]
        fitted_current = fitted[-1]
        residuals = [window[i] - fitted[i] for i in range(n)]
        resid_std = max(statistics.pstdev(residuals), 1.0)
        resid_z = (window[-1] - fitted_current) / resid_std
        return slope, fitted_current, resid_z

    def depth_features(
        self,
        order_depth: OrderDepth,
        mid: Optional[float],
        best_bid_volume: Optional[int],
        best_ask_volume: Optional[int],
    ) -> Tuple[float, float, float]:
        l1_imbalance = self.imbalance(best_bid_volume, best_ask_volume)
        if mid is None:
            return l1_imbalance, l1_imbalance, 0.0

        bid_levels = self.top_levels(order_depth, "buy", depth=2)
        ask_levels = self.top_levels(order_depth, "sell", depth=2)
        weights = (1.0, self.L2_LEVEL_WEIGHT)

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

    def signed_trade_flow(
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

    def build_fair_base(
        self,
        mid: Optional[float],
        ema_fast: Optional[float],
        ema_slow: Optional[float],
        trend_slope: float,
    ) -> Optional[float]:
        usable: List[Tuple[float, float]] = []
        if ema_fast is not None:
            usable.append((self.FAST_WEIGHT, ema_fast))
        if ema_slow is not None:
            usable.append((self.SLOW_WEIGHT, ema_slow))
        if mid is not None:
            usable.append((self.MID_WEIGHT, mid))
        if not usable:
            return None
        weight_sum = sum(w for w, _ in usable)
        anchor = sum(w * v for w, v in usable) / weight_sum
        return anchor + trend_slope * self.TREND_FORECAST_HORIZON

    def continuation_adjustment(
        self,
        trend_slope: float,
        l2_imbalance: float,
        micro_shift: float,
        flow_recent: float,
    ) -> float:
        if abs(l2_imbalance) < self.CONTINUATION_IMBALANCE:
            return 0.0
        trend_dir = self.sign(trend_slope)
        book_dir = self.sign(l2_imbalance)
        aligned_trend = trend_dir != 0 and trend_dir == book_dir
        aligned_flow = flow_recent * l2_imbalance > 0.015
        aligned_micro = micro_shift * l2_imbalance > 0.0
        if not (aligned_trend or aligned_flow or aligned_micro):
            return 0.0
        strength = self.clamp(abs(l2_imbalance) / 0.40 + 0.30 * abs(flow_recent), 0.0, 1.0)
        if aligned_trend and abs(l2_imbalance) >= self.CONTINUATION_STRONG_IMBALANCE:
            strength = self.clamp(strength + 0.18, 0.0, 1.0)
        return book_dir * self.CONTINUATION_BONUS * strength

    def pullback_adjustment(self, trend_slope: float, resid_z: float, l2_imbalance: float) -> float:
        trend_dir = self.sign(trend_slope)
        if trend_dir == 0:
            return 0.0
        if trend_dir > 0 and resid_z <= -self.PULLBACK_Z_THRESHOLD and l2_imbalance > self.PULLBACK_IMBALANCE_BLOCK:
            strength = self.clamp((abs(resid_z) - self.PULLBACK_Z_THRESHOLD) / 1.3 + 0.35, 0.0, 1.0)
            return self.PULLBACK_BONUS * strength
        if trend_dir < 0 and resid_z >= self.PULLBACK_Z_THRESHOLD and l2_imbalance < -self.PULLBACK_IMBALANCE_BLOCK:
            strength = self.clamp((abs(resid_z) - self.PULLBACK_Z_THRESHOLD) / 1.3 + 0.35, 0.0, 1.0)
            return -self.PULLBACK_BONUS * strength
        if trend_dir > 0 and resid_z >= self.STRETCH_Z_THRESHOLD and l2_imbalance < self.STRETCH_IMBALANCE_CONFIRM:
            strength = self.clamp((resid_z - self.STRETCH_Z_THRESHOLD) / 1.2 + 0.25, 0.0, 1.0)
            return -self.STRETCH_TRIM_BONUS * strength
        if trend_dir < 0 and resid_z <= -self.STRETCH_Z_THRESHOLD and l2_imbalance > -self.STRETCH_IMBALANCE_CONFIRM:
            strength = self.clamp((abs(resid_z) - self.STRETCH_Z_THRESHOLD) / 1.2 + 0.25, 0.0, 1.0)
            return self.STRETCH_TRIM_BONUS * strength
        return 0.0

    def desired_inventory(
        self,
        trend_signal: float,
        continuation_adj: float,
        visible_spread: Optional[int],
        vol: float,
        l2_imbalance: float,
        flow_recent: float,
    ) -> int:
        raw_signal = trend_signal + 0.8 * continuation_adj
        direction = self.sign(raw_signal)
        if direction == 0:
            return 0
        strength = self.clamp(
            abs(raw_signal) / 3.6 + 0.30 * abs(l2_imbalance) + 0.20 * abs(flow_recent),
            0.0, 1.0,
        )
        target = self.TARGET_INVENTORY_MAX * strength
        if abs(raw_signal) < self.WEAK_TREND_SIGNAL:
            target *= self.WEAK_TARGET_SCALE
        if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD:
            target *= self.WIDE_TARGET_SCALE
        if vol >= self.VOLATILE_VOL_THRESHOLD:
            target *= 0.82
        if direction * l2_imbalance < -self.TREND_PROTECTION_IMBALANCE:
            target *= 0.72
        if direction * flow_recent < -self.TREND_PROTECTION_FLOW:
            target *= 0.78
        if (
            abs(raw_signal) >= self.STRONG_TREND_SIGNAL
            and direction * l2_imbalance >= 0.0
            and direction * flow_recent >= -0.05
        ):
            target *= self.STRONG_TREND_TARGET_BONUS
        target = self.clamp(target, 0.0, float(self.TARGET_INVENTORY_MAX))
        return int(round(direction * target))

    def inventory_budget_units(
        self,
        vol: float,
        visible_spread: Optional[int],
        resid_z: float,
        trend_signal: float,
        continuation_adj: float,
        l2_imbalance: float,
        flow_recent: float,
    ) -> int:
        raw_signal = trend_signal + 0.8 * continuation_adj
        direction = self.sign(raw_signal)
        aligned_imbalance = max(0.0, direction * l2_imbalance) if direction != 0 else 0.0
        aligned_flow = max(0.0, direction * flow_recent) if direction != 0 else 0.0
        aligned_strength = (
            abs(trend_signal)
            + 1.15 * abs(continuation_adj)
            + 2.10 * aligned_imbalance
            + 1.35 * aligned_flow
        )
        risk_budget = self.BUDGET_BASE_RISK * (
            1.0 + self.BUDGET_TREND_BONUS * self.clamp(aligned_strength / 4.0, 0.0, 1.0)
        )
        adverse_move = 3.0 + self.BUDGET_ADVERSE_VOL * vol + self.BUDGET_ADVERSE_RESID * max(0.0, abs(resid_z) - 0.35)
        if visible_spread is not None and visible_spread > 10:
            adverse_move += self.BUDGET_ADVERSE_SPREAD * (visible_spread - 10)
        units = risk_budget / max(adverse_move, 1.0)
        return int(round(self.clamp(units, self.BUDGET_MIN_UNITS, self.BUDGET_MAX_UNITS)))

    def carry_inventory_floor(
        self,
        trend_signal: float,
        continuation_adj: float,
        l2_imbalance: float,
        flow_recent: float,
        target_inventory: int,
    ) -> int:
        raw_signal = trend_signal + 0.8 * continuation_adj
        direction = self.sign(raw_signal)
        if direction == 0:
            return 0
        if abs(raw_signal) < self.CARRY_MODE_SIGNAL:
            return 0
        if direction * l2_imbalance < self.CARRY_MODE_IMBALANCE:
            return 0
        if direction * flow_recent < self.CARRY_MODE_FLOW_FLOOR:
            return 0

        base_floor = max(
            abs(target_inventory) * self.CARRY_FLOOR_FRACTION,
            self.TARGET_INVENTORY_MAX * 0.25,
        )
        strength = self.clamp(
            abs(raw_signal) / 4.5 + 0.20 * max(0.0, direction * l2_imbalance) + 0.15 * max(0.0, direction * flow_recent),
            0.0,
            1.0,
        )
        floor = base_floor + strength * self.TARGET_INVENTORY_MAX * 0.12
        floor = self.clamp(floor, 0.0, float(self.TARGET_INVENTORY_MAX))
        return int(round(direction * floor))

    def adaptive_half_spread(
        self,
        vol: float,
        visible_spread: Optional[int],
        trend_signal: float,
        continuation_adj: float,
        l2_imbalance: float,
        flow_recent: float,
    ) -> int:
        half_spread = max(self.MIN_HALF_SPREAD, int(round(self.BASE_HALF_SPREAD + self.VOL_MULTIPLIER * vol)))
        if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD:
            half_spread += self.WIDE_BOOK_SPREAD_ADD
        weak_signal = abs(trend_signal) < self.WEAK_TREND_SIGNAL and abs(continuation_adj) < 0.35
        if weak_signal:
            half_spread += self.WEAK_SIGNAL_SPREAD_ADD
        if (
            abs(trend_signal) >= self.STRONG_TREND_SIGNAL
            and self.sign(trend_signal) * self.sign(l2_imbalance) > 0
            and self.sign(trend_signal) * flow_recent >= -0.05
            and visible_spread is not None
            and visible_spread <= 10
        ):
            half_spread = max(self.MIN_HALF_SPREAD, half_spread - 1)
        return half_spread

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

    def passive_sizes(
        self,
        position: int,
        target_inventory: int,
        buy_capacity: int,
        sell_capacity: int,
        buy_hard_capacity: int,
        sell_hard_capacity: int,
        vol: float,
        visible_spread: Optional[int],
        trend_signal: float,
        continuation_adj: float,
    ) -> Tuple[int, int]:
        base_size = max(1, self.MAX_PASSIVE_SIZE - int(round(0.50 * vol)))
        if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD:
            base_size = max(1, base_size - 2)
        if abs(trend_signal) < self.WEAK_TREND_SIGNAL and abs(continuation_adj) < 0.35:
            base_size = max(1, base_size - 2)
        passive_buy_size = min(base_size, buy_capacity, buy_hard_capacity)
        passive_sell_size = min(base_size, sell_capacity, sell_hard_capacity)

        inventory_gap = position - target_inventory
        if inventory_gap > 0:
            pressure_units = int(inventory_gap // self.PASSIVE_REDUCTION_STEP)
            passive_buy_size = max(0, passive_buy_size - pressure_units)
            passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + pressure_units)
        elif inventory_gap < 0:
            pressure_units = int((-inventory_gap) // self.PASSIVE_REDUCTION_STEP)
            passive_sell_size = max(0, passive_sell_size - pressure_units)
            passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + pressure_units)

        soft_p = self.soft_pressure(position)
        if position >= self.SOFT_POSITION_LIMIT:
            passive_buy_size = int(math.floor(passive_buy_size * (1.0 - soft_p)))
        elif position <= -self.SOFT_POSITION_LIMIT:
            passive_sell_size = int(math.floor(passive_sell_size * (1.0 - soft_p)))

        return max(0, passive_buy_size), max(0, passive_sell_size)

    def adjust_directional_quotes(
        self,
        passive_bid: int,
        passive_ask: int,
        passive_buy_size: int,
        passive_sell_size: int,
        best_bid: Optional[int],
        best_ask: Optional[int],
        visible_spread: Optional[int],
        signal_ticks: float,
        trend_signal: float,
        l2_imbalance: float,
        micro_shift: float,
        continuation_adj: float,
        flow_recent: float,
        buy_capacity: int,
        sell_capacity: int,
        buy_hard_capacity: int,
        sell_hard_capacity: int,
    ) -> Tuple[int, int, int, int]:
        direction = self.sign(signal_ticks)

        if abs(continuation_adj) >= 0.45 and abs(l2_imbalance) >= self.CONTINUATION_IMBALANCE:
            if continuation_adj > 0:
                passive_sell_size = int(math.floor(passive_sell_size * self.TOXIC_OPPOSITE_SIZE_SCALE))
            elif continuation_adj < 0:
                passive_buy_size = int(math.floor(passive_buy_size * self.TOXIC_OPPOSITE_SIZE_SCALE))

        directional = (
            visible_spread is not None
            and visible_spread >= 4
            and abs(signal_ticks) >= self.DIRECTIONAL_SIGNAL
            and (abs(l2_imbalance) >= 0.12 or abs(micro_shift) >= 0.18 or abs(continuation_adj) >= 0.28)
        )
        if not directional:
            return passive_bid, passive_ask, passive_buy_size, passive_sell_size

        if direction > 0:
            if self.sign(trend_signal) < 0 and abs(trend_signal) >= self.WEAK_TREND_SIGNAL:
                return passive_bid, passive_ask, passive_buy_size, passive_sell_size
            if best_bid is not None and best_ask is not None:
                target_bid = min(best_ask - 1, best_bid + 1 + self.DIRECTIONAL_STEP_IN)
                passive_bid = max(passive_bid, target_bid)
            elif best_bid is not None:
                passive_bid = max(passive_bid, best_bid + 1)
            ask_widen = self.OPPOSITE_WIDEN_TICKS + (
                1 if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD else 0
            )
            passive_ask += ask_widen
            passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + self.DIRECTIONAL_SIZE_BONUS)
            passive_sell_size = int(math.floor(passive_sell_size * self.DIRECTIONAL_OPPOSITE_SIZE_SCALE))
        elif direction < 0:
            if self.sign(trend_signal) > 0 and abs(trend_signal) >= self.WEAK_TREND_SIGNAL:
                return passive_bid, passive_ask, passive_buy_size, passive_sell_size
            if best_bid is not None and best_ask is not None:
                target_ask = max(best_bid + 1, best_ask - 1 - self.DIRECTIONAL_STEP_IN)
                passive_ask = min(passive_ask, target_ask)
            elif best_ask is not None:
                passive_ask = min(passive_ask, best_ask - 1)
            bid_widen = self.OPPOSITE_WIDEN_TICKS + (
                1 if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD else 0
            )
            passive_bid -= bid_widen
            passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + self.DIRECTIONAL_SIZE_BONUS)
            passive_buy_size = int(math.floor(passive_buy_size * self.DIRECTIONAL_OPPOSITE_SIZE_SCALE))

        if direction != 0 and direction * flow_recent < -self.TREND_PROTECTION_FLOW:
            if direction > 0:
                passive_buy_size = int(math.floor(passive_buy_size * 0.75))
            else:
                passive_sell_size = int(math.floor(passive_sell_size * 0.75))

        if best_ask is not None:
            passive_bid = min(passive_bid, best_ask - 1)
        if best_bid is not None:
            passive_ask = max(passive_ask, best_bid + 1)
        if passive_bid >= passive_ask:
            passive_bid = passive_ask - 1

        return passive_bid, passive_ask, max(0, passive_buy_size), max(0, passive_sell_size)

    def trade_pepper(
        self,
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
            self.PRODUCT,
            {
                "ema_fast": None, "ema_slow": None,
                "mids": [], "flows": [],
                "prev_best_bid": None, "prev_best_ask": None,
            },
        )

        # Classify market_trades using the previous tick's book (trades arrived last tick).
        prev_best_bid = product_state.get("prev_best_bid")
        prev_best_ask = product_state.get("prev_best_ask")
        prev_mid = self.compute_mid(prev_best_bid, prev_best_ask)
        current_flow = self.signed_trade_flow(
            market_trades,
            prev_best_bid if prev_best_bid is not None else best_bid,
            prev_best_ask if prev_best_ask is not None else best_ask,
            prev_mid if prev_mid is not None else mid,
        )

        ema_fast, ema_slow, mids, flows = self.update_state(product_state, mid, current_flow)

        # Persist current book for next tick's flow classification.
        product_state["prev_best_bid"] = best_bid
        product_state["prev_best_ask"] = best_ask

        if mid is None:
            return orders

        # Don't trade until enough history for reliable trend estimation.
        if len(mids) < self.WARMUP_TICKS:
            return orders

        trend_slope, fitted_current, resid_z = self.estimate_trend(mids)
        fair_base = self.build_fair_base(mid, ema_fast, ema_slow, trend_slope)
        if fair_base is None:
            return orders

        vol = self.realized_volatility(mids)
        l1_imbalance, l2_imbalance, micro_shift = self.depth_features(
            order_depth, mid, best_bid_volume, best_ask_volume
        )
        flow_recent = self.clamp(sum(flows[-3:]) / self.FLOW_CONFIRM_SCALE, -1.0, 1.0) if flows else 0.0

        l1_adj = self.L1_IMBALANCE_BETA * l1_imbalance
        l2_adj = self.L2_IMBALANCE_BETA * l2_imbalance
        micro_adj = self.MICROPRICE_BETA * micro_shift
        continuation_adj = self.continuation_adjustment(trend_slope, l2_imbalance, micro_shift, flow_recent)
        pullback_adj = self.pullback_adjustment(trend_slope, resid_z, l2_imbalance)

        fair_signal = fair_base + l1_adj + l2_adj + micro_adj + continuation_adj + pullback_adj
        trend_signal = fair_base - mid
        target_inventory = self.desired_inventory(
            trend_signal, continuation_adj, visible_spread, vol, l2_imbalance, flow_recent
        )
        inventory_budget = self.inventory_budget_units(
            vol, visible_spread, resid_z, trend_signal, continuation_adj, l2_imbalance, flow_recent
        )
        target_direction = self.sign(target_inventory)
        target_abs = abs(target_inventory)
        extra_budget = max(0, inventory_budget - target_abs)
        target_inventory = target_direction * min(inventory_budget, target_abs + int(round(0.60 * extra_budget)))
        target_inventory = int(round(self.clamp(target_inventory, -self.HARD_POSITION_LIMIT, self.HARD_POSITION_LIMIT)))
        raw_signal = trend_signal + 0.8 * continuation_adj
        trend_dir = self.sign(raw_signal)
        warehouse_mode = (
            trend_dir != 0
            and abs(raw_signal) >= self.WAREHOUSE_MODE_SIGNAL
            and trend_dir * l2_imbalance >= self.WAREHOUSE_MODE_IMBALANCE
            and trend_dir * flow_recent >= self.WAREHOUSE_MODE_FLOW
        )
        if warehouse_mode:
            warehouse_target = max(abs(target_inventory), int(round(inventory_budget * self.WAREHOUSE_TARGET_FRACTION)))
            target_inventory = trend_dir * warehouse_target
        carry_floor = self.carry_inventory_floor(
            trend_signal, continuation_adj, l2_imbalance, flow_recent, target_inventory
        )
        if warehouse_mode:
            carry_floor = trend_dir * max(
                abs(carry_floor),
                int(round(abs(target_inventory) * self.WAREHOUSE_FLOOR_FRACTION)),
            )
        carry_floor = int(round(self.clamp(carry_floor, -self.HARD_POSITION_LIMIT, self.HARD_POSITION_LIMIT)))
        if carry_floor > 0:
            target_inventory = max(target_inventory, carry_floor)
        elif carry_floor < 0:
            target_inventory = min(target_inventory, carry_floor)

        buy_capacity, sell_capacity = self.capacities(position)
        buy_hard_capacity, sell_hard_capacity = self.hard_capacities(position)

        reservation_price = fair_signal - self.INVENTORY_SKEW * (position - target_inventory)
        signal_ticks = reservation_price - mid
        half_spread = self.adaptive_half_spread(
            vol, visible_spread, trend_signal, continuation_adj, l2_imbalance, flow_recent
        )

        take_edge = self.TAKE_EDGE + (self.STRONG_SIGNAL_EXTRA_TAKE if abs(signal_ticks) >= self.STRONG_SIGNAL else 0)
        if abs(trend_signal) < self.WEAK_TREND_SIGNAL and abs(continuation_adj) < 0.35:
            take_edge += self.WEAK_SIGNAL_TAKE_ADD
        if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD:
            take_edge += 1
        if self.sign(trend_signal) * self.sign(l2_imbalance) < 0 and abs(l2_imbalance) >= self.CONTINUATION_IMBALANCE:
            take_edge += self.ADVERSE_SELECTION_TAKE_ADD
        aggressive_buy_threshold = math.floor(reservation_price - take_edge)
        aggressive_sell_threshold = math.ceil(reservation_price + take_edge)
        if warehouse_mode:
            aggressive_buy_threshold += trend_dir * self.WAREHOUSE_THRESHOLD_SHIFT
            aggressive_sell_threshold += trend_dir * self.WAREHOUSE_THRESHOLD_SHIFT

        projected_position = position

        if order_depth.sell_orders and buy_capacity > 0 and buy_hard_capacity > 0:
            remaining_take = min(buy_capacity, buy_hard_capacity, self.AGGRESSIVE_CAP)
            if signal_ticks < -self.DIRECTIONAL_SIGNAL and projected_position > target_inventory:
                remaining_take = min(
                    remaining_take,
                    max(self.MIN_AGGRESSIVE_CAP, int(self.AGGRESSIVE_CAP * self.TREND_PROTECTION_CAP_FRACTION)),
                )
            for ask_price in sorted(order_depth.sell_orders.keys()):
                ask_volume = -order_depth.sell_orders[ask_price]
                if remaining_take <= 0:
                    break
                if ask_price <= aggressive_buy_threshold:
                    qty = min(ask_volume, remaining_take)
                    if carry_floor < 0:
                        qty = min(qty, max(0, carry_floor - projected_position))
                    if qty <= 0:
                        break
                    self.add_order(orders, self.PRODUCT, ask_price, qty)
                    buy_capacity -= qty
                    buy_hard_capacity -= qty
                    remaining_take -= qty
                    projected_position += qty
                else:
                    break

        if order_depth.buy_orders and sell_capacity > 0 and sell_hard_capacity > 0:
            remaining_take = min(sell_capacity, sell_hard_capacity, self.AGGRESSIVE_CAP)
            if signal_ticks > self.DIRECTIONAL_SIGNAL and projected_position < target_inventory:
                remaining_take = min(
                    remaining_take,
                    max(self.MIN_AGGRESSIVE_CAP, int(self.AGGRESSIVE_CAP * self.TREND_PROTECTION_CAP_FRACTION)),
                )
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                bid_volume = order_depth.buy_orders[bid_price]
                if remaining_take <= 0:
                    break
                if bid_price >= aggressive_sell_threshold:
                    qty = min(bid_volume, remaining_take)
                    if carry_floor > 0:
                        qty = min(qty, max(0, projected_position - carry_floor))
                    if qty <= 0:
                        break
                    self.add_order(orders, self.PRODUCT, bid_price, -qty)
                    sell_capacity -= qty
                    sell_hard_capacity -= qty
                    remaining_take -= qty
                    projected_position -= qty
                else:
                    break

        reservation_price = fair_signal - self.INVENTORY_SKEW * (projected_position - target_inventory)
        signal_ticks = reservation_price - mid
        buy_hard_capacity, sell_hard_capacity = self.hard_capacities(projected_position)
        buy_hard_capacity = min(buy_capacity, buy_hard_capacity)
        sell_hard_capacity = min(sell_capacity, sell_hard_capacity)

        desired_bid = math.floor(reservation_price - half_spread)
        desired_ask = math.ceil(reservation_price + half_spread)
        passive_bid, passive_ask = self.clamp_passive_quotes(
            reservation_price, best_bid, best_ask, desired_bid, desired_ask
        )

        passive_buy_size, passive_sell_size = self.passive_sizes(
            projected_position, target_inventory,
            buy_capacity, sell_capacity,
            buy_hard_capacity, sell_hard_capacity,
            vol, visible_spread, trend_signal, continuation_adj,
        )

        if carry_floor > 0 and projected_position < carry_floor:
            passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + self.CARRY_SIZE_BONUS)
            passive_sell_size = int(math.floor(passive_sell_size * self.CARRY_OPPOSITE_SIZE_SCALE))
        elif carry_floor < 0 and projected_position > carry_floor:
            passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + self.CARRY_SIZE_BONUS)
            passive_buy_size = int(math.floor(passive_buy_size * self.CARRY_OPPOSITE_SIZE_SCALE))
        if warehouse_mode:
            if trend_dir > 0:
                passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + self.WAREHOUSE_SIZE_BONUS)
                passive_sell_size = int(math.floor(passive_sell_size * self.WAREHOUSE_OPPOSITE_SCALE))
            else:
                passive_sell_size = min(sell_capacity, sell_hard_capacity, passive_sell_size + self.WAREHOUSE_SIZE_BONUS)
                passive_buy_size = int(math.floor(passive_buy_size * self.WAREHOUSE_OPPOSITE_SCALE))

        passive_bid, passive_ask, passive_buy_size, passive_sell_size = self.adjust_directional_quotes(
            passive_bid, passive_ask, passive_buy_size, passive_sell_size,
            best_bid, best_ask, visible_spread, signal_ticks,
            trend_signal, l2_imbalance, micro_shift, continuation_adj, flow_recent,
            buy_capacity, sell_capacity, buy_hard_capacity, sell_hard_capacity,
        )

        if carry_floor > 0 and signal_ticks > self.CARRY_MODE_SIGNAL:
            passive_ask += self.CARRY_EXTRA_QUOTE_WIDEN
            if best_bid is not None:
                passive_ask = max(passive_ask, best_bid + 1)
        elif carry_floor < 0 and signal_ticks < -self.CARRY_MODE_SIGNAL:
            passive_bid -= self.CARRY_EXTRA_QUOTE_WIDEN
            if best_ask is not None:
                passive_bid = min(passive_bid, best_ask - 1)
        if warehouse_mode:
            if trend_dir > 0:
                passive_ask += 1
            else:
                passive_bid -= 1

        if passive_buy_size > 0:
            self.add_order(orders, self.PRODUCT, passive_bid, passive_buy_size)
        if passive_sell_size > 0:
            self.add_order(orders, self.PRODUCT, passive_ask, -passive_sell_size)

        return orders


# ═══════════════════════════════════════════════════════════════════════════════
# Combined model — entry point for the Prosperity platform
# ═══════════════════════════════════════════════════════════════════════════════

class _PepperTrader(_PepperTraderBase):
    """G2: refined PEPPER time-scheduled inventory policy."""

    WARMUP_TICKS = 8
    TARGET_INVENTORY_MAX = 80
    SOFT_POSITION_LIMIT = 78
    HARD_POSITION_LIMIT = 80
    MAX_PASSIVE_SIZE = 22
    PASSIVE_REDUCTION_STEP = 5
    BUDGET_MIN_UNITS = 74
    BUDGET_MAX_UNITS = 80
    BUDGET_BASE_RISK = 710.0

    EARLY_END = 0.24
    MID_END = 0.78
    LATE_END = 0.92
    EARLY_TARGET = 80
    MID_TARGET = 76
    LATE_TARGET = 72
    END_TARGET = 50
    TARGET_ADVERSE_CUT = 10

    def _session_progress(self) -> float:
        return float(getattr(self, '_current_progress', 1.0))

    def _scheduled_target(self, l2_imbalance: float, flow_recent: float) -> int:
        p = self._session_progress()
        if p < self.EARLY_END:
            target = self.EARLY_TARGET
        elif p < self.MID_END:
            target = self.MID_TARGET
        elif p < self.LATE_END:
            target = self.LATE_TARGET
        else:
            target = self.END_TARGET
        if l2_imbalance < -0.18 and flow_recent < -0.10:
            target -= self.TARGET_ADVERSE_CUT
        elif l2_imbalance < -0.08:
            target -= 4
        elif l2_imbalance > 0.10 and flow_recent > -0.05 and p < self.LATE_END:
            target += 2
        return max(12, min(self.TARGET_INVENTORY_MAX, target))

    def desired_inventory(self, trend_signal: float, continuation_adj: float, visible_spread: int | None, vol: float, l2_imbalance: float, flow_recent: float) -> int:
        raw_signal = trend_signal + 0.8 * continuation_adj
        target = self._scheduled_target(l2_imbalance, flow_recent)
        if raw_signal < -0.95:
            target -= 12
        elif raw_signal < -0.45:
            target -= 6
        self._last_schedule_target = max(12, min(self.TARGET_INVENTORY_MAX, target))
        return self._last_schedule_target

    def carry_inventory_floor(self, trend_signal: float, continuation_adj: float, l2_imbalance: float, flow_recent: float, target_inventory: int) -> int:
        p = self._session_progress()
        floor_frac = 0.88 if p < self.LATE_END else 0.78
        floor = max(14, int(round(target_inventory * floor_frac)))
        if trend_signal + 0.8 * continuation_adj < -1.0:
            floor = max(10, floor - 10)
        return min(target_inventory, floor)

    def passive_sizes(self, position: int, target_inventory: int, buy_capacity: int, sell_capacity: int, buy_hard_capacity: int, sell_hard_capacity: int, vol: float, visible_spread: int | None, trend_signal: float, continuation_adj: float) -> tuple[int, int]:
        passive_buy_size, passive_sell_size = super().passive_sizes(position, target_inventory, buy_capacity, sell_capacity, buy_hard_capacity, sell_hard_capacity, vol, visible_spread, trend_signal, continuation_adj)
        gap = max(0, target_inventory - position)
        if gap > 0:
            passive_buy_size = min(buy_capacity, buy_hard_capacity, passive_buy_size + min(5, max(1, gap // 10)))
            passive_sell_size = int(math.floor(passive_sell_size * (0.20 if gap >= 12 else 0.42)))
        return max(0, passive_buy_size), max(0, passive_sell_size)

    def adjust_directional_quotes(self, passive_bid: int, passive_ask: int, passive_buy_size: int, passive_sell_size: int, best_bid: int | None, best_ask: int | None, visible_spread: int | None, signal_ticks: float, trend_signal: float, l2_imbalance: float, micro_shift: float, continuation_adj: float, flow_recent: float, buy_capacity: int, sell_capacity: int, buy_hard_capacity: int, sell_hard_capacity: int) -> tuple[int, int, int, int]:
        passive_bid, passive_ask, passive_buy_size, passive_sell_size = super().adjust_directional_quotes(passive_bid, passive_ask, passive_buy_size, passive_sell_size, best_bid, best_ask, visible_spread, signal_ticks, trend_signal, l2_imbalance, micro_shift, continuation_adj, flow_recent, buy_capacity, sell_capacity, buy_hard_capacity, sell_hard_capacity)
        gap = max(0, int(getattr(self, '_last_schedule_target', 0)) - int(getattr(self, '_position_snapshot', 0)))
        if gap >= 10 and best_bid is not None and best_ask is not None and visible_spread is not None and visible_spread >= 4:
            passive_bid = max(passive_bid, min(best_ask - 1, best_bid + 1))
            passive_ask += 1
        return max(0, passive_bid), max(0, passive_ask), max(0, passive_buy_size), max(0, passive_sell_size)

    def trade_pepper(self, order_depth: OrderDepth, position: int, state_store: Dict, market_trades: List[Trade], timestamp: int) -> List[Order]:
        self._current_progress = float(timestamp) / 999900.0 if timestamp >= 0 else 1.0
        self._position_snapshot = position
        self._last_schedule_target = 0
        try:
            return super().trade_pepper(order_depth, position, state_store, market_trades)
        finally:
            self._current_progress = 1.0
            self._position_snapshot = 0


class Trader:
    """Round 1 model_G2: policy architecture research variant."""

    def __init__(self) -> None:
        self.ash = _AshTrader()
        self.pepper = _PepperTrader()

    def _load_state(self, trader_data: str) -> Dict:
        default = {
            self.ash.PRODUCT: {"anchor": None, "tick": 0},
            self.pepper.PRODUCT: {
                "ema_fast": None,
                "ema_slow": None,
                "mids": [],
                "flows": [],
                "prev_best_bid": None,
                "prev_best_ask": None,
            },
        }
        if not trader_data:
            return default
        try:
            parsed = json.loads(trader_data)
            if not isinstance(parsed, dict):
                return default
            parsed.setdefault(self.ash.PRODUCT, {})
            ash = parsed[self.ash.PRODUCT]
            ash.setdefault("anchor", None)
            ash.setdefault("tick", 0)
            parsed.setdefault(self.pepper.PRODUCT, {})
            pep = parsed[self.pepper.PRODUCT]
            pep.setdefault("ema_fast", None)
            pep.setdefault("ema_slow", None)
            pep.setdefault("mids", [])
            pep.setdefault("flows", [])
            pep.setdefault("prev_best_bid", None)
            pep.setdefault("prev_best_ask", None)
            return parsed
        except Exception:
            return default

    @staticmethod
    def _dump_state(state: Dict) -> str:
        return json.dumps(state, separators=(",", ":"))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        state_store = self._load_state(state.traderData)

        ash_depth = state.order_depths.get(self.ash.PRODUCT)
        if ash_depth is not None:
            best_bid, _, best_ask, _ = self.ash.best_levels(ash_depth)
            mid = self.ash.compute_mid(best_bid, best_ask)
            ash_state = state_store[self.ash.PRODUCT]
            anchor_fair = self.ash.update_anchor(ash_state, mid)
            ash_position = state.position.get(self.ash.PRODUCT, 0)
            result[self.ash.PRODUCT] = self.ash.trade_ash(
                self.ash.PRODUCT,
                ash_depth,
                ash_position,
                anchor_fair,
            )
        else:
            result[self.ash.PRODUCT] = []

        pepper_depth = state.order_depths.get(self.pepper.PRODUCT)
        if pepper_depth is not None:
            pepper_position = state.position.get(self.pepper.PRODUCT, 0)
            result[self.pepper.PRODUCT] = self.pepper.trade_pepper(
                pepper_depth,
                pepper_position,
                state_store,
                state.market_trades.get(self.pepper.PRODUCT, []),
                state.timestamp,
            )
        else:
            result[self.pepper.PRODUCT] = []

        for product in state.order_depths:
            result.setdefault(product, [])

        return result, 0, self._dump_state(state_store)
