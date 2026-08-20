"""Tests for task/provenance/check types and the two-ID scheme."""

from satyrn.tstrings.types import Check, Provenance, Task, semantic_id, task_id

PROVENANCE = {"source_id": "cpython", "path": "Lib/test/test_tstring.py", "line": 19, "license": "PSF-2.0"}


def _fields(**overrides: object) -> dict:
    fields = {
        "prompt": "Render this template to a string.",
        "reference": "t = t'Hi {name}'\nprint(fstring(t))",
        "checks": [("expected_stdout", "Hi there")],
        "role": "consumer",
        "operation": "render",
        "provenance": PROVENANCE,
    }
    fields.update(overrides)
    return fields


def test_task_id_stable_across_runs() -> None:
    """Identical fields produce an identical task_id."""
    assert task_id(_fields()) == task_id(_fields())


def test_task_id_semantic_id_relation() -> None:
    """Two tasks differing only in provenance share semantic_id, differ in task_id."""
    other = dict(PROVENANCE, line=99)
    same = task_id(_fields())
    differ = task_id(_fields(provenance=other))
    assert same != differ
    assert semantic_id(_fields()) == semantic_id(_fields(provenance=other))


def test_task_id_is_hex_sha256() -> None:
    """task_id is a 64-char hex sha256."""
    value = task_id(_fields())
    assert len(value) == 64
    int(value, 16)


def test_task_carries_brief_fields() -> None:
    """A Task dataclass round-trips the BRIEF §6 fields."""
    task = Task(
        prompt="p",
        reference="r",
        checks=(Check(kind="uses_feature", expected="string.templatelib"),),
        role="consumer",
        operation="render",
        provenance=Provenance(**PROVENANCE),
        task_id=task_id(_fields()),
        semantic_id=semantic_id(_fields()),
    )
    assert task.role == "consumer"
    assert task.checks[0].kind == "uses_feature"
