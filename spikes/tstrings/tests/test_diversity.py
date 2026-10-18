"""Tests for the structural skeleton and diversity floor."""

from satyrn.tstrings.diversity import UNPARSEABLE, distinct_skeleton_ratio, skeleton, skeleton_floor
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


def test_skeleton_ignores_names_and_literals() -> None:
    """References differing only in names and literals share a skeleton."""
    first = "def f(x):\n    return x * 2\n"
    second = "def g(y):\n    return y * 3\n"
    assert skeleton(first) == skeleton(second)


def test_skeleton_distinguishes_structure() -> None:
    """Structurally different references produce different skeletons."""
    function = "def f(x):\n    return x * 2\n"
    statements = "x = 1\ny = x + 2\n"
    assert skeleton(function) != skeleton(statements)


def test_skeleton_unparseable_sentinel() -> None:
    """An unparseable reference yields the unparseable sentinel."""
    assert skeleton("def :") == UNPARSEABLE


def test_distinct_skeleton_ratio_counts_distinct_shapes() -> None:
    """The ratio is distinct skeletons over total tasks."""
    a = _make_task(reference="def f(x):\n    return x * 2\n")
    b = _make_task(reference="def g(y):\n    return y * 3\n")
    c = _make_task(reference="x = 1\n")
    assert distinct_skeleton_ratio([a, b, c]) == 2 / 3


def test_distinct_skeleton_ratio_empty_is_zero() -> None:
    """An empty task list has a zero ratio."""
    assert distinct_skeleton_ratio([]) == 0.0


def test_skeleton_floor_derives_from_measured() -> None:
    """The floor is 0.75 times the measured ratio, floored at 0.25."""
    assert skeleton_floor(0.336) == 0.252
    assert skeleton_floor(0.1) == 0.25
