"""Entry point the services use to read their settings."""

from settings import DEFAULTS, merge


def load(overrides: dict) -> dict:
    """This deployment's settings."""
    return merge(DEFAULTS, overrides)
