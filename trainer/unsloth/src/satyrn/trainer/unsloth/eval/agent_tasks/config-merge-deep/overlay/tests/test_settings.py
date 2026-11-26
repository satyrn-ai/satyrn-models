from app import load


def test_top_level_override():
    assert load({"workers": 8})["workers"] == 8


def test_lists_are_replaced_not_extended():
    assert load({"allowed_hosts": ["example.com"]})["allowed_hosts"] == ["example.com"]


def test_nested_override_keeps_siblings():
    database = load({"database": {"port": 6543}})["database"]
    assert database["port"] == 6543
    assert database["host"] == "localhost"
    assert database["options"] == {"sslmode": "prefer", "connect_timeout": 10}


def test_deeply_nested_override():
    options = load({"database": {"options": {"sslmode": "require"}}})["database"]["options"]
    assert options == {"sslmode": "require", "connect_timeout": 10}


def test_one_load_never_changes_another():
    first = load({"database": {"port": 1}, "allowed_hosts": ["a"]})
    first["database"]["options"]["sslmode"] = "disable"
    first["allowed_hosts"].append("b")
    fresh = load({})
    assert fresh["database"] == {
        "host": "localhost",
        "port": 5432,
        "options": {"sslmode": "prefer", "connect_timeout": 10},
    }
    assert fresh["allowed_hosts"] == ["localhost"]
