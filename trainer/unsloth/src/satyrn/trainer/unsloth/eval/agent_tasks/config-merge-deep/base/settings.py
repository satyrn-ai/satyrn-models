"""Application settings: built-in defaults, overridden per deployment."""

DEFAULTS = {
    "database": {"host": "localhost", "port": 5432, "options": {"sslmode": "prefer", "connect_timeout": 10}},
    "workers": 4,
    "allowed_hosts": ["localhost"],
}


def merge(defaults: dict, overrides: dict) -> dict:
    """Settings with `overrides` applied on top of `defaults`."""
    merged = dict(defaults)
    merged.update(overrides)
    return merged
