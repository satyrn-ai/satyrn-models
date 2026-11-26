from pricing import apply_discount


def test_discount_is_capped_at_half():
    assert apply_discount(1000, 0.8) == 500
    assert apply_discount(1000, 1.0) == 500


def test_negative_and_missing_discounts():
    assert apply_discount(1000, -0.2) == 1000
    assert apply_discount(1000, None) == 1000


def test_ordinary_discount():
    assert apply_discount(1000, 0.25) == 750
