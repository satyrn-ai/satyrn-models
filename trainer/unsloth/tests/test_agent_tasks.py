"""Every packaged agent-eval task is gradable: its starting code fails, its reference passes, its manifest is sound."""

from pathlib import Path

import pytest

from satyrn.trainer.unsloth.eval.agent_eval.agent_task import AgentTask, directories_to_jsonl, jsonl_to_directories
from satyrn.trainer.unsloth.eval.agent_eval.task import TASKS_FILE, agent_eval, grade
from satyrn.trainer.unsloth.eval.agent_eval.workspace import Workspace

TASKS = [AgentTask.from_json(line) for line in TASKS_FILE.read_text().splitlines()]
CATEGORIES = {"finish", "recover", "judgement"}


def test_there_are_packaged_tasks_and_the_eval_runs_them_by_default() -> None:
    assert TASKS
    assert [sample.id for sample in agent_eval().dataset] == [task.name for task in TASKS]


def test_tasks_survive_a_round_trip_through_folders(tmp_path: Path) -> None:
    jsonl_to_directories(TASKS_FILE, tmp_path / "tasks")
    directories_to_jsonl(tmp_path / "tasks", tmp_path / "tasks.jsonl")
    assert (tmp_path / "tasks.jsonl").read_text() == TASKS_FILE.read_text()


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.name)
def test_manifest_is_sound(task: AgentTask) -> None:
    assert task.category in CATEGORIES
    assert 300 <= len(task.contract) <= 900, "prompts follow the agentic SFT data, 400-800 characters"
    assert all(f"base/{path}" in task.files for path in task.protected), "every protected path exists in base/"
    for path, replacements in task.on_first_touch.items():
        text = task.files[f"base/{path}"]
        assert all(old in text for old, _new in replacements), f"every first-touch change to {path} applies to base/"
    has_reference = any(path.startswith("reference/") for path in task.files) or task.manifest.get("reference_delete")
    assert task.manifest.get("base_passes") or has_reference, "a task to solve needs a reference"


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task.name)
def test_base_fails_and_reference_passes(task: AgentTask, tmp_path: Path) -> None:
    """The starting code fails the hidden tests (unless the task is already done) and the reference passes them."""
    ws = Workspace.create(task, tmp_path)
    passed = grade(ws, task)
    if task.manifest.get("base_passes"):
        assert passed == set(task.expected)
        return
    assert passed != set(task.expected), "the starting code must fail at least one hidden test"
    task.write_files(ws.root, "reference")
    for path in task.manifest.get("reference_delete", []):  # a reference solution that removes files
        (ws.root / path).unlink()
    assert grade(ws, task) == set(task.expected)
    assert task.changed_protected_paths(ws.root) == [], "the reference solution leaves protected files alone"
