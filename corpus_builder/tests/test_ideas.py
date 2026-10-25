"""Tests for the ``ideas`` command and the shared idea loading helpers.

The branch splits idea generation out of ``sft``/``rl`` into its own command that
writes a JSONL file of ``Idea`` rows.  ``sft`` and ``rl`` then load those rows
back with :func:`load_ideas`.  These tests cover both halves of that contract
without touching the network or Docker.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from satyrn.dataset import ideas
from satyrn.dataset.llm.models import SchemaValidationError
from satyrn.dataset.utils.generation import Idea, load_ideas, read_jsonl_file


class StubModel:
    """A minimal Model whose ``generate`` returns a canned response."""

    def __init__(self, response: dict | Exception) -> None:
        self.response = response
        self.calls = 0

    def generate(self, prompt: str, context: Any, thinking: bool = False, effort: str = "medium") -> Any:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def write_ideas_file(path: Path, ideas: list[dict]) -> Path:
    """Write idea rows to a JSONL file."""
    with path.open("w", encoding="utf-8") as handle:
        for idea in ideas:
            handle.write(json.dumps(idea) + "\n")
    return path


# --- shared loading helpers -------------------------------------------------


def test_read_jsonl_file_yields_each_object(tmp_path: Path) -> None:
    path = write_ideas_file(tmp_path / "ideas.jsonl", [{"a": 1}, {"b": 2}])

    assert list(read_jsonl_file(path)) == [{"a": 1}, {"b": 2}]


def test_load_ideas_round_trips_idea_fields_and_path_type(tmp_path: Path) -> None:
    doc = tmp_path / "PEP750.rst"
    path = write_ideas_file(
        tmp_path / "ideas.jsonl",
        [
            {"doc_path": str(doc), "description": "Use t-strings", "python_version": "3.15"},
            {"doc_path": str(doc), "description": "Format a t-string", "python_version": "3.15"},
        ],
    )

    loaded = load_ideas(path)

    assert loaded == [
        Idea(doc, "Use t-strings", "3.15"),
        Idea(doc, "Format a t-string", "3.15"),
    ]
    assert all(isinstance(idea.doc_path, Path) for idea in loaded)


def test_load_ideas_empty_file(tmp_path: Path) -> None:
    path = write_ideas_file(tmp_path / "ideas.jsonl", [])

    assert load_ideas(path) == []


# --- the ideas command ------------------------------------------------------


def test_ideas_command_writes_one_line_per_idea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "PEP750.rst"
    doc.write_text("documentation", encoding="utf-8")
    output = tmp_path / "ideas.jsonl"
    model = StubModel({"ideas": ["first", "second"]})
    monkeypatch.setattr(ideas, "get_llm", lambda *args, **kwargs: model)

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(doc), "-o", str(output), "--python-version", "3.15"],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"doc_path": str(doc.absolute()), "description": "first", "python_version": "3.15"},
        {"doc_path": str(doc.absolute()), "description": "second", "python_version": "3.15"},
    ]


def test_ideas_command_skips_document_on_schema_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "PEP750.rst"
    doc.write_text("documentation", encoding="utf-8")
    output = tmp_path / "ideas.jsonl"
    model = StubModel(SchemaValidationError("no schema compliant response"))
    monkeypatch.setattr(ideas, "get_llm", lambda *args, **kwargs: model)

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(doc), "-o", str(output), "--python-version", "3.15"],
    )

    # A single unparseable document must not abort the run or create a file.
    assert result.exit_code == 0, result.output
    assert not output.exists()


def test_ideas_command_preview_prints_ideas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "PEP750.rst"
    doc.write_text("documentation", encoding="utf-8")
    output = tmp_path / "ideas.jsonl"
    model = StubModel({"ideas": ["demonstrate t-strings"]})
    monkeypatch.setattr(ideas, "get_llm", lambda *args, **kwargs: model)

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(doc), "-o", str(output), "--python-version", "3.15", "--preview"],
    )

    assert result.exit_code == 0, result.output
    # print_ideas renders through a Rich console that writes to stdout.
    assert "demonstrate t-strings" in result.output


def test_ideas_command_rejects_non_jsonl_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "PEP750.rst"
    doc.write_text("documentation", encoding="utf-8")
    monkeypatch.setattr(ideas, "get_llm", lambda *args, **kwargs: StubModel({"ideas": []}))

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(doc), "-o", str(tmp_path / "ideas.txt"), "--python-version", "3.15"],
    )

    assert result.exit_code != 0
    assert "Output file must end with .jsonl" in result.output


def test_ideas_command_uses_llm_model_name_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "PEP750.rst"
    doc.write_text("documentation", encoding="utf-8")
    captured: dict[str, str] = {}

    def fake_get_llm(provider: str, model_name: str) -> StubModel:
        captured.update(provider=provider, model_name=model_name)
        return StubModel({"ideas": []})

    monkeypatch.setattr(ideas, "get_llm", fake_get_llm)
    monkeypatch.setenv("LLM_MODEL_NAME", "custom-model")

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(doc), "-o", str(tmp_path / "ideas.jsonl"), "--python-version", "3.15"],
    )

    assert result.exit_code == 0, result.output
    assert captured == {"provider": "deepseek", "model_name": "custom-model"}


def test_ideas_command_generates_from_every_rst_in_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PEP750.rst").write_text("a", encoding="utf-8")
    (docs / "PEP815.rst").write_text("b", encoding="utf-8")
    (docs / "notes.txt").write_text("ignored", encoding="utf-8")
    output = tmp_path / "ideas.jsonl"
    model = StubModel({"ideas": ["an idea"]})
    monkeypatch.setattr(ideas, "get_llm", lambda *args, **kwargs: model)
    monkeypatch.setattr(ideas, "generate_ideas", lambda m, doc, version: [Idea(doc, "an idea", version)])

    result = CliRunner().invoke(
        ideas.main,
        ["-i", str(docs), "-o", str(output), "--python-version", "3.15"],
    )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert sorted(Path(row["doc_path"]).name for row in rows) == ["PEP750.rst", "PEP815.rst"]
