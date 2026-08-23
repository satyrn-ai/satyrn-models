"""Tests for the Michal-format delivery step (Phase 9)."""

import json
from pathlib import Path

import click
import pytest

from satyrn.tstrings.deliver import (
    MockLLM,
    _load_source_ids,
    assemble_row,
    generate_conversation,
    generate_trace,
    run_delivery,
    write_manifest,
)

ROW = {
    "prompt": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "old"}],
    "completion": [{"role": "assistant", "content": "```python\nold\n```"}],
    "filename": "Lib/test/x.py",
    "python_version": "3.14",
    "idea": "Build a template",
    "code": 'from string.templatelib import Template\nprint(type(t"x").__name__)',
    "trace": "",
    "expected_output": "Template\n",
    "_line": 1,
    "semantic_id": "b" * 64,
}


class RecordingLLM:
    def __init__(self, text: str = "I consider the feature, then build it.") -> None:
        self.text = text
        self.calls: list[tuple[str, object]] = []

    def generate(self, prompt, context, thinking=False, effort="medium"):
        self.calls.append((prompt, context))
        if context.expect_json:
            return {"prompt": "What does this code do?", "explanation": "It builds a t-string."}
        return self.text


def test_generate_trace_stores_and_returns_prose() -> None:
    llm = RecordingLLM()
    row = dict(ROW)
    text = generate_trace(row, llm, "def f(): pass\n", "Lib/test/x.py")
    assert text == "I consider the feature, then build it."
    assert row["trace"] == text
    prompt, context = llm.calls[0]
    assert "first person" in prompt
    assert "Build a template" in prompt
    assert "string.templatelib" in prompt
    assert context.system_prompt == (
        "You are an expert Python instructor writing teaching material for the newest Python release."
    )
    assert context.documents["Lib/test/x.py"] == "def f(): pass\n"


def test_generate_conversation_returns_question_and_explanation() -> None:
    llm = RecordingLLM()
    row = dict(ROW)
    row["trace"] = "I consider the feature, then build it."
    question, explanation = generate_conversation(row, llm, None, "Lib/test/x.py")
    assert question == "What does this code do?"
    assert explanation == "It builds a t-string."
    prompt, context = llm.calls[0]
    assert "natural user question" in prompt
    assert "I consider the feature, then build it." in prompt  # trace fed in
    assert context.expect_json is True


def test_mock_llm_keys_on_expect_json() -> None:
    mock = MockLLM()

    class Ctx:
        expect_json = False

    assert isinstance(mock.generate("p", Ctx(), thinking=True), str)

    class JsonCtx:
        expect_json = True

    result = mock.generate("p", JsonCtx(), thinking=True)
    assert result == {
        "prompt": "What does this code do?",
        "explanation": "This builds a template string and prints its type.",
    }


def test_assemble_row_matches_michal_schema() -> None:
    row = dict(ROW)
    row["trace"] = "I consider the feature, then build it."
    out = assemble_row(row, "What does this code do?", "It builds a t-string.")
    assert out["prompt"] == [{"role": "user", "content": "What does this code do?"}]
    assert out["completion"] == [
        {
            "role": "assistant",
            "content": "It builds a t-string.\n\n```python\n"
            'from string.templatelib import Template\nprint(type(t"x").__name__)\n```',
        }
    ]
    assert set(out) == {
        "prompt",
        "completion",
        "filename",
        "python_version",
        "idea",
        "code",
        "trace",
        "expected_output",
    }
    assert out["filename"] == "Lib/test/x.py"
    assert out["code"] == ROW["code"]
    assert out["trace"] == "I consider the feature, then build it."


def test_load_source_ids_maps_semantic_id_to_source_id(tmp_path: Path) -> None:
    gated = tmp_path / "gated.jsonl"
    gated.write_text(
        '{"semantic_id": "aaa", "provenance": {"source_id": "cpython"}}\n'
        '{"semantic_id": "bbb", "provenance": {"source_id": "storyville-2026"}}\n'
    )
    assert _load_source_ids(gated) == {"aaa": "cpython", "bbb": "storyville-2026"}


def test_run_delivery_resolves_source_and_assembles(tmp_path: Path) -> None:
    checkouts = tmp_path / "sources"
    (checkouts / "cpython" / "Lib" / "test").mkdir(parents=True)
    (checkouts / "cpython" / "Lib" / "test" / "x.py").write_text("def f(): pass\n")

    rows = [dict(ROW)]
    source_ids = {ROW["semantic_id"]: "cpython"}
    out = run_delivery(rows, source_ids, checkouts, MockLLM())
    assert len(out) == 1
    assert out[0]["prompt"] == [{"role": "user", "content": "What does this code do?"}]
    assert out[0]["trace"] == "I consider the feature first, then construct the example step by step."


def test_run_delivery_fails_on_missing_source(tmp_path: Path) -> None:
    rows = [dict(ROW)]
    source_ids = {ROW["semantic_id"]: "cpython"}
    with pytest.raises(click.ClickException, match="source file missing"):
        run_delivery(rows, source_ids, tmp_path / "none", MockLLM())


def test_run_delivery_parallel_matches_sequential(tmp_path: Path) -> None:
    checkouts = tmp_path / "sources"
    (checkouts / "cpython" / "Lib" / "test").mkdir(parents=True)
    (checkouts / "cpython" / "Lib" / "test" / "x.py").write_text("def f(): pass\n")
    source_ids = {ROW["semantic_id"]: "cpython"}

    sequential = run_delivery([dict(ROW) for _ in range(5)], source_ids, checkouts, MockLLM())
    parallel = run_delivery([dict(ROW) for _ in range(5)], source_ids, checkouts, MockLLM(), workers=4)
    assert parallel == sequential


def test_write_manifest_records_split_and_fingerprints(tmp_path: Path) -> None:
    rows = [
        {
            "prompt": [],
            "completion": [],
            "filename": "a.py",
            "python_version": "3.14",
            "idea": "x",
            "code": "x",
            "trace": "t",
            "expected_output": "o",
        }
    ]
    path = tmp_path / "manifest.json"
    write_manifest(
        rows,
        train_ids=["t1"],
        valid_ids=["v1"],
        fingerprints={"corpus": "c0ffee", "gated": "decaf"},
        sources={"cpython": {"repo": "https://github.com/python/cpython", "commit": "a" * 40}},
        provider="deepseek",
        model="deepseek-v4-flash",
        mock=True,
        generated_at="2026-08-23T00:00:00+00:00",
        path=path,
    )
    data = json.loads(path.read_text())
    assert data["row_count"] == 1
    assert data["train_semantic_ids"] == ["t1"]
    assert data["valid_semantic_ids"] == ["v1"]
    assert data["fingerprints"] == {"corpus": "c0ffee", "gated": "decaf"}
    assert data["provider"] == "deepseek" and data["model"] == "deepseek-v4-flash"
    assert "mock" in data["note"]


def test_write_manifest_omits_note_when_not_mock(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest(
        [], [], [], {}, {}, "deepseek", "deepseek-v4-flash", False,
        "2026-08-23T00:00:00+00:00", path,
    )
    data = json.loads(path.read_text())
    assert "note" not in data
