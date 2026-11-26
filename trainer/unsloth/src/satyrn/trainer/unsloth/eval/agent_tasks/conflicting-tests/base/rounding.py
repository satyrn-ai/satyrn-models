"""Rounding rules for invoice amounts."""


def round_price(value: float) -> int:
    """Whole currency units, with halves rounded up."""
    return int(value + 0.5)
