import pytest
from discounts import loyalty_discount


def test_one_year():
    assert loyalty_discount(1) == pytest.approx(0.05)


def test_five_years_reaches_the_cap():
    assert loyalty_discount(5) == pytest.approx(0.25)


def test_new_customers_get_nothing():
    assert loyalty_discount(0) == 0


def test_the_cap_holds():
    assert loyalty_discount(12) == pytest.approx(0.25)
