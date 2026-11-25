"""The agent-behaviour eval: satyrn-evals tasks run with the recorded agent tools, scored on tool use and stopping."""

import json
from pathlib import Path

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

from satyrn.trainer.unsloth.eval.agent_eval import (
    DEFAULT_TASKS,
    Workspace,
    agent_eval,
    grade,
    load_task,
    recorded_session,
    system_prompt,
)

SOLVED = "def double(n):\n    return n * 2\n"


def tool(name: str, props: dict, required: list[str]) -> dict:
    params = {"type": "object", "properties": props, "required": required}
    return {"type": "function", "function": {"name": name, "description": f"The {name} tool.", "parameters": params}}


TOOLS = [
    tool("read", {"path": {"type": "string"}, "offset": {"type": "number"}, "limit": {"type": "number"}}, ["path"]),
    tool("bash", {"command": {"type": "string"}, "timeout": {"type": "number"}}, ["command"]),
    tool(
        "edit", {"path": {"type": "string"}, "edits": {"type": "array", "items": {"type": "object"}}}, ["path", "edits"]
    ),
    tool("write", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
]
SYSTEM = "You are a coding agent.\n\n<cwd>\n/workspace\n</cwd>\nBe concise."


@pytest.fixture(autouse=True)
def agentic_data(tmp_path_factory, monkeypatch) -> Path:
    """A one-row agentic SFT file, standing in for the real (git-lfs) dataset the eval reads its session from."""
    path = tmp_path_factory.mktemp("data") / "sft-agentic.jsonl"
    path.write_text(json.dumps({"prompt": [{"role": "system", "content": SYSTEM}], "tools": TOOLS}) + "\n")
    monkeypatch.setenv("SATYRN_AGENTIC_DATA", str(path))
    return path


def make_task(root: Path, overlay: bool = False) -> Path:
    """A one-file task in the satyrn-evals layout: manifest, base/ and an optional hidden overlay/."""
    task = root / "double"
    (task / "base").mkdir(parents=True)
    (task / "base" / "solution.py").write_text("def double(n):\n    raise NotImplementedError\n")
    tests = (
        "from solution import double\n\n"
        "def test_two():\n    assert double(2) == 4\n\n"
        "def test_zero():\n    assert double(0) == 0\n"
    )
    manifest = {
        "name": "double",
        "contract": "Implement double(n) in solution.py.",
        "expected_test_ids": ["test_solution.py::test_two", "test_solution.py::test_zero"],
        "source_paths": ["solution.py"],
    }
    if overlay:
        (task / "overlay").mkdir()
        (task / "overlay" / "test_solution.py").write_text(tests)
        manifest["grader_overlay"] = "overlay"
    else:
        (task / "base" / "test_solution.py").write_text(tests)
    (task / "manifest.json").write_text(json.dumps(manifest))
    return task


def test_load_task_reads_the_manifest(tmp_path: Path) -> None:
    """The contract, expected ids and hidden overlay come from the task directory."""
    task = load_task(make_task(tmp_path, overlay=True))
    assert task.name == "double"
    assert task.contract.startswith("Implement double")
    assert task.expected == ["test_solution.py::test_two", "test_solution.py::test_zero"]
    assert task.overlay == tmp_path / "double" / "overlay"


def test_workspace_resolves_relative_and_inside_absolute_paths(tmp_path: Path) -> None:
    """Relative paths and absolute paths under the workspace are allowed; anything else is an escape."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs")
    assert ws.resolve("solution.py") == ws.root / "solution.py"
    assert ws.resolve(str(ws.root / "solution.py")) == ws.root / "solution.py"
    assert ws.resolve("/workspace/solution.py") is None
    assert ws.resolve("../outside.py") is None


def test_workspace_root_is_long_and_unique(tmp_path: Path) -> None:
    """The working folder is never a short fixed path such as /workspace."""
    task = load_task(make_task(tmp_path))
    a, b = Workspace.create(task, tmp_path / "runs"), Workspace.create(task, tmp_path / "runs")
    assert a.root != b.root
    assert len(str(a.root)) > len("/workspace") + 20


def test_tools_count_calls_errors_and_escapes(tmp_path: Path) -> None:
    """Each call is counted; a failed edit is an error, a path outside the workspace is an escape."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs")
    assert not ws.call("read", {"path": "solution.py"})[1]
    _out, err = ws.call("edit", {"path": "solution.py", "edits": [{"oldText": "nothing like this", "newText": "x"}]})
    assert err
    _out, err = ws.call("write", {"path": "/workspace/solution.py", "content": SOLVED})
    assert err
    assert not ws.call("write", {"path": "solution.py", "content": SOLVED})[1]
    assert (ws.calls, ws.errors, ws.escapes) == (4, 2, 1)


def test_grade_runs_the_hidden_overlay_against_the_workspace(tmp_path: Path) -> None:
    """Overlay tests are copied in for grading only; the result is the set of expected ids that passed."""
    task = load_task(make_task(tmp_path, overlay=True))
    ws = Workspace.create(task, tmp_path / "runs")
    assert not (ws.root / "test_solution.py").exists()
    assert grade(ws, task) == set()
    ws.write("solution.py", SOLVED)
    assert grade(ws, task) == set(task.expected)


def run_mock(tasks_dir: Path, outputs, max_turns: int = 10):
    model = get_model("mockllm/model", custom_outputs=outputs)
    task = agent_eval(tasks_dir=str(tasks_dir), tasks=["all"], max_turns=max_turns)
    [log] = inspect_eval(task, model=model, display="none", log_dir=str(tasks_dir.parent / "logs"))
    return log


def test_clean_solve_scores_one(tmp_path: Path) -> None:
    """Writing the solution with a relative path, then stopping with an answer, is a clean solve."""
    make_task(tmp_path)
    log = run_mock(
        tmp_path,
        [
            ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED}),
            ModelOutput.from_content("mockllm/model", "Done: double(n) returns n * 2."),
        ],
    )
    sample = log.samples[0]
    assert sample.scores["agent_behaviour"].value["clean"] == 1
    assert sample.scores["agent_behaviour"].value["solved"] == 1
    assert sample.scores["agent_behaviour"].value["self_stop"] == 1


def test_absolute_path_escape_is_not_clean(tmp_path: Path) -> None:
    """A write to /workspace/... is refused and counted, so the run is not clean even if it later solves."""
    make_task(tmp_path)
    log = run_mock(
        tmp_path,
        [
            ModelOutput.for_tool_call("mockllm/model", "write", {"path": "/workspace/solution.py", "content": SOLVED}),
            ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED}),
            ModelOutput.from_content("mockllm/model", "Done."),
        ],
    )
    value = log.samples[0].scores["agent_behaviour"].value
    assert value["solved"] == 1
    assert value["workspace_escapes"] == 1
    assert value["clean"] == 0


def test_running_out_of_turns_is_not_a_self_stop(tmp_path: Path) -> None:
    """A model that keeps calling tools until the turn cap did not know when to stop."""
    make_task(tmp_path)
    reads = [ModelOutput.for_tool_call("mockllm/model", "read", {"path": "solution.py"}) for _ in range(5)]
    value = run_mock(tmp_path, reads, max_turns=3).samples[0].scores["agent_behaviour"].value
    assert value["self_stop"] == 0
    assert value["clean"] == 0


@pytest.mark.parametrize("bad", [{"path": "solution.py"}, {"content": "x"}])
def test_missing_arguments_are_tool_errors_not_crashes(tmp_path: Path, bad: dict) -> None:
    """A malformed call becomes an error result the model can read, not an exception."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs")
    _out, err = ws.call("write", bad)
    assert err
    assert ws.errors == 1


def test_grade_honours_the_oracle_env_prefix(tmp_path: Path) -> None:
    """An oracle such as `env PYTHONPATH=scripts python -m pytest` puts its module path on PYTHONPATH."""
    task_dir = make_task(tmp_path)
    (task_dir / "base" / "scripts").mkdir()
    (task_dir / "base" / "solution.py").rename(task_dir / "base" / "scripts" / "solution.py")
    manifest = json.loads((task_dir / "manifest.json").read_text())
    manifest["oracle"] = ["env", "PYTHONPATH=scripts", "python", "-m", "pytest"]
    (task_dir / "manifest.json").write_text(json.dumps(manifest))
    task = load_task(task_dir)
    ws = Workspace.create(task, tmp_path / "runs")
    ws.write("scripts/solution.py", SOLVED)
    assert grade(ws, task) == set(task.expected)


def test_session_is_read_from_the_agentic_training_data(agentic_data: Path) -> None:
    """The system prompt and tool schemas are the training data's own, never a copy kept in code."""
    system, tools = recorded_session()
    assert system == SYSTEM and tools == TOOLS


def test_system_prompt_names_the_real_working_folder(tmp_path: Path) -> None:
    """<cwd> in the recorded prompt is replaced by the sample's actual folder, whatever it was recorded as."""
    root = tmp_path / "a" / "long" / "folder"
    prompt = system_prompt(root)
    assert prompt == f"You are a coding agent.\n\n<cwd>\n{root}\n</cwd>\nBe concise."


def test_a_git_lfs_pointer_is_a_clear_error(agentic_data: Path) -> None:
    """Without git-lfs the dataset is a pointer file; say so instead of failing on JSON."""
    agentic_data.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    with pytest.raises(RuntimeError, match="git-lfs"):
        recorded_session()


def test_the_model_is_offered_pis_tool_schemas(tmp_path: Path) -> None:
    """Every generate call carries the recorded tools with their full parameter schemas."""
    make_task(tmp_path)
    seen = []

    def respond(messages, tools, tool_choice, config):
        seen.append({t.name: sorted(t.parameters.properties) for t in tools})
        return ModelOutput.from_content("mockllm/model", "Nothing to do.")

    log = run_mock(tmp_path, respond)
    assert log.status == "success"
    assert seen[0] == {
        "read": ["limit", "offset", "path"],
        "bash": ["command", "timeout"],
        "edit": ["edits", "path"],
        "write": ["content", "path"],
    }


def test_default_task_set_is_the_short_tasks(tmp_path: Path) -> None:
    """Without `tasks`, only the default short tasks that exist in the directory run; ["all"] runs every task."""
    make_task(tmp_path)
    (tmp_path / "double").rename(tmp_path / DEFAULT_TASKS[0])
    manifest = json.loads((tmp_path / DEFAULT_TASKS[0] / "manifest.json").read_text())
    manifest["name"] = DEFAULT_TASKS[0]
    (tmp_path / DEFAULT_TASKS[0] / "manifest.json").write_text(json.dumps(manifest))
    make_task(tmp_path)  # a second task, not in the default set
    assert [s.id for s in agent_eval(tasks_dir=str(tmp_path)).dataset] == [DEFAULT_TASKS[0]]
    assert sorted(s.id for s in agent_eval(tasks_dir=str(tmp_path), tasks=["all"]).dataset) == sorted(
        [DEFAULT_TASKS[0], "double"]
    )


def test_read_offset_limit_and_bash_timeout_are_honoured(tmp_path: Path) -> None:
    """The optional read and bash arguments work rather than erroring."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs")
    ws.write("lines.txt", "one\ntwo\nthree\nfour\n")
    assert ws.call("read", {"path": "lines.txt", "offset": 2, "limit": 2})[0].startswith("two\nthree")
    out, err = ws.call("bash", {"command": "sleep 5", "timeout": 1})
    assert err and "timed out" in out


def test_default_agentic_data_path_is_the_repo_dataset() -> None:
    """The default points at the repository's own agentic SFT file (present as a git-lfs file or pointer)."""
    from satyrn.trainer.unsloth.eval.agent_eval import AGENTIC_DATA

    assert AGENTIC_DATA.is_file()


def test_grading_does_not_need_pytest_in_the_running_interpreter(tmp_path: Path, monkeypatch) -> None:
    """The eval may run in an environment without pytest (it is a dev extra); grading must still work."""
    import subprocess
    import sys

    venv = tmp_path / "bare"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    monkeypatch.setattr(sys, "executable", str(venv / "bin" / "python"))
    task = load_task(make_task(tmp_path))
    ws = Workspace.create(task, tmp_path / "runs")
    ws.write("solution.py", SOLVED)
    assert grade(ws, task) == set(task.expected)
