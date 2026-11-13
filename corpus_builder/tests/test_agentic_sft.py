"""Tests for agentic SFT task generation, with stubs instead of the LLM and the Docker sandboxes."""

from pathlib import Path
from typing import Any

import pytest

from satyrn.dataset.agentic_sft import PASS_MARKER, Task, extract_session, generate_task, verify_code
from satyrn.dataset.pi_harness.harness import File
from satyrn.dataset.utils.generation import Idea

RESPONSE = {
    "file_name": "render.py",
    "initial": "def render(name):\n    return '<p>' + name + '</p>'\n",
    "prompt": "Make render(name) in render.py safe for user input.",
    "solution": "def render(name):\n    return html(t'<p>{name}</p>')\n",
    "tests": "assert render('a') == '<p>a</p>'",
}
TASK = Task(
    prompt=RESPONSE["prompt"],
    initial=File("render.py", RESPONSE["initial"]),
    solution=File("render.py", RESPONSE["solution"]),
    tests=RESPONSE["tests"],
)


class StubModel:
    """A Model whose generate returns the given responses in order and records the prompts."""

    def __init__(self, *responses: dict) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str, context: Any, thinking: bool = False, effort: str = "medium") -> Any:
        self.prompts.append(prompt)
        return self.responses[len(self.prompts) - 1]


class StubSandbox:
    """Return the given outputs in order while recording submitted programs."""

    def __init__(self, python_version: str, *outputs: str) -> None:
        self.python_version = python_version
        self.outputs = list(outputs)
        self.programs: list[str] = []

    def run(self, code: str) -> str:
        self.programs.append(code)
        return self.outputs[len(self.programs) - 1]


@pytest.fixture
def idea(tmp_path: Path) -> Idea:
    doc_path = tmp_path / "PEP750.rst"
    doc_path.write_text("documentation", encoding="utf-8")
    return Idea(doc_path, "Make render.py safe with a t-string", "3.14", "agentic-sft")


def test_verify_code_accepts_tests_that_pass_only_on_the_target() -> None:
    sandbox = StubSandbox("3.14", f"some output\n{PASS_MARKER}\n")
    predecessor_sandbox = StubSandbox("3.13", "SyntaxError")

    assert verify_code(TASK.solution.content, TASK.tests, sandbox, predecessor_sandbox) is None
    assert sandbox.programs[0].startswith(RESPONSE["solution"].rstrip())
    assert RESPONSE["tests"] in sandbox.programs[0]
    assert predecessor_sandbox.programs == sandbox.programs


def test_verify_code_rejects_tests_that_fail_on_the_target() -> None:
    sandbox = StubSandbox("3.14", f"{PASS_MARKER}\nAssertionError")
    predecessor_sandbox = StubSandbox("3.13")

    rejection = verify_code(TASK.solution.content, TASK.tests, sandbox, predecessor_sandbox)

    assert rejection is not None
    assert "The tests failed under Python 3.14" in rejection
    assert "AssertionError" in rejection
    assert predecessor_sandbox.programs == []


def test_verify_code_rejects_tests_that_also_pass_on_the_predecessor() -> None:
    sandbox = StubSandbox("3.14", PASS_MARKER)
    predecessor_sandbox = StubSandbox("3.13", PASS_MARKER)

    rejection = verify_code(TASK.solution.content, TASK.tests, sandbox, predecessor_sandbox)

    assert rejection is not None
    assert "The tests also passed under Python 3.13" in rejection


def test_extract_session_drops_priming_and_render_messages() -> None:
    system_message = {"role": "system", "content": "system prompt"}
    priming_message = {"role": "user", "content": [{"type": "text", "text": "Read this document"}]}
    ready_message = {"role": "assistant", "content": "ready"}
    task_message = {"role": "user", "content": [{"type": "text", "text": "Fix render.py"}]}
    agent_turns = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "done"},
        {"role": "assistant", "content": "Finished"},
    ]
    render_message = {"role": "user", "content": [{"type": "text", "text": "[RENDER SESSION AND ABORT]"}]}
    messages = [system_message, priming_message, ready_message, task_message, *agent_turns, render_message]

    prompt, completion = extract_session(messages, "Fix render.py")

    assert prompt == [system_message, {"role": "user", "content": "Fix render.py"}]
    assert completion == agent_turns


def test_generate_task_returns_the_first_verified_task(idea: Idea) -> None:
    model = StubModel(RESPONSE)

    task = generate_task(model, idea, StubSandbox("3.14", PASS_MARKER), StubSandbox("3.13", "SyntaxError"))

    assert task == TASK
    assert idea.description in model.prompts[0]


def test_generate_task_has_no_initial_file_for_a_new_file(idea: Idea) -> None:
    model = StubModel({**RESPONSE, "initial": ""})

    task = generate_task(model, idea, StubSandbox("3.14", PASS_MARKER), StubSandbox("3.13", "SyntaxError"))

    assert task.initial is None


def test_generate_task_retries_with_the_previous_task_and_the_rejection(idea: Idea) -> None:
    corrected_response = {**RESPONSE, "tests": "assert render('b') == '<p>b</p>'"}
    model = StubModel(RESPONSE, corrected_response)
    sandbox = StubSandbox("3.14", PASS_MARKER, PASS_MARKER)
    predecessor_sandbox = StubSandbox("3.13", PASS_MARKER, "SyntaxError")

    task = generate_task(model, idea, sandbox, predecessor_sandbox)

    assert task.tests == corrected_response["tests"]
    assert "The tests also passed under Python 3.13" in model.prompts[1]
    assert RESPONSE["tests"] in model.prompts[1]


def test_generate_task_gives_up_after_three_rejected_attempts(idea: Idea) -> None:
    model = StubModel(RESPONSE, RESPONSE, RESPONSE)
    sandbox = StubSandbox("3.14", "AssertionError", "AssertionError", "AssertionError")

    with pytest.raises(ValueError, match="Could not generate a verified task"):
        generate_task(model, idea, sandbox, StubSandbox("3.13"))
