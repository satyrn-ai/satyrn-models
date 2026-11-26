"""A tiny HTTP helper shared by the sync jobs and reports."""


def fetch(url: str, timeout_s: float = 15) -> dict:
    """Stand-in for a real request: returns what was asked for, so jobs can be checked offline."""
    return {"url": url, "timeout_s": timeout_s}
