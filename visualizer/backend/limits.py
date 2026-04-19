KNOWN_LIMITS = {
    # Prosperity 4
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
    # Prosperity 3
    "RAINFOREST_RESIN": 50,
    "KELP": 50,
    "SQUID_INK": 50,
    "CROISSANTS": 250,
    "JAMS": 350,
    "DJEMBES": 60,
    "PICNIC_BASKET1": 60,
    "PICNIC_BASKET2": 100,
    "VOLCANIC_ROCK": 400,
    "VOLCANIC_ROCK_VOUCHER_9500": 200,
    "VOLCANIC_ROCK_VOUCHER_9750": 200,
    "VOLCANIC_ROCK_VOUCHER_10000": 200,
    "VOLCANIC_ROCK_VOUCHER_10250": 200,
    "VOLCANIC_ROCK_VOUCHER_10500": 200,
    "MAGNIFICENT_MACARONS": 75,
    # Prosperity 2 / 1 era
    "AMETHYSTS": 20,
    "STARFRUIT": 20,
    "ORCHIDS": 100,
    "CHOCOLATE": 250,
    "STRAWBERRIES": 350,
    "ROSES": 60,
    "GIFT_BASKET": 60,
    "COCONUT": 300,
    "COCONUT_COUPON": 600,
    # Tutorial / local datasets
    "EMERALDS": 80,
    "TOMATOES": 80,
}


def default_limit(product: str) -> int:
    return KNOWN_LIMITS.get(product, 80)


def build_limits(products: list[str]) -> dict[str, int]:
    return {product: default_limit(product) for product in products}
