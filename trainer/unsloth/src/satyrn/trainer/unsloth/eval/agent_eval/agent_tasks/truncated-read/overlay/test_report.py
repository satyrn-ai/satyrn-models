import inspect

import legacy_report


def test_amount_is_in_currency_units():
    assert legacy_report.format_amount({"amount": 1234}) == "12.34"
    assert legacy_report.format_amount({"amount": 5}) == "0.05"


def test_missing_amount_is_empty():
    assert legacy_report.format_amount({}) == ""


def test_other_columns_are_unchanged():
    formatters = [name for name, _ in inspect.getmembers(legacy_report, inspect.isfunction)]
    assert len(formatters) == 400
    for name in ("col_000", "col_299", "col_301", "col_399"):
        assert getattr(legacy_report, f"format_{name}")({name: 1234}) == "1234"
        assert getattr(legacy_report, f"format_{name}")({}) == ""
