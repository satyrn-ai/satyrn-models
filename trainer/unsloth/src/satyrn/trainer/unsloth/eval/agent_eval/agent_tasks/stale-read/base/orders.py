"""Order totals for the checkout service."""

TAX_RATE = 0.2


def order_total(items: list[dict]) -> float:
    """Total price of `items`, each {"price": float, "qty": int}, with tax added."""
    subtotal = 0
    for item in items:
        subtotal += item["price"]
    return round(subtotal * (1 + TAX_RATE), 2)
