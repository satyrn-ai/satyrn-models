"""Helpers for running work in parallel."""

import math


def split_workers(worker_count: int) -> tuple[int, int]:
    """Split worker_count into a near-square (rows, cols) grid, rows * cols <= worker_count."""
    rows = math.isqrt(worker_count)
    return rows, worker_count // rows
