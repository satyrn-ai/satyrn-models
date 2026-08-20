"""Tests for deduplicating tasks on their semantic_id."""

from satyrn.tstrings.dedupe import deduplicate
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


def test_deduplicate_keeps_first_per_semantic_id() -> None:
    """Tasks sharing a semantic_id collapse to the first occurrence."""
    task = _make_task()
    twin = _make_task(provenance={"source_id": "rust", "path": "src/lib.rs", "line": 3, "license": "MIT"})
    distinct = _make_task(prompt="Print a greeting.")
    assert task.semantic_id == twin.semantic_id
    assert task.task_id != twin.task_id
    kept, removed = deduplicate([task, twin, distinct])
    assert kept == [task, distinct]
    assert removed == 1


def test_deduplicate_preserves_input_order() -> None:
    """The deduped list keeps the original relative ordering."""
    first = _make_task()
    twin = _make_task(provenance={"source_id": "rust", "path": "src/lib.rs", "line": 3, "license": "MIT"})
    later = _make_task(prompt="Print a greeting.")
    kept, _ = deduplicate([later, first, twin])
    assert kept == [later, first]
