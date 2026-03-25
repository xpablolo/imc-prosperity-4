from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple


class Trader:
    PRODUCT = "EMERALDS"      # Cambia esto si el símbolo real es otro
    FAIR_VALUE = 10000
    POSITION_LIMIT = 20

    # Parámetros de estrategia
    TAKE_EDGE = 1             # Toma liquidez si el precio es claramente favorable
    DEFAULT_QUOTE_OFFSET = 3  # Distancia base para quotes pasivas alrededor del fair
    INVENTORY_SKEW = 0.5      # Cuánto desplazar el fair según la posición
    MAX_PASSIVE_SIZE = 6      # Tamaño máximo por quote pasiva

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

    def make_emerald_orders(self, product: str, order_depth: OrderDepth, position: int) -> List[Order]:
        orders: List[Order] = []

        buy_capacity = self.POSITION_LIMIT - position
        sell_capacity = self.POSITION_LIMIT + position

        # Ajuste del fair por inventario:
        # si estás largo, bajas tu fair interno para comprar menos y vender antes
        # si estás corto, lo subes para recomprar antes y vender menos agresivamente
        skewed_fair = self.FAIR_VALUE - int(round(self.INVENTORY_SKEW * position))

        # Umbrales para tomar liquidez
        aggressive_buy_threshold = skewed_fair - self.TAKE_EDGE
        aggressive_sell_threshold = skewed_fair + self.TAKE_EDGE

        best_bid, best_ask = self.best_bid_ask(order_depth)

        # -------------------------------------------------
        # 1) TAKE LIQUIDITY: comprar asks claramente baratos
        # -------------------------------------------------
        if order_depth.sell_orders and buy_capacity > 0:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                ask_volume = -order_depth.sell_orders[ask_price]  # en sell_orders viene negativo

                if ask_price <= aggressive_buy_threshold and buy_capacity > 0:
                    qty = min(ask_volume, buy_capacity)
                    self.add_order(orders, product, ask_price, qty)
                    buy_capacity -= qty
                else:
                    break

        # -------------------------------------------------
        # 2) TAKE LIQUIDITY: vender bids claramente caros
        # -------------------------------------------------
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

        # Tamaños pasivos con ajuste por inventario
        passive_buy_size = min(self.MAX_PASSIVE_SIZE, buy_capacity)
        passive_sell_size = min(self.MAX_PASSIVE_SIZE, sell_capacity)

        if position > 0:
            # Si ya estás largo, compras menos y vendes algo más
            passive_buy_size = max(0, passive_buy_size - position // 4)
            passive_sell_size = min(sell_capacity, passive_sell_size + position // 4)
        elif position < 0:
            # Si ya estás corto, vendes menos y compras algo más
            passive_sell_size = max(0, passive_sell_size - (-position) // 4)
            passive_buy_size = min(buy_capacity, passive_buy_size + (-position) // 4)

        # Quotes pasivas finales
        if passive_buy_size > 0:
            self.add_order(orders, product, passive_bid, passive_buy_size)

        if passive_sell_size > 0:
            self.add_order(orders, product, passive_ask, -passive_sell_size)

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