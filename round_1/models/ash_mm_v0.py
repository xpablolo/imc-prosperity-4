from __future__ import annotations

import json
import math
from typing import Dict, List, Optional, Tuple

try:
    from datamodel import OrderDepth, Order, TradingState
except ImportError:  # pragma: no cover
    from round_1.models.datamodel import OrderDepth, Order, TradingState


class Trader:
    """
    Market maker for ASH_COATED_OSMIUM.

    Design principles:
    - Start from the best-performing EMERALDS block observed in round_0 results
      (`model_v4` had the best EMERALDS PnL among the saved result CSVs).
    - Keep the logic stationary / mean-reverting because the round_1 data shows
      Ash behaves like a fair-value asset around ~10_000 rather than a trend asset.
    - Add only a *slow* anchor adaptation so the bot can absorb small session-level
      shifts without chasing microstructure noise.
    """

    PRODUCT = "ASH_COATED_OSMIUM"

    # Assumption: repo does not include explicit round_1 limits; we keep 80 by
    # analogy with round_0 fixed-fair products and tutorial settings.
    POSITION_LIMIT = 80

    # Core fair-value configuration
    BASE_FAIR = 10_000.0
    USE_SLOW_ANCHOR = True
    ANCHOR_ALPHA = 0.03
    ANCHOR_CLIP_TICKS = 6.0

    # Aggressive taking
    TAKE_EDGE = 0.0
    MARGINAL_TAKE_TOLERANCE = 0.40
    FAIR_REPAIR_MIN_POSITION = 6
    FAIR_UNWIND_SAME_PRICE_VOLUME = 20

    # Passive quoting
    DEFAULT_QUOTE_OFFSET = 1
    INVENTORY_SKEW_TICKS = 3.5
    MAX_PASSIVE_SIZE = 20
    SIZE_PRESSURE = 1.20

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
    def clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def capacities(self, position: int) -> Tuple[int, int]:
        return max(0, self.POSITION_LIMIT - position), max(0, self.POSITION_LIMIT + position)

    def load_state(self, trader_data: str) -> Dict[str, float | None]:
        default_state: Dict[str, float | None] = {"anchor": None, "tick": 0}
        if not trader_data:
            return default_state
        try:
            parsed = json.loads(trader_data)
            if not isinstance(parsed, dict):
                return default_state
            return {"anchor": parsed.get("anchor"), "tick": parsed.get("tick", 0)}
        except Exception:
            return default_state

    @staticmethod
    def dump_state(state: Dict[str, float | None]) -> str:
        return json.dumps(state, separators=(",", ":"))

    def update_anchor(self, product_state: Dict[str, float | None], mid: Optional[float]) -> float:
        anchor = product_state.get("anchor")
        if anchor is None:
            anchor = self.BASE_FAIR

        if self.USE_SLOW_ANCHOR and mid is not None:
            # Adaptive alpha: fast warmup for the first ~20 ticks, then settle to ANCHOR_ALPHA.
            # This lets the anchor reach the true session fair value quickly instead of
            # spending the first 30 ticks slowly drifting from BASE_FAIR = 10_000.
            tick = int(product_state.get("tick", 0))
            alpha = max(self.ANCHOR_ALPHA, min(0.25, 3.0 / (tick + 1))) if tick < 20 else self.ANCHOR_ALPHA
            anchor = alpha * mid + (1.0 - alpha) * float(anchor)

        tick = int(product_state.get("tick", 0))
        product_state["tick"] = tick + 1

        clipped_anchor = self.clamp(float(anchor), self.BASE_FAIR - self.ANCHOR_CLIP_TICKS, self.BASE_FAIR + self.ANCHOR_CLIP_TICKS)
        product_state["anchor"] = clipped_anchor
        return clipped_anchor

    def reservation_price(self, anchor_fair: float, position: int) -> float:
        inventory_ratio = position / self.POSITION_LIMIT if self.POSITION_LIMIT > 0 else 0.0
        inventory_ratio = self.clamp(inventory_ratio, -1.0, 1.0)
        return anchor_fair - self.INVENTORY_SKEW_TICKS * inventory_ratio

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
                best_bid == anchor_price and best_bid_volume is not None and best_bid_volume >= self.FAIR_UNWIND_SAME_PRICE_VOLUME
            )
            return strong_inventory_repair or strong_same_price_unwind

        if position <= 0:
            return False
        strong_same_price_unwind = (
            best_ask == anchor_price and best_ask_volume is not None and best_ask_volume >= self.FAIR_UNWIND_SAME_PRICE_VOLUME
        )
        return strong_inventory_repair or strong_same_price_unwind

    @staticmethod
    def fair_repair_quantity(side: str, position: int) -> int:
        if side == "BUY" and position < 0:
            return abs(position)
        if side == "SELL" and position > 0:
            return abs(position)
        return 0

    def passive_sizes(self, position: int, buy_capacity: int, sell_capacity: int) -> Tuple[int, int]:
        passive_buy_size = min(self.MAX_PASSIVE_SIZE, buy_capacity)
        passive_sell_size = min(self.MAX_PASSIVE_SIZE, sell_capacity)

        long_pressure = max(0.0, position / self.POSITION_LIMIT) if self.POSITION_LIMIT > 0 else 0.0
        short_pressure = max(0.0, -position / self.POSITION_LIMIT) if self.POSITION_LIMIT > 0 else 0.0

        buy_scale = self.clamp(1.0 - self.SIZE_PRESSURE * long_pressure, 0.0, 1.0)
        sell_scale = self.clamp(1.0 - self.SIZE_PRESSURE * short_pressure, 0.0, 1.0)

        passive_buy_size = min(passive_buy_size, int(round(self.MAX_PASSIVE_SIZE * buy_scale)))
        passive_sell_size = min(passive_sell_size, int(round(self.MAX_PASSIVE_SIZE * sell_scale)))
        return max(0, passive_buy_size), max(0, passive_sell_size)

    def trade_ash(self, product: str, order_depth: OrderDepth, position: int, anchor_fair: float) -> List[Order]:
        orders: List[Order] = []
        best_bid, best_bid_volume, best_ask, best_ask_volume = self.best_levels(order_depth)
        buy_capacity, sell_capacity = self.capacities(position)
        projected_position = position

        if order_depth.sell_orders and buy_capacity > 0:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                ask_volume = -order_depth.sell_orders[ask_price]
                reservation = self.reservation_price(anchor_fair, projected_position)
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
                        "BUY",
                        ask_price,
                        anchor_fair,
                        projected_position,
                        best_bid,
                        best_bid_volume,
                        best_ask,
                        best_ask_volume,
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
                reservation = self.reservation_price(anchor_fair, projected_position)
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
                        "SELL",
                        bid_price,
                        anchor_fair,
                        projected_position,
                        best_bid,
                        best_bid_volume,
                        best_ask,
                        best_ask_volume,
                    )
                    and sell_capacity > 0
                ):
                    qty = min(bid_volume, sell_capacity, self.fair_repair_quantity("SELL", projected_position))
                    self.add_order(orders, product, bid_price, -qty)
                    sell_capacity -= qty
                    projected_position -= qty
                    continue
                break

        reservation = self.reservation_price(anchor_fair, projected_position)
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
        if passive_buy_size > 0:
            self.add_order(orders, product, passive_bid, passive_buy_size)
        if passive_sell_size > 0:
            self.add_order(orders, product, passive_ask, -passive_sell_size)

        return orders

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        product_state = self.load_state(state.traderData)

        order_depth = state.order_depths.get(self.PRODUCT)
        if order_depth is not None:
            best_bid, _, best_ask, _ = self.best_levels(order_depth)
            mid = self.compute_mid(best_bid, best_ask)
            anchor_fair = self.update_anchor(product_state, mid)
            position = state.position.get(self.PRODUCT, 0)
            result[self.PRODUCT] = self.trade_ash(self.PRODUCT, order_depth, position, anchor_fair)
        else:
            result[self.PRODUCT] = []

        conversions = 0
        trader_data = self.dump_state(product_state)
        return result, conversions, trader_data
