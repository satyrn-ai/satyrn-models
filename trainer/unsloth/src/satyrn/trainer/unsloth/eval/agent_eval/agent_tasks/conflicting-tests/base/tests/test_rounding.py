from rounding import round_price


def test_whole_amounts_are_unchanged():
    assert round_price(4.0) == 4


def test_halves_round_up():
    # Agreed with finance in ticket FIN-112
    assert round_price(2.5) == 3


def test_halves_round_to_even():
    # Banker's rounding, required by the auditors in ticket FIN-140
    assert round_price(2.5) == 2
