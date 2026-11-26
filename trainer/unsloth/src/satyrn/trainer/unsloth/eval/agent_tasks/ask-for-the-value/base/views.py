"""Listing views."""

import config


def page_size(requested: int | None) -> int:
    if requested is None:
        return config.PAGE_SIZE
    return max(1, min(requested, config.MAX_PAGE_SIZE))
