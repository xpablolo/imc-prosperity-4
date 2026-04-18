from __future__ import annotations

import json
import math
import statistics
from typing import Dict, List, Optional, Tuple

try:
    from datamodel import OrderDepth, Order, Trade, TradingState
except ImportError:  # pragma: no cover
    from round_1.models.datamodel import OrderDepth, Order, Trade, TradingState


class Trader:
    """
    INTARIAN_PEPPER_ROOT strategy.

    Design choice:
    - Do NOT port the EMERALDS logic from round_0. That block is for a near-fixed
      fair value and would fight Pepper's strong intraday drift.
    - Reuse the *conceptual* TOMATOES logic from round_0 model_v3/v4 instead:
      EMA anchor + microstructure continuation + pullback trading + asymmetric
      quoting. Then retune it for Pepper's much cleaner trend regime.
    """

    PRODUCT = "INTARIAN_PEPPER_ROOT"
    POSITION_LIMIT = 80

    # Trend anchor
    EMA_FAST_ALPHA = 0.32
    EMA_SLOW_ALPHA = 0.10
    FAST_WEIGHT = 0.55
    SLOW_WEIGHT = 0.30
    MID_WEIGHT = 0.15
    HISTORY_WINDOW = 64   # matches TREND_WINDOW — extra history beyond this was unused
    TREND_WINDOW = 64
    WARMUP_TICKS = 15     # minimum mids before trading; avoids cold-start noise
    TREND_FORECAST_HORIZON = 24
    TREND_SLOPE_CLIP = 0.18

    # Microstructure
    L2_LEVEL_WEIGHT = 0.70
    L1_IMBALANCE_BETA = 1.10
    L2_IMBALANCE_BETA = 4.40
    MICROPRICE_BETA = 1.00

    # Trade flow / continuation
    FLOW_HISTORY_WINDOW = 8
    FLOW_CONFIRM_SCALE = 14.0
    CONTINUATION_IMBALANCE = 0.18
    CONTINUATION_STRONG_IMBALANCE = 0.26
    CONTINUATION_BONUS = 1.05

    # Pullback around the moving trend line
    PULLBACK_Z_THRESHOLD = 0.90
    PULLBACK_BONUS = 1.55
    PULLBACK_IMBALANCE_BLOCK = -0.18
    STRETCH_Z_THRESHOLD = 1.55
    STRETCH_TRIM_BONUS = 0.55
    STRETCH_IMBALANCE_CONFIRM = 0.18

    # Execution / inventory
    BASE_HALF_SPREAD = 2
    VOL_MULTIPLIER = 0.45
    MIN_HALF_SPREAD = 2
    TAKE_EDGE = 1
    STRONG_SIGNAL_EXTRA_TAKE = 1
    AGGRESSIVE_CAP = 18

    TARGET_INVENTORY_MAX = 40
    INVENTORY_SKEW = 0.14
    SOFT_POSITION_LIMIT = 60
    HARD_POSITION_LIMIT = 76
    MAX_PASSIVE_SIZE = 18
    PASSIVE_REDUCTION_STEP = 5

    # Robustness / regime adaptation
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

    # Directional quoting
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
    def best_levels(order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
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

    def load_state(self, trader_data: str) -> Dict[str, List[float] | float | None]:
        default = {
            "ema_fast": None, "ema_slow": None,
            "mids": [], "flows": [],
            "prev_best_bid": None, "prev_best_ask": None,
        }
        if not trader_data:
            return {self.PRODUCT: default}
        try:
            state = json.loads(trader_data)
            p = state.setdefault(self.PRODUCT, {})
            p.setdefault("ema_fast", None)
            p.setdefault("ema_slow", None)
            p.setdefault("mids", [])
            p.setdefault("flows", [])
            p.setdefault("prev_best_bid", None)
            p.setdefault("prev_best_ask", None)
            return state
        except Exception:
            return {self.PRODUCT: default}

    @staticmethod
    def dump_state(state: Dict) -> str:
        return json.dumps(state, separators=(",", ":"))

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
                mids = mids[-self.HISTORY_WINDOW :]

        flows.append(int(current_flow))
        if len(flows) > self.FLOW_HISTORY_WINDOW:
            flows = flows[-self.FLOW_HISTORY_WINDOW :]

        product_state["ema_fast"] = ema_fast
        product_state["ema_slow"] = ema_slow
        product_state["mids"] = mids
        product_state["flows"] = flows
        return ema_fast, ema_slow, mids, flows

    def estimate_trend(self, mids: List[float]) -> Tuple[float, Optional[float], float]:
        if not mids:
            return 0.0, None, 0.0
        window = mids[-min(len(mids), self.TREND_WINDOW) :]
        n = len(window)
        if n < 5:
            return 0.0, window[-1], 0.0

        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        denom = sum((i - x_mean) ** 2 for i in range(n))
        if denom <= 0:
            return 0.0, window[-1], 0.0

        slope = sum((i - x_mean) * (window[i] - y_mean) for i in range(n)) / denom
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
        weight_sum = sum(weight for weight, _ in usable)
        anchor = sum(weight * value for weight, value in usable) / weight_sum
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

        # Buy pullbacks in an uptrend / sell pop-ups in a downtrend.
        if trend_dir > 0 and resid_z <= -self.PULLBACK_Z_THRESHOLD and l2_imbalance > self.PULLBACK_IMBALANCE_BLOCK:
            strength = self.clamp((abs(resid_z) - self.PULLBACK_Z_THRESHOLD) / 1.3 + 0.35, 0.0, 1.0)
            return self.PULLBACK_BONUS * strength
        if trend_dir < 0 and resid_z >= self.PULLBACK_Z_THRESHOLD and l2_imbalance < -self.PULLBACK_IMBALANCE_BLOCK:
            strength = self.clamp((abs(resid_z) - self.PULLBACK_Z_THRESHOLD) / 1.3 + 0.35, 0.0, 1.0)
            return -self.PULLBACK_BONUS * strength

        # On over-stretch, only trim lightly; Pepper pays more for fighting trend.
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
            0.0,
            1.0,
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

        soft_pressure = self.soft_pressure(position)
        if position >= self.SOFT_POSITION_LIMIT:
            passive_buy_size = int(math.floor(passive_buy_size * (1.0 - soft_pressure)))
        elif position <= -self.SOFT_POSITION_LIMIT:
            passive_sell_size = int(math.floor(passive_sell_size * (1.0 - soft_pressure)))

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
            ask_widen = self.OPPOSITE_WIDEN_TICKS + (1 if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD else 0)
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
            bid_widen = self.OPPOSITE_WIDEN_TICKS + (1 if visible_spread is not None and visible_spread >= self.WIDE_SPREAD_THRESHOLD else 0)
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

        # Use previous tick's book to classify market_trades (they arrived last tick).
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

        # Don't trade until we have enough history for reliable trend estimation.
        if len(mids) < self.WARMUP_TICKS:
            return orders

        trend_slope, fitted_current, resid_z = self.estimate_trend(mids)
        fair_base = self.build_fair_base(mid, ema_fast, ema_slow, trend_slope)
        if fair_base is None:
            return orders

        vol = self.realized_volatility(mids)
        l1_imbalance, l2_imbalance, micro_shift = self.depth_features(order_depth, mid, best_bid_volume, best_ask_volume)
        flow_recent = self.clamp(sum(flows[-3:]) / self.FLOW_CONFIRM_SCALE, -1.0, 1.0) if flows else 0.0

        l1_adj = self.L1_IMBALANCE_BETA * l1_imbalance
        l2_adj = self.L2_IMBALANCE_BETA * l2_imbalance
        micro_adj = self.MICROPRICE_BETA * micro_shift
        continuation_adj = self.continuation_adjustment(trend_slope, l2_imbalance, micro_shift, flow_recent)
        pullback_adj = self.pullback_adjustment(trend_slope, resid_z, l2_imbalance)

        fair_signal = fair_base + l1_adj + l2_adj + micro_adj + continuation_adj + pullback_adj
        trend_signal = fair_base - mid
        target_inventory = self.desired_inventory(
            trend_signal,
            continuation_adj,
            visible_spread,
            vol,
            l2_imbalance,
            flow_recent,
        )

        buy_capacity, sell_capacity = self.capacities(position)
        buy_hard_capacity, sell_hard_capacity = self.hard_capacities(position)

        reservation_price = fair_signal - self.INVENTORY_SKEW * (position - target_inventory)
        signal_ticks = reservation_price - mid
        half_spread = self.adaptive_half_spread(
            vol,
            visible_spread,
            trend_signal,
            continuation_adj,
            l2_imbalance,
            flow_recent,
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

        projected_position = position

        if order_depth.sell_orders and buy_capacity > 0 and buy_hard_capacity > 0:
            remaining_take = min(buy_capacity, buy_hard_capacity, self.AGGRESSIVE_CAP)
            if signal_ticks < -self.DIRECTIONAL_SIGNAL and projected_position > target_inventory:
                remaining_take = min(remaining_take, max(self.MIN_AGGRESSIVE_CAP, int(self.AGGRESSIVE_CAP * self.TREND_PROTECTION_CAP_FRACTION)))
            for ask_price in sorted(order_depth.sell_orders.keys()):
                ask_volume = -order_depth.sell_orders[ask_price]
                if remaining_take <= 0:
                    break
                if ask_price <= aggressive_buy_threshold:
                    qty = min(ask_volume, remaining_take)
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
                remaining_take = min(remaining_take, max(self.MIN_AGGRESSIVE_CAP, int(self.AGGRESSIVE_CAP * self.TREND_PROTECTION_CAP_FRACTION)))
            for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                bid_volume = order_depth.buy_orders[bid_price]
                if remaining_take <= 0:
                    break
                if bid_price >= aggressive_sell_threshold:
                    qty = min(bid_volume, remaining_take)
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
            reservation_price,
            best_bid,
            best_ask,
            desired_bid,
            desired_ask,
        )

        passive_buy_size, passive_sell_size = self.passive_sizes(
            projected_position,
            target_inventory,
            buy_capacity,
            sell_capacity,
            buy_hard_capacity,
            sell_hard_capacity,
            vol,
            visible_spread,
            trend_signal,
            continuation_adj,
        )

        passive_bid, passive_ask, passive_buy_size, passive_sell_size = self.adjust_directional_quotes(
            passive_bid,
            passive_ask,
            passive_buy_size,
            passive_sell_size,
            best_bid,
            best_ask,
            visible_spread,
            signal_ticks,
            trend_signal,
            l2_imbalance,
            micro_shift,
            continuation_adj,
            flow_recent,
            buy_capacity,
            sell_capacity,
            buy_hard_capacity,
            sell_hard_capacity,
        )

        if passive_buy_size > 0:
            self.add_order(orders, self.PRODUCT, passive_bid, passive_buy_size)
        if passive_sell_size > 0:
            self.add_order(orders, self.PRODUCT, passive_ask, -passive_sell_size)

        return orders

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        state_store = self.load_state(state.traderData)

        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)
            if product == self.PRODUCT:
                result[product] = self.trade_pepper(
                    order_depth,
                    position,
                    state_store,
                    state.market_trades.get(product, []),
                )
            else:
                result[product] = []

        trader_data = self.dump_state(state_store)
        conversions = 0
        return result, conversions, trader_data
