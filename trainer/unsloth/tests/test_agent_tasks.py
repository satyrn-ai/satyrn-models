"""Every packaged agent-eval task is gradable: its starting code fails, its reference passes, its manifest is sound."""

import json
import shutil
from pathlib import Path

import pytest

from satyrn.trainer.unsloth.eval.agent_eval.agent_task import (
    AgentTask,
    directories_to_jsonl,
    file_digest,
    jsonl_to_directories,
)
from satyrn.trainer.unsloth.eval.agent_eval.task import AGENT_TASKS, agent_eval, grade
from satyrn.trainer.unsloth.eval.agent_eval.workspace import Workspace

TASK_DIRS = sorted(path.parent for path in AGENT_TASKS.glob("*/manifest.json"))
CATEGORIES = {"finish", "recover", "judgement"}


def test_there_are_packaged_tasks_and_the_eval_runs_them_by_default() -> None:
    assert TASK_DIRS
    assert sorted(sample.id for sample in agent_eval().dataset) == sorted(path.name for path in TASK_DIRS)


def test_tasks_survive_a_round_trip_through_jsonl(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "tasks.jsonl"
    directories_to_jsonl(AGENT_TASKS, jsonl_path)
    jsonl_to_directories(jsonl_path, tmp_path / "tasks")
    for task_dir in TASK_DIRS:
        assert AgentTask.from_directory(tmp_path / "tasks" / task_dir.name) == AgentTask.from_directory(task_dir)


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=lambda path: path.name)
def test_manifest_is_sound(task_dir: Path) -> None:
    manifest = json.loads((task_dir / "manifest.json").read_text())
    task = AgentTask.from_directory(task_dir)
    assert task.name == task_dir.name
    assert task.category in CATEGORIES
    assert 300 <= len(task.contract) <= 900, "prompts follow the agentic SFT data, 400-800 characters"
    for path, replacements in task.on_first_touch.items():
        text = task.files[f"base/{path}"]
        assert all(old in text for old, _new in replacements), f"every first-touch change to {path} applies to base/"
    has_reference = (task_dir / "reference").is_dir() or manifest.get("reference_delete")
    assert manifest.get("base_passes") or has_reference, "a task to solve needs a reference"


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=lambda path: path.name)
def test_base_fails_and_reference_passes(task_dir: Path, tmp_path: Path) -> None:
    """The starting code fails the hidden tests (unless the task is already done) and the reference passes them."""
    task = AgentTask.from_directory(task_dir)
    manifest = json.loads((task_dir / "manifest.json").read_text())
    ws = Workspace.create(task, tmp_path)
    passed = grade(ws, task)
    if manifest.get("base_passes"):
        assert passed == set(task.expected)
        return
    assert passed != set(task.expected), "the starting code must fail at least one hidden test"
    if (task_dir / "reference").is_dir():
        shutil.copytree(task_dir / "reference", ws.root, dirs_exist_ok=True)
    for path in manifest.get("reference_delete", []):  # a reference solution that removes files
        (ws.root / path).unlink()
    assert grade(ws, task) == set(task.expected)
    changed = [path for path, digest in task.protected.items() if file_digest(ws.root / path) != digest]
    assert changed == [], "the reference solution leaves protected files alone"
