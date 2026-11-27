"""Nightly order totals."""

from orders.parsing import parse_line


def order_total_cents(lines: list[str]) -> int:
    total = 0
    for line in lines:
        item = parse_line(line)
        total += item["quantity"] * item["unit_price_cents"]
    return total
