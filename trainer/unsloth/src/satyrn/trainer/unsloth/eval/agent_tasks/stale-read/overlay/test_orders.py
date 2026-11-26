import orders


def test_quantity_is_charged():
    assert orders.order_total([{"price": 10.0, "qty": 3}]) == 36.0


def test_tax_is_added():
    assert orders.order_total([{"price": 10.0, "qty": 1}, {"price": 5.0, "qty": 2}]) == 24.0


def test_the_teammates_rename_is_kept():
    assert orders.VAT_RATE == 0.2
    assert not hasattr(orders, "TAX_RATE")
