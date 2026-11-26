"""Daily report download."""

import http_client


def run() -> dict:
    return http_client.fetch("https://api.internal/reports/daily", timeout=60)
