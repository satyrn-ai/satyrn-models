"""Tests for agentic SFT task generation, with a stub model instead of the LLM."""

from pathlib import Path
from typing import Any

import pytest

from satyrn.dataset.agentic_sft import Task, generate_task
from satyrn.dataset.pi_harness.harness import File
from satyrn.dataset.utils.generation import Idea

RESPONSE = {
    "file_name": "render.py",
    "before": "def render(name):\n    return '<p>' + name + '</p>'\n",
    "prompt": "Refactor render(name) in render.py to use a t-string.",
    "after": "def render(name):\n    return html(t'<p>{name}</p>')\n",
    "tests": "assert render('a') == '<p>a</p>'",
}


class StubModel:
    """A Model whose generate returns a canned response and records the prompt."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str, context: Any, thinking: bool = False, effort: str = "medium") -> Any:
        self.prompts.append(prompt)
        return self.response


@pytest.fixture
def idea(tmp_path: Path) -> Idea:
    doc_path = tmp_path / "PEP750.rst"
    doc_path.write_text("documentation", encoding="utf-8")
    return Idea(doc_path, "Refactor render.py to use a t-string", "3.14", "agentic-sft")


def test_generate_task_builds_a_task_from_the_response(idea: Idea) -> None:
    model = StubModel(RESPONSE)

    task = generate_task(model, idea)

    assert task == Task(
        prompt=RESPONSE["prompt"],
        before=File("render.py", RESPONSE["before"]),
        after=File("render.py", RESPONSE["after"]),
        tests=RESPONSE["tests"],
    )
    assert idea.description in model.prompts[0]


def test_generate_task_has_no_before_file_for_a_new_file(idea: Idea) -> None:
    task = generate_task(StubModel({**RESPONSE, "before": ""}), idea)

    assert task.before is None
