from pagination import page_count, page_items

ITEMS = list(range(10))


def test_pages_do_not_overlap():
    assert page_items(ITEMS, 1, 3) == [0, 1, 2]
    assert page_items(ITEMS, 2, 3) == [3, 4, 5]


def test_last_page_holds_the_remainder():
    assert page_items(ITEMS, 4, 3) == [9]


def test_page_count_includes_a_partial_page():
    assert page_count(10, 3) == 4
    assert page_count(1, 25) == 1


def test_page_count_of_exact_multiples_and_empty_lists():
    assert page_count(9, 3) == 3
    assert page_count(0, 3) == 0
