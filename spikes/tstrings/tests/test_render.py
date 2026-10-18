"""Tests for rendering qualified tasks as converged SFT rows."""

import json
from pathlib import Path

import pytest

from satyrn.tstrings.render import contamination_check, generate_trace, render_tasks
from satyrn.tstrings.types import Check, Provenance, Task

SYSTEM = (
    "You are a precise Python 3.14 programmer. Use template strings (t-strings, PEP 750) "
    "where a template is appropriate, and plain f-strings otherwise. "
    "Write complete, runnable code and nothing else.\n"
)

PROV = Provenance(source_id="cpython", path="Lib/test/x.py", line=1, license="PSF-2.0")


def _task(**overrides: object) -> Task:
    fields = {
        "prompt": "Build a template",
        "reference": 'from string.templatelib import Template\nprint(type(t"x").__name__)',
        "checks": (
            Check(kind="uses_feature", expected="string.templatelib"),
            Check(kind="expected_stdout", expected="Template"),
        ),
        "role": "consumer",
        "operation": "render",
        "provenance": PROV,
        "task_id": "a" * 64,
        "semantic_id": "b" * 64,
    }
    fields.update(overrides)
    return Task(**fields)  # type: ignore[arg-type]


def test_render_row_shape() -> None:
    """Render a task into the converged row shape from the spec's ruling 2."""
    rows = render_tasks([_task()], SYSTEM)
    row = rows[0]
    assert row["prompt"] == [
        {"role": "system", "content": SYSTEM.strip()},
        {"role": "user", "content": "Build a template"},
    ]
    assert row["completion"][0]["role"] == "assistant"
    assert "```python" in row["completion"][0]["content"]
    assert row["filename"] == PROV.path and row["python_version"] == "3.14"
    assert row["idea"] == "Build a template" and row["code"] == _task().reference
    assert row["expected_output"] == "Template" and row["trace"] == ""


def test_expected_output_falls_back_to_empty() -> None:
    """A task without an expected_stdout check renders an empty expected_output."""
    task = _task(checks=(Check(kind="uses_feature", expected="string.templatelib"),))
    rows = render_tasks([task], SYSTEM)
    assert rows[0]["expected_output"] == ""


def test_contamination_check_raises_on_pair_overlap(tmp_path: Path) -> None:
    """A rendered (idea, code) pair in the benchmark raises ValueError (ground rule 2.4)."""
    task = _task()
    rows = render_tasks([task], SYSTEM)
    benchmark = tmp_path / "tasks.jsonl"
    benchmark.write_text(json.dumps({"prompt": task.prompt, "reference": task.reference}) + "\n")
    with pytest.raises(ValueError):
        contamination_check(rows, benchmark)


def test_contamination_check_raises_on_bare_code_overlap(tmp_path: Path) -> None:
    """A rendered code string among the benchmark references raises ValueError."""
    task = _task()
    rows = render_tasks([task], SYSTEM)
    benchmark = tmp_path / "tasks.jsonl"
    benchmark.write_text(json.dumps({"prompt": "unrelated", "reference": task.reference}) + "\n")
    with pytest.raises(ValueError):
        contamination_check(rows, benchmark)


def test_contamination_check_passes_on_clean_benchmark(tmp_path: Path) -> None:
    """A benchmark with no overlap does not raise."""
    task = _task()
    rows = render_tasks([task], SYSTEM)
    benchmark = tmp_path / "tasks.jsonl"
    benchmark.write_text(json.dumps({"prompt": "unrelated", "reference": "print('unrelated')\n"}) + "\n")
    contamination_check(rows, benchmark)


def test_generate_trace_returns_prose_and_sets_row_trace() -> None:
    """generate_trace stores the LLM's prose in the row and returns it."""

    class FakeLLM:
        def generate(self, prompt, context):
            self.prompt = prompt
            self.context = context
            return "I start by importing Template and constructing a t-string."

    row = render_tasks([_task()], SYSTEM)[0]
    fake = FakeLLM()
    text = generate_trace(row, fake)
    assert text == "I start by importing Template and constructing a t-string."
    assert row["trace"] == text
    assert "Build a template" in fake.prompt
    assert "string.templatelib" in fake.prompt
    assert fake.context.system_prompt == (
        "You are writing a first-person reasoning trace for a Python teaching example."
    )
