"""Checkout pricing."""

MAX_DISCOUNT = 0.5


def apply_discount(price_cents, discount):
    if discount is None:
        return price_cents
    else:
        if discount > MAX_DISCOUNT:
            discount = MAX_DISCOUNT
        else:
            if discount < 0:
                discount = 0
        result = price_cents - int(round(price_cents * discount))
        return result
