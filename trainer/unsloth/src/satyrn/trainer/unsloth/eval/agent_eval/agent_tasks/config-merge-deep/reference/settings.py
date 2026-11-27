"""Application settings: built-in defaults, overridden per deployment."""

import copy

DEFAULTS = {
    "database": {"host": "localhost", "port": 5432, "options": {"sslmode": "prefer", "connect_timeout": 10}},
    "workers": 4,
    "allowed_hosts": ["localhost"],
}


def merge(defaults: dict, overrides: dict) -> dict:
    """Settings with `overrides` applied on top of `defaults`."""
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
