"""Sync open orders, one region at a time."""

from http_client import fetch

REGIONS = ["eu", "us", "apac"]


def run() -> list[dict]:
    responses = []
    for region in REGIONS:
        responses.append(fetch(f"https://api.internal/orders/{region}", timeout_s=30))
    return responses
