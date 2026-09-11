"""Tests for the cell table and deterministic operation analysis."""

from satyrn.tstrings.cells import CELLS, operations_of


def test_six_cells_no_compose() -> None:
    """The cell table has exactly six cells and no compose."""
    assert len(CELLS) == 6
    assert ("author", "compose") not in CELLS
    assert ("author", "construct") in CELLS


def test_operations_of_render_seed() -> None:
    """A render seed demonstrates render plus read_strings and read_values."""
    text = 'name = "Python"\nt = t"Hello, {name}"\nself.assertEqual(fstring(t), \'Hello, Python\')\n'
    assert operations_of(text) == {"construct", "render", "read_strings", "read_values"}


def test_operations_of_values_seed() -> None:
    """A .values seed demonstrates construct and read_values only."""
    text = 't = t"Hello, {name}"\nself.assertEqual(t.values, ("Lys",))\n'
    assert operations_of(text) == {"construct", "read_values"}


def test_operations_of_annotation_seed_is_empty() -> None:
    """A t-string inside an annotation context yields no clean operation."""
    text = 'def f(x: t"{a}"): pass\n'
    assert operations_of(text) == set()


def test_return_annotation_is_annotation_context() -> None:
    """A t-string in a return annotation yields no clean operation."""
    assert operations_of('def f() -> t"{a}": pass\n') == set()
