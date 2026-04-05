from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple


class Trader:
    # =========================
    # Feature flags (all ON by default)
    # =========================
    USE_EMERALDS_AGGRESSIVE = True
    USE_EMERALDS_PASSIVE = True
    USE_EMERALDS_INVENTORY_SKEW = False
    USE_EMERALDS_SIZE_SKEW = False
    USE_EMERALDS_FLATTENING = False
    USE_EMERALDS_AGGRESSIVE_FLATTENING = False

    PRODUCT = "EMERALDS"      # Cambia esto si el símbolo real es otro
    FAIR_VALUE = 10000
    POSITION_LIMIT = 80

    # Parámetros de estrategia
    TAKE_EDGE = 1             # Toma liquidez si el precio es claramente favorable
    DEFAULT_QUOTE_OFFSET = 1  # Distancia base para quotes pasivas alrededor del fair
    INVENTORY_SKEW = 0.5      # Cuánto desplazar el fair según la posición
    MAX_PASSIVE_SIZE = 6      # Tamaño máximo por quote pasiva
    EMERALDS_FLATTEN_THRESHOLD = 30
    EMERALDS_FLATTEN_SIZE = 15

    def bid(self):
        # Solo importa en Round 2; en otros rounds se ignora
        return 15

    @staticmethod
    def best_bid_ask(order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    @staticmethod
    def add_order(orders: List[Order], product: str, price: int, quantity: int) -> None:
        if quantity != 0:
            orders.append(Order(product, price, quantity))

    def capacities(self, position: int) -> Tuple[int, int]:
        buy_capacity = self.POSITION_LIMIT - position
        sell_capacity = self.POSITION_LIMIT + position
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
        Add optional inventory-flattening order at 10000 and return updated capacities.
        flatten_side:
          - "LONG"  -> flattening sell was placed (position too long)
          - "SHORT" -> flattening buy was placed (position too short)
          - None    -> no flattening order
        """
        if not self.USE_EMERALDS_FLATTENING:
            return buy_capacity, sell_capacity, None

        if position >= self.EMERALDS_FLATTEN_THRESHOLD and sell_capacity > 0:
            qty = min(self.EMERALDS_FLATTEN_SIZE, position, sell_capacity)
            self.add_order(orders, product, self.FAIR_VALUE, -qty)
            sell_capacity -= qty
            return buy_capacity, sell_capacity, "LONG"

        if position <= -self.EMERALDS_FLATTEN_THRESHOLD and buy_capacity > 0:
            qty = min(self.EMERALDS_FLATTEN_SIZE, -position, buy_capacity)
            self.add_order(orders, product, self.FAIR_VALUE, qty)
            buy_capacity -= qty
            return buy_capacity, sell_capacity, "SHORT"

        return buy_capacity, sell_capacity, None

    def make_emerald_orders(self, product: str, order_depth: OrderDepth, position: int) -> List[Order]:
        orders: List[Order] = []

        buy_capacity, sell_capacity = self.capacities(position)

        # Ajuste opcional del fair por inventario:
        # si estás largo, bajas tu fair interno para comprar menos y vender antes
        # si estás corto, lo subes para recomprar antes y vender menos agresivamente
        inv_skew = self.INVENTORY_SKEW * position if self.USE_EMERALDS_INVENTORY_SKEW else 0.0
        skewed_fair = self.FAIR_VALUE - int(round(inv_skew))

        # Umbrales para tomar liquidez
        aggressive_buy_threshold = skewed_fair - self.TAKE_EDGE
        aggressive_sell_threshold = skewed_fair + self.TAKE_EDGE

        best_bid, best_ask = self.best_bid_ask(order_depth)

        # -------------------------------------------------
        # 1-2) TAKE LIQUIDITY opcional
        # -------------------------------------------------
        if self.USE_EMERALDS_AGGRESSIVE:
            if order_depth.sell_orders and buy_capacity > 0:
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]  # en sell_orders viene negativo

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

        # -------------------------------------------------
        # 3) MARKET MAKING PASIVO alrededor del fair skewed
        # -------------------------------------------------
        # Elegimos quotes dentro del spread visible, pero sin perder ventaja
        quote_offset = self.DEFAULT_QUOTE_OFFSET

        # Bid pasivo:
        # - mejora el best bid si se puede
        # - nunca por encima de skewed_fair - 1
        if best_bid is not None:
            passive_bid = min(best_bid + 1, skewed_fair - quote_offset)
        else:
            passive_bid = skewed_fair - quote_offset

        # Ask pasivo:
        # - mejora el best ask si se puede
        # - nunca por debajo de skewed_fair + 1
        if best_ask is not None:
            passive_ask = max(best_ask - 1, skewed_fair + quote_offset)
        else:
            passive_ask = skewed_fair + quote_offset

        # Garantizar que no crucen
        if passive_bid >= passive_ask:
            passive_bid = skewed_fair - 1
            passive_ask = skewed_fair + 1

        flatten_side: Optional[str] = None
        if self.USE_EMERALDS_FLATTENING and self.USE_EMERALDS_AGGRESSIVE_FLATTENING:
            # Aggressive flattening mode: consume capacity first to reduce inventory.
            buy_capacity, sell_capacity, flatten_side = self.apply_flattening(
                orders, product, position, buy_capacity, sell_capacity
            )

        if self.USE_EMERALDS_PASSIVE:
            # Tamaños pasivos con ajuste opcional por inventario
            passive_buy_size = min(self.MAX_PASSIVE_SIZE, buy_capacity)
            passive_sell_size = min(self.MAX_PASSIVE_SIZE, sell_capacity)

            if self.USE_EMERALDS_SIZE_SKEW:
                if position > 0:
                    # Si ya estás largo, compras menos y vendes algo más
                    passive_buy_size = max(0, passive_buy_size - position // 4)
                    passive_sell_size = min(sell_capacity, passive_sell_size + position // 4)
                elif position < 0:
                    # Si ya estás corto, vendes menos y compras algo más
                    passive_sell_size = max(0, passive_sell_size - (-position) // 4)
                    passive_buy_size = min(buy_capacity, passive_buy_size + (-position) // 4)

            # In aggressive flattening mode, avoid passive quotes that worsen inventory.
            allow_passive_bid = not (flatten_side == "LONG")
            allow_passive_ask = not (flatten_side == "SHORT")

            # Quotes pasivas finales
            if allow_passive_bid and passive_buy_size > 0:
                self.add_order(orders, product, passive_bid, passive_buy_size)
                buy_capacity -= passive_buy_size

            if allow_passive_ask and passive_sell_size > 0:
                self.add_order(orders, product, passive_ask, -passive_sell_size)
                sell_capacity -= passive_sell_size

        # Normal mode: flattening happens after passive quotes (existing behavior).
        if self.USE_EMERALDS_FLATTENING and not self.USE_EMERALDS_AGGRESSIVE_FLATTENING:
            buy_capacity, sell_capacity, _ = self.apply_flattening(
                orders, product, position, buy_capacity, sell_capacity
            )

        return orders

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        for product, order_depth in state.order_depths.items():
            if product == self.PRODUCT:
                position = state.position.get(product, 0)
                result[product] = self.make_emerald_orders(product, order_depth, position)
            else:
                result[product] = []

        traderData = ""
        conversions = 0
        return result, conversions, traderData


# ------------------------------------------------------------
# Config quick guide:
# - Actual: USE_EMERALDS_FLATTENING = False.
# - Version B: USE_EMERALDS_FLATTENING = True.
# - Aggressive B: USE_EMERALDS_FLATTENING = True and
#   USE_EMERALDS_AGGRESSIVE_FLATTENING = True.
# ------------------------------------------------------------