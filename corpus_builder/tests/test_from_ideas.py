"""Tests that ``sft`` and ``rl`` consume ideas from a file instead of docs.

The branch moved idea generation into its own command.  ``sft`` and ``rl`` now
read ``Idea`` rows from ``--ideas-path`` and feed each one to ``build_dataset_line``.
These tests stub out the Docker sandboxes and the LLM so the loading behaviour can
be verified in isolation.
"""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from click.testing import CliRunner

from satyrn.dataset import rl, sft
from satyrn.dataset.utils.generation import Idea


@pytest.fixture
def ideas_file(tmp_path: Path) -> Path:
    """A JSONL file containing two ideas, as written by the ``ideas`` command."""
    path = tmp_path / "ideas.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for description in ("first idea", "second idea"):
            handle.write(
                json.dumps(
                    {
                        "doc_path": str(tmp_path / "PEP750.rst"),
                        "description": description,
                        "python_version": "3.15",
                    }
                )
                + "\n"
            )
    return path


def stub_sandboxes(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Docker-backed dependencies of a dataset command with no-ops."""
    monkeypatch.setattr(module, "get_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "Sandbox", lambda python_version: object())
    monkeypatch.setattr(module, "get_predecessor_python_version", lambda python_version: "3.14")
    monkeypatch.setattr(module, "remove_leftover_containers", lambda: 0)


@pytest.mark.parametrize("module", [sft, rl], ids=["sft", "rl"])
def test_command_feeds_every_loaded_idea_to_build_dataset_line(
    module: ModuleType,
    ideas_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sandboxes(module, monkeypatch)
    output = tmp_path / "dataset.jsonl"
    seen: list[Idea] = []

    def fake_build(model: Any, idea: Idea, sandbox: Any, predecessor: Any) -> dict:
        seen.append(idea)
        return {"description": idea.description, "filename": idea.doc_path.name}

    monkeypatch.setattr(module, "build_dataset_line", fake_build)

    result = CliRunner().invoke(
        module.main,
        ["-i", str(ideas_file), "-o", str(output), "--python-version", "3.15"],
    )

    assert result.exit_code == 0, result.output
    assert [idea.description for idea in seen] == ["first idea", "second idea"]
    assert all(idea.python_version == "3.15" for idea in seen)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    # Ideas are appended as their futures complete, so even with one worker the
    # on-disk order is not guaranteed once every future finishes immediately.
    assert sorted(rows, key=lambda row: row["description"]) == [
        {"description": "first idea", "filename": "PEP750.rst"},
        {"description": "second idea", "filename": "PEP750.rst"},
    ]


@pytest.mark.parametrize("module", [sft, rl], ids=["sft", "rl"])
def test_command_skips_none_results(
    module: ModuleType,
    ideas_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sandboxes(module, monkeypatch)
    output = tmp_path / "dataset.jsonl"
    monkeypatch.setattr(module, "build_dataset_line", lambda *args: None)

    result = CliRunner().invoke(
        module.main,
        ["-i", str(ideas_file), "-o", str(output), "--python-version", "3.15"],
    )

    assert result.exit_code == 0, result.output
    assert not output.exists()


@pytest.mark.parametrize("module", [sft, rl], ids=["sft", "rl"])
def test_command_requires_existing_ideas_file(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_sandboxes(module, monkeypatch)
    monkeypatch.setattr(module, "build_dataset_line", lambda *args: None)

    result = CliRunner().invoke(
        module.main,
        ["-i", str(tmp_path / "missing.jsonl"), "-o", str(tmp_path / "out.jsonl"), "--python-version", "3.15"],
    )

    assert result.exit_code == 2
    assert "does not exist" in result.output
