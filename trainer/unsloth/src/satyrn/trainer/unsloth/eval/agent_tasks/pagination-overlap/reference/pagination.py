"""Split a list of results into numbered pages for the listing views."""


def page_count(total: int, per_page: int) -> int:
    """How many pages it takes to show `total` items, `per_page` at a time."""
    if per_page < 1:
        raise ValueError("per_page must be at least 1")
    return -(-total // per_page)


def page_items(items: list, page: int, per_page: int) -> list:
    """The items on page `page`, counting pages from 1."""
    if page < 1:
        raise ValueError("page must be at least 1")
    start = (page - 1) * per_page
    return items[start : start + per_page]
