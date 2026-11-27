from app import load


def test_top_level_override():
    assert load({"workers": 8})["workers"] == 8


def test_lists_are_replaced_not_extended():
    assert load({"allowed_hosts": ["example.com"]})["allowed_hosts"] == ["example.com"]
