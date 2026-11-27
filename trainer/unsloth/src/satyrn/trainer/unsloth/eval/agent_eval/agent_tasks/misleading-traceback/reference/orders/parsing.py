"""Parse order lines. Used by the totals report and by the warehouse export."""


def parse_line(line: str) -> dict:
    """One order line, 'SKU,QUANTITY,UNIT_PRICE_CENTS', as a dict; quantity and unit_price_cents are ints."""
    sku, quantity, price = (part.strip() for part in line.split(","))
    return {"sku": sku, "quantity": int(quantity), "unit_price_cents": int(price)}
