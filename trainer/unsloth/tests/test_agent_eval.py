"""The agent-behaviour eval: satyrn-evals tasks run with the recorded agent tools, scored on tool use and stopping."""

import json
from pathlib import Path

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

from satyrn.trainer.unsloth.eval.agent_eval.agent_task import load_task
from satyrn.trainer.unsloth.eval.agent_eval.task import DEFAULT_TASKS, agent_eval, grade, system_prompt
from satyrn.trainer.unsloth.eval.agent_eval.workspace import Workspace

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
        "system_prompt": SYSTEM,
        "tools": TOOLS,
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


def test_tools_count_calls_failures_and_escapes(tmp_path: Path) -> None:
    """Each call is counted; a non-matching edit failed, and a path outside the workspace failed and escaped."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs")
    assert not ws.call("read", {"path": "solution.py"})[1]
    _out, err = ws.call("edit", {"path": "solution.py", "edits": [{"oldText": "nothing like this", "newText": "x"}]})
    assert err
    _out, err = ws.call("write", {"path": "/workspace/solution.py", "content": SOLVED})
    assert err
    assert not ws.call("write", {"path": "solution.py", "content": SOLVED})[1]
    assert (ws.calls, ws.invalid, ws.failed, ws.escapes) == (4, 0, 2, 1)


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


def read_call(offset: int = 1) -> ModelOutput:
    return ModelOutput.for_tool_call("mockllm/model", "read", {"path": "solution.py", "offset": offset})


def scored(log) -> tuple[dict, dict]:
    """The sample's score values and its run record."""
    score = log.samples[0].scores["agent_behaviour"]
    return score.value, score.metadata


def test_running_out_of_turns_is_not_a_self_stop(tmp_path: Path) -> None:
    """A model that keeps calling tools until the turn cap did not know when to stop."""
    make_task(tmp_path)
    value, run = scored(run_mock(tmp_path, [read_call(n) for n in range(1, 6)], max_turns=3))
    assert run["ending"] == "turn_cap"
    assert value["self_stop"] == 0
    assert value["looped"] == 0
    assert value["clean"] == 0


def test_the_same_turn_three_times_ends_the_sample_as_a_loop(tmp_path: Path) -> None:
    """Greedy decoding repeats itself exactly; the third identical turn ends the sample without running it."""
    make_task(tmp_path)
    value, run = scored(run_mock(tmp_path, [read_call() for _ in range(10)], max_turns=10))
    assert run["ending"] == "looped"
    assert run["turns"] == 3
    assert run["calls"] == 2  # the repeat that ended it was not run
    assert value["looped"] == 1
    assert value["self_stop"] == 0


def test_a_different_turn_in_between_resets_the_loop_count(tmp_path: Path) -> None:
    """Only consecutive repeats count; returning to an earlier call after something else is not a loop."""
    make_task(tmp_path)
    outputs = [read_call(1), read_call(1), read_call(2), read_call(1), read_call(1)]
    outputs.append(ModelOutput.from_content("mockllm/model", "Nothing to change."))
    value, run = scored(run_mock(tmp_path, outputs, max_turns=10))
    assert run["ending"] == "stopped"
    assert value["looped"] == 0


def test_loop_repeats_is_configurable(tmp_path: Path) -> None:
    """With loop_repeats=2 the first repeat ends the sample."""
    make_task(tmp_path)
    model = get_model("mockllm/model", custom_outputs=[read_call() for _ in range(5)])
    task = agent_eval(tasks_dir=str(tmp_path), tasks=["all"], max_turns=10, loop_repeats=2)
    [log] = inspect_eval(task, model=model, display="none", log_dir=str(tmp_path.parent / "logs"))
    _value, run = scored(log)
    assert (run["ending"], run["turns"]) == ("looped", 2)


def test_solving_then_looping_is_an_overrun(tmp_path: Path) -> None:
    """The workspace is graded however the sample ended: solved but not stopped is an overrun, not a solve-and-stop."""
    make_task(tmp_path)
    write = ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED})
    value, run = scored(run_mock(tmp_path, [write] + [read_call() for _ in range(5)], max_turns=10))
    assert run["ending"] == "looped"
    assert (value["solved"], value["overrun"], value["premature_stop"], value["clean"]) == (1, 1, 0, 0)


def test_stopping_unsolved_is_a_premature_stop(tmp_path: Path) -> None:
    """Stopping on its own with the tests still failing is a premature stop."""
    make_task(tmp_path)
    value, run = scored(run_mock(tmp_path, [read_call(), ModelOutput.from_content("mockllm/model", "All done.")]))
    assert run["ending"] == "stopped"
    assert (value["self_stop"], value["solved"], value["premature_stop"], value["overrun"]) == (1, 0, 1, 0)


def test_a_tool_call_written_as_text_is_not_a_stop(tmp_path: Path) -> None:
    """A turn whose only tool call is plain text ends the sample, but it is an invalid call, not a stop."""
    make_task(tmp_path)
    text_call = ModelOutput.from_content("mockllm/model", '<tool_call>\n{"name": "read"}\n</tool_call>')
    value, run = scored(run_mock(tmp_path, [text_call]))
    assert run["ending"] == "text_tool_call"
    assert (value["self_stop"], value["premature_stop"], value["invalid_tool_calls"]) == (0, 0, 1)


@pytest.mark.parametrize("bad", [{"path": "solution.py"}, {"content": "x"}])
def test_missing_arguments_are_invalid_calls_not_crashes(tmp_path: Path, bad: dict) -> None:
    """A malformed call becomes an error result the model can read, not an exception, with or without schemas."""
    task = load_task(make_task(tmp_path))
    for schemas in ({}, SCHEMAS):
        ws = Workspace.create(task, tmp_path / "runs", schemas)
        _out, err = ws.call("write", bad)
        assert err
        assert (ws.calls, ws.invalid, ws.failed) == (1, 1, 0)


SCHEMAS = {spec["function"]["name"]: spec["function"]["parameters"] for spec in TOOLS}


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("read", {"path": "solution.py", "offset": "two"}, "'two' is not of type 'number'"),
        ("bash", {}, "'command' is a required property"),
        ("edit", {"path": "solution.py", "edits": "oldText=a"}, "is not of type 'array'"),
        ("grep", {"pattern": "x"}, "unknown tool grep"),
    ],
)
def test_calls_that_break_the_schema_are_invalid_and_not_run(
    tmp_path: Path, name: str, arguments: dict, message: str
) -> None:
    """A wrong type, a missing required argument or an unknown tool is the model's mistake; the call is not run."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    out, err = ws.call(name, arguments)
    assert err and message in out
    assert (ws.calls, ws.invalid, ws.failed) == (1, 1, 0)
    assert ws.by_tool[name].invalid == 1


def test_valid_calls_whose_operation_fails_are_failed_not_invalid(tmp_path: Path) -> None:
    """A missing file, a non-matching edit and a path outside the workspace are failed operations."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    assert ws.call("read", {"path": "missing.py"})[1]
    assert ws.call("edit", {"path": "solution.py", "edits": [{"oldText": "absent", "newText": "x"}]})[1]
    assert ws.call("write", {"path": "../outside.py", "content": "x"})[1]
    assert (ws.calls, ws.invalid, ws.failed, ws.escapes) == (3, 0, 3, 1)


def test_a_command_exiting_non_zero_is_ok_but_counted(tmp_path: Path) -> None:
    """A grep with no match or a failing test run is often intended, so it is not a failed call."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    out, err = ws.call("bash", {"command": "grep -q nothing-like-this solution.py"})
    assert not err and "exited with code 1" in out
    assert (ws.calls, ws.invalid, ws.failed, ws.command_exit_nonzero) == (1, 0, 0, 1)


def test_scores_separate_invalid_from_failed_calls(tmp_path: Path) -> None:
    """Rates: invalid over all attempted calls, failed over the calls that ran; per-tool counts in the run."""
    make_task(tmp_path)
    outputs = [
        ModelOutput.for_tool_call("mockllm/model", "read", {"path": "solution.py", "offset": "two"}),  # invalid
        ModelOutput.for_tool_call("mockllm/model", "read", {"path": "missing.py"}),  # failed
        ModelOutput.for_tool_call("mockllm/model", "bash", {"command": "exit 3"}),  # ok, non-zero exit
        ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED}),  # ok
        ModelOutput.from_content("mockllm/model", "Done."),
    ]
    value, run = scored(run_mock(tmp_path, outputs))
    assert value["invalid_call_rate"] == 1 / 4
    assert value["failed_call_rate"] == 1 / 3
    assert (value["invalid_tool_calls"], value["command_exit_nonzero"]) == (1, 1)
    assert run["by_tool"]["read"] == {"calls": 2, "invalid": 1, "failed": 1}
    assert (value["solved"], value["clean"]) == (1, 0)  # solved and stopped, but an invalid call is not clean


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


def test_system_prompt_names_the_real_working_folder(tmp_path: Path) -> None:
    """<cwd> in the recorded prompt is replaced by the sample's actual folder, whatever it was recorded as."""
    root = tmp_path / "a" / "long" / "folder"
    prompt = system_prompt(SYSTEM, root)
    assert prompt == f"You are a coding agent.\n\n<cwd>\n{root}\n</cwd>\nBe concise."


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


def make_judgement_task(root: Path) -> Path:
    """The double task, already solved, with its solution protected and a call limit."""
    task = make_task(root)
    (task / "base" / "solution.py").write_text(SOLVED)
    manifest = json.loads((task / "manifest.json").read_text())
    manifest |= {"category": "judgement", "protected_paths": ["solution.py"], "max_calls": 2}
    (task / "manifest.json").write_text(json.dumps(manifest))
    return task


def test_leaving_finished_work_alone_within_the_call_limit_is_solved(tmp_path: Path) -> None:
    make_judgement_task(tmp_path)
    value, run = scored(run_mock(tmp_path, [read_call(), ModelOutput.from_content("mockllm/model", "Already done.")]))
    assert run["protected_changed"] == []
    assert (value["solved"], value["clean"]) == (1, 1)


def test_rewriting_a_protected_file_is_not_solved_even_if_tests_pass(tmp_path: Path) -> None:
    make_judgement_task(tmp_path)
    rewrite = ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED + "\n"})
    value, run = scored(run_mock(tmp_path, [rewrite, ModelOutput.from_content("mockllm/model", "Tidied it.")]))
    assert run["protected_changed"] == ["solution.py"]
    assert value["solved"] == 0


def test_going_over_the_call_limit_is_not_solved(tmp_path: Path) -> None:
    make_judgement_task(tmp_path)
    outputs = [read_call(1), read_call(2), read_call(3), ModelOutput.from_content("mockllm/model", "Fine.")]
    value, _run = scored(run_mock(tmp_path, outputs))
    assert value["solved"] == 0


def test_scores_are_also_reported_per_category(tmp_path: Path) -> None:
    make_judgement_task(tmp_path)
    log = run_mock(tmp_path, [ModelOutput.from_content("mockllm/model", "Already done.")])
    metrics = {score.name: set(score.metrics) for score in log.results.scores}
    assert any("judgement" in name for name in metrics["clean"] - {"mean"})
    assert any("judgement" in name for name in metrics["solved"] - {"mean"})


def test_read_truncates_like_pi_and_says_how_to_continue(tmp_path: Path) -> None:
    """At most 2000 lines (or 50KB) per read, then pi's own notice naming the offset to continue from."""
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    ws.write("big.txt", "".join(f"line {n}\n" for n in range(1, 2501)))
    out, err = ws.call("read", {"path": "big.txt"})
    assert not err
    assert out.splitlines()[1999] == "line 2000"
    assert out.endswith("\n\n[500 more lines in file. Use offset=2001 to continue.]")
    out, _err = ws.call("read", {"path": "big.txt", "offset": 2001})
    assert out.startswith("line 2001\n") and "more lines" not in out
    out, _err = ws.call("read", {"path": "big.txt", "offset": 20, "limit": 12})
    assert out.endswith("[2469 more lines in file. Use offset=32 to continue.]")


def test_read_stops_at_50kb(tmp_path: Path) -> None:
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    ws.write("wide.txt", ("x" * 1023 + "\n") * 100)
    out, _err = ws.call("read", {"path": "wide.txt"})
    assert out.endswith("[50 more lines in file. Use offset=51 to continue.]")


def make_changing_task(root: Path) -> Path:
    """The double task, where a teammate renames the function's argument once the model first touches the file."""
    task = make_task(root)
    manifest = json.loads((task / "manifest.json").read_text())
    manifest["on_first_touch"] = {"solution.py": [["(n)", "(number)"]]}
    (task / "manifest.json").write_text(json.dumps(manifest))
    return task


def test_a_change_lands_after_the_first_read_so_a_stale_edit_fails(tmp_path: Path) -> None:
    ws = Workspace.create(load_task(make_changing_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    out, _err = ws.call("read", {"path": "solution.py"})
    assert "double(n)" in out  # the model sees the file as it was
    assert "double(number)" in (ws.root / "solution.py").read_text()  # then the teammate's change lands
    _out, err = ws.call("edit", {"path": "solution.py", "edits": [{"oldText": "double(n)", "newText": "double(k)"}]})
    assert err
    assert ws.changes_made == ["solution.py"]


def test_naming_the_file_in_a_command_also_counts_as_touching_it(tmp_path: Path) -> None:
    ws = Workspace.create(load_task(make_changing_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    ws.call("bash", {"command": "ls"})
    assert ws.changes_made == []
    out, _err = ws.call("bash", {"command": "cat solution.py"})
    assert "double(n)" in out
    assert ws.changes_made == ["solution.py"]


def test_solving_after_a_failure_counts_as_recovered(tmp_path: Path) -> None:
    make_task(tmp_path)
    outputs = [
        ModelOutput.for_tool_call("mockllm/model", "read", {"path": "missing.py"}),
        ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED}),
        ModelOutput.from_content("mockllm/model", "Done."),
    ]
    value, _run = scored(run_mock(tmp_path, outputs))
    assert (value["hit_failure"], value["recovered"], value["solved"]) == (1, 1, 1)


def test_a_clean_run_has_nothing_to_recover_from(tmp_path: Path) -> None:
    make_task(tmp_path)
    write = ModelOutput.for_tool_call("mockllm/model", "write", {"path": "solution.py", "content": SOLVED})
    value, _run = scored(run_mock(tmp_path, [write, ModelOutput.from_content("mockllm/model", "Done.")]))
    assert (value["hit_failure"], value["recovered"]) == (0, 0)


def test_commands_never_see_secrets_or_host_uv_settings(tmp_path: Path, monkeypatch) -> None:
    """The trainer's secrets stay out of transcripts, and Molab's UV_NO_SYNC/UV_PYTHON/PYTHONPATH stay out of tasks."""
    hidden = {
        "HF_TOKEN": "hf-secret",
        "MLFLOW_TRACKING_PASSWORD": "mlflow-secret",
        "DEEPSEEK_API_KEY": "api-secret",
        "UV_NO_SYNC": "1",
        "UV_PYTHON": "3.13.11",
        "PYTHONPATH": "/trainer/site-packages",
        "PYTHONSAFEPATH": "1",
    }
    for name, value in hidden.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("UV_CACHE_DIR", "/kept/cache")
    ws = Workspace.create(load_task(make_task(tmp_path)), tmp_path / "runs", SCHEMAS)
    out, _err = ws.call("bash", {"command": "env"})
    seen = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    assert not set(hidden) & set(seen)
    assert not {"hf-secret", "mlflow-secret", "api-secret"} & set(seen.values())
    assert seen["UV_CACHE_DIR"] == "/kept/cache"
