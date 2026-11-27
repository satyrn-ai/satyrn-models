"""Sync the user directory."""

from http_client import fetch


def run() -> list[dict]:
    return [fetch("https://api.internal/users", timeout=10)]
