"""Customer discounts."""


def loyalty_discount(years: int) -> float:
    """The loyalty discount for a customer of `years` years, as a fraction of the price."""
    return min(years * 0.05, 0.25)
