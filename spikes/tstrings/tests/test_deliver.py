"""Tests for the Michal-format delivery step (Phase 9)."""

import json
from pathlib import Path

from satyrn.tstrings.deliver import (
    MockLLM,
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


def _row(**overrides: object) -> dict:
    row = dict(ROW)
    row.update(overrides)
    return row


def test_generate_trace_stores_and_returns_prose() -> None:
    llm = RecordingLLM()
    row = _row()
    text = generate_trace(row, llm)
    assert text == "I consider the feature, then build it."
    assert row["trace"] == text
    prompt, context = llm.calls[0]
    assert "first person" in prompt
    assert "Build a template" in prompt
    assert "string.templatelib" in prompt
    assert context.system_prompt == (
        "You are an expert Python instructor writing teaching material for the newest Python release."
    )
    assert context.documents == {}


def test_generate_conversation_returns_question_and_explanation() -> None:
    llm = RecordingLLM()
    row = _row(trace="I consider the feature, then build it.")
    question, explanation = generate_conversation(row, llm)
    assert question == "What does this code do?"
    assert explanation == "It builds a t-string."
    prompt, context = llm.calls[0]
    assert "natural user question" in prompt
    assert "must match" in prompt  # anchoring to the idea
    assert "I consider the feature, then build it." in prompt  # trace fed in
    assert context.expect_json is True


def test_generate_conversation_handles_json_string_response() -> None:
    class StrLLM:
        def generate(self, prompt, context, thinking=False, effort="medium"):
            return json.dumps({"prompt": "Q?", "explanation": "E."})

    question, explanation = generate_conversation(_row(), StrLLM())
    assert (question, explanation) == ("Q?", "E.")


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
    row = _row(trace="I consider the feature, then build it.")
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


def test_run_delivery_delivers_all_rows_in_order(tmp_path: Path) -> None:
    rows = [_row(semantic_id=f"id{i}") for i in range(3)]
    delivered, complete = run_delivery(rows, RecordingLLM(), tmp_path)
    assert complete is True
    assert [r["prompt"][0]["content"] for r in delivered] == ["What does this code do?"] * 3
    assert (tmp_path / "_checkpoint.jsonl").exists()


def test_run_delivery_resumes_skipping_completed(tmp_path: Path) -> None:
    # Pre-populate the checkpoint with row "id1" already delivered.
    checkpoint = tmp_path / "_checkpoint.jsonl"
    done_row = assemble_row(_row(semantic_id="id1"), "Done?", "Done.")
    checkpoint.write_text(json.dumps({"semantic_id": "id1", "row": done_row}) + "\n")

    llm = RecordingLLM()
    rows = [_row(semantic_id="id0"), _row(semantic_id="id1"), _row(semantic_id="id2")]
    delivered, complete = run_delivery(rows, llm, tmp_path)
    assert complete is True
    # Only two rows were generated (id1 was skipped).
    assert len(llm.calls) == 4  # 2 rows x 2 calls
    assert delivered[1]["prompt"][0]["content"] == "Done?"


def test_run_delivery_isolates_failures(tmp_path: Path) -> None:
    class FlakyLLM:
        def generate(self, prompt, context, thinking=False, effort="medium"):
            if "IDEA-MARKER" in prompt:
                raise RuntimeError("boom")
            if context.expect_json:
                return {"prompt": "Q?", "explanation": "E."}
            return "trace"

    rows = [_row(semantic_id="id0", idea="IDEA-MARKER"), _row(semantic_id="id1")]
    delivered, complete = run_delivery(rows, FlakyLLM(), tmp_path)
    assert complete is False
    assert len(delivered) == 1  # only id1 delivered; id0 failed and is retryable


def test_run_delivery_parallel_matches_sequential(tmp_path: Path) -> None:
    rows = [_row(semantic_id=f"id{i}") for i in range(5)]
    seq, _ = run_delivery(rows, MockLLM(), tmp_path / "seq")
    par, _ = run_delivery(rows, MockLLM(), tmp_path / "par", workers=4)
    assert par == seq


def test_run_delivery_reports_progress(capsys, tmp_path: Path) -> None:
    rows = [_row(semantic_id=f"id{i}") for i in range(6)]
    run_delivery(rows, MockLLM(), tmp_path, progress_every=3)
    out = capsys.readouterr().out
    assert "progress: 3/6" in out
    assert "progress: 6/6" in out


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
        generated_at="2026-08-23T00:00:00+00:00",
        note="mock",
        path=path,
    )
    data = json.loads(path.read_text())
    assert data["row_count"] == 1
    assert data["train_semantic_ids"] == ["t1"]
    assert data["valid_semantic_ids"] == ["v1"]
    assert data["note"] == "mock"


def test_write_manifest_omits_note_when_absent(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_manifest([], [], [], {}, {}, "deepseek", "deepseek-v4-flash", "2026-08-23T00:00:00+00:00", path)
    data = json.loads(path.read_text())
    assert "note" not in data
