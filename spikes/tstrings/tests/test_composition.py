"""Tests for the composition floor over deduplicated tasks."""

import pytest

from satyrn.tstrings.composition import cell_counts, check_composition
from satyrn.tstrings.types import Check, Provenance, Task, semantic_id, task_id

PROVENANCE = {"source_id": "cpython", "path": "Lib/test/test_tstring.py", "line": 19, "license": "PSF-2.0"}


def _make_task(**overrides: object) -> Task:
    fields = {
        "prompt": "Render this template to a string.",
        "reference": "t = t'Hi {name}'\nprint(fstring(t))",
        "checks": [("expected_stdout", "Hi there")],
        "role": "consumer",
        "operation": "render",
        "provenance": PROVENANCE,
    }
    fields.update(overrides)
    return Task(
        prompt=fields["prompt"],
        reference=fields["reference"],
        checks=tuple(Check(kind=kind, expected=expected) for kind, expected in fields["checks"]),
        role=fields["role"],
        operation=fields["operation"],
        provenance=Provenance(**fields["provenance"]),
        task_id=task_id(fields),
        semantic_id=semantic_id(fields),
    )


def test_cell_counts_tallies_role_operation() -> None:
    """cell_counts groups tasks by their (role, operation) cell."""
    a = _make_task(role="author", operation="construct")
    b = _make_task(role="consumer", operation="read_strings")
    c = _make_task(role="consumer", operation="read_strings")
    assert cell_counts([a, b, c]) == {
        ("author", "construct"): 1,
        ("consumer", "read_strings"): 2,
    }


def test_cell_counts_empty_is_empty() -> None:
    """An empty task list has no cells."""
    assert cell_counts([]) == {}


def test_check_composition_passes_at_or_above_floor() -> None:
    """check_composition is a no-op when every cell meets its floor."""
    a = _make_task(role="author", operation="construct")
    b = _make_task(role="consumer", operation="render")
    floors = {("author", "construct"): 1, ("consumer", "render"): 1}
    assert check_composition([a, b], floors) is None


def test_check_composition_raises_naming_the_starved_cell() -> None:
    """A cell below its floor raises ValueError naming that cell."""
    task = _make_task(role="author", operation="construct")
    with pytest.raises(ValueError, match=r"\(author, construct\)"):
        check_composition([task], {("author", "construct"): 2})


def test_check_composition_flags_a_cell_with_zero_tasks() -> None:
    """A floor for a cell absent from the tasks also raises."""
    task = _make_task(role="author", operation="construct")
    with pytest.raises(ValueError, match=r"\(consumer, render\)"):
        check_composition([task], {("consumer", "render"): 1})
