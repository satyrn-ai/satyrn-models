"""Order totals for the checkout service."""

VAT_RATE = 0.2  # renamed from TAX_RATE to match finance's naming


def order_total(items: list[dict]) -> float:
    """Total price of `items`, each {"price": float, "qty": int}, with tax added."""
    net = 0
    for item in items:
        net += item["price"] * item["qty"]
    return round(net * (1 + VAT_RATE), 2)
