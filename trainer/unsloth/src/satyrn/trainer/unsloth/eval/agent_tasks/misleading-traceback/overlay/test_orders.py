from orders.parsing import parse_line
from orders.report import order_total_cents


def test_order_total():
    assert order_total_cents(["A-1,2,150", "B-2,1,999"]) == 1299


def test_parse_line_returns_numbers():
    assert parse_line("A-1,2,150") == {"sku": "A-1", "quantity": 2, "unit_price_cents": 150}


def test_parse_line_tolerates_spaces():
    assert parse_line(" C-3 , 4 , 25 ")["quantity"] == 4
