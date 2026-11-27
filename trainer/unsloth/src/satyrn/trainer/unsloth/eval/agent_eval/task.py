"""inspect_ai task scoring agent behaviour: correct tool calls and knowing when to stop (issue #69).

Each sample is a satyrn-evals task (`manifest.json`, `base/`, an optional hidden `overlay/`). The model works
in a fresh copy of `base/` through the coding tools of the agentic SFT data (read, bash, edit, write) for at most
`max_turns` turns.
The working folder is long and unique per sample, never a short fixed path such as `/workspace`, so a model
that learned to build absolute paths from one fixed folder is caught writing outside its workspace.

A sample ends in one of four ways: the model stops on its own (a turn with no tool calls), it writes a tool call
as plain text instead of stopping, it repeats the same turn `loop_repeats` times in a row (the repeat is not
run), or it reaches `max_turns`. The workspace is graded however the sample ended, so stopping can be scored
against solving: a premature stop gave up unsolved, an overrun solved the task but did not stop.

A sample is *clean* when the hidden tests pass, the model stopped on its own, and it made no workspace escapes
and no invalid tool calls. The headline score is the share of clean samples; the parts are logged beside it,
named as in satyrn-evals where the two measure the same thing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageTool, get_model
from inspect_ai.scorer import Score, Scorer, Target, grouped, mean, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import ToolDef, ToolParams

from satyrn.trainer.unsloth.eval.agent_eval.agent_task import AgentTask
from satyrn.trainer.unsloth.eval.agent_eval.workspace import Workspace, task_env

TASKS_FILE = Path(__file__).resolve().parents[8] / "datasets" / "eval" / "agent_tasks.jsonl"
CWD_BLOCK = re.compile(r"<cwd>\n.*?\n</cwd>", re.DOTALL)
TEXT_TOOL_CALL = re.compile(r"<tool_call>|<\|tool_call>|\"name\"\s*:\s*\"(read|bash|edit|write)\"")
# Greedy decoding repeats itself exactly once it starts looping, so the same turn this many times in a row ends it
LOOP_REPEATS = 3
# Bounds the long tail: a model that wanders without repeating itself exactly would otherwise set the eval's run time
# (one such sample took 30 turns and doubled the eval to 14 minutes); 90% of agentic SFT sessions take 11 turns or fewer
MAX_TURNS = 15
# How a sample ended
STOPPED, TEXT_TOOL_CALL_END, LOOPED, TURN_CAP = "stopped", "text_tool_call", "looped", "turn_cap"


def grade(workspace: Workspace, agent_task: AgentTask) -> set[str]:
    """Expected test ids that pass on a copy of the workspace with the hidden overlay added."""
    if not agent_task.expected:
        return set()
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "grade"
        caches = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.pyc", ".git")
        shutil.copytree(workspace.root, tree, ignore=caches)
        if overlay := agent_task.manifest.get("grader_overlay"):
            agent_task.write_files(tree, overlay)
        files = sorted({test_id.split("::")[0] for test_id in agent_task.expected})
        if (tree / "pyproject.toml").is_file():
            command = ["uv", "run", "--with", "pytest", "python", "-m", "pytest", "-rA", "-p", "no:cacheprovider"]
        else:
            # never the running interpreter: pytest is a dev extra and may not be installed where the eval runs
            command = [
                "uv",
                "run",
                "--no-project",
                "--with",
                "pytest",
                "python",
                "-m",
                "pytest",
                "-rA",
                "-p",
                "no:cacheprovider",
            ]
        env = task_env() | {"PYTHONPATH": str(tree)}
        for key, value in agent_task.oracle_env.items():
            env[key] = (
                os.pathsep.join(str(tree / part) for part in value.split(os.pathsep)) + os.pathsep + str(tree)
                if key == "PYTHONPATH"
                else value
            )
        done = subprocess.run([*command, *files], cwd=tree, capture_output=True, text=True, env=env)
    output = done.stdout + done.stderr
    return {test_id for test_id in agent_task.expected if f"PASSED {test_id}" in output}


def system_prompt(template: str, root: Path) -> str:
    """The system prompt, with its <cwd> block naming the sample's real working folder."""
    return CWD_BLOCK.sub(lambda _match: f"<cwd>\n{root}\n</cwd>", template)


async def _executed_by_workspace(**_arguments: object) -> str:
    raise NotImplementedError  # the solver executes calls through its Workspace


def agent_tools(specs: list[dict]) -> list[ToolDef]:
    """Return an inspect_ai ToolDef for each tool schema in specs."""
    return [
        ToolDef(
            _executed_by_workspace,
            name=spec["function"]["name"],
            description=spec["function"]["description"],
            parameters=ToolParams.model_validate(spec["function"]["parameters"]),
        )
        for spec in specs
    ]


def turn_signature(tool_calls: list) -> tuple:
    """What a turn asked for: its calls' names and arguments, in order, ignoring call ids."""
    return tuple((call.function, json.dumps(call.arguments, sort_keys=True, default=str)) for call in tool_calls)


@solver
def agent_loop(tasks_file: str, max_turns: int, loop_repeats: int = LOOP_REPEATS) -> Solver:
    """Let the model call tools until it answers without one, repeats itself, or reaches max_turns turns."""
    lines = Path(tasks_file).read_text().splitlines()
    tasks = {task.name: task for task in map(AgentTask.from_json, lines)}

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        agent_task = tasks[state.sample_id]
        ws = Workspace.create(agent_task, Path(tempfile.gettempdir()))
        state.messages.insert(0, ChatMessageSystem(content=system_prompt(agent_task.system_prompt, ws.root)))
        tools, model = agent_tools(agent_task.tools), get_model()
        ending, text_calls, turns = TURN_CAP, 0, 0
        last_signature, repeats = None, 0
        for turns in range(1, max_turns + 1):  # noqa: B007 - the last turn number is the turn count
            output = await model.generate(state.messages, tools)
            message = output.message
            state.messages.append(message)
            if not message.tool_calls:
                text_calls += bool(TEXT_TOOL_CALL.search(message.text or ""))
                ending = TEXT_TOOL_CALL_END if text_calls else STOPPED
                break
            signature = turn_signature(message.tool_calls)
            repeats = repeats + 1 if signature == last_signature else 1
            last_signature = signature
            if repeats >= loop_repeats:
                ending = LOOPED  # the repeat is not run: it would only return the same results again
                break
            for call in message.tool_calls:
                if call.parse_error:
                    result = ws.reject(call.function, f"could not parse the tool call arguments: {call.parse_error}")
                else:
                    result, _err = ws.call(call.function, call.arguments)
                state.messages.append(ChatMessageTool(content=result, tool_call_id=call.id, function=call.function))
        state.metadata["agent"] = {
            "workspace": str(ws.root),
            "turns": turns,
            "ending": ending,
            "self_stop": ending == STOPPED,
            "calls": ws.calls + text_calls,  # a tool call written as text is an attempted call
            "invalid_tool_calls": ws.invalid + text_calls,
            "failed_calls": ws.failed,
            "command_exit_nonzero": ws.command_exit_nonzero,
            "workspace_escapes": ws.escapes,
            "by_tool": {name: asdict(stats) for name, stats in ws.by_tool.items()},
            "passed": sorted(grade(ws, agent_task)),
            "max_calls": agent_task.max_calls,
            "changes_made": ws.changes_made,
            "protected_changed": sorted(agent_task.changed_protected_paths(ws.root)),
        }
        return state

    return solve


@scorer(
    metrics={
        "clean": [mean(), grouped(mean(), "category", all=False, name_template="{group_name}")],
        "solved": [mean(), grouped(mean(), "category", all=False, name_template="{group_name}")],
        "self_stop": [mean()],
        "premature_stop": [mean()],
        "overrun": [mean()],
        "looped": [mean()],
        "hit_failure": [mean()],
        "recovered": [mean()],
        "invalid_call_rate": [mean()],
        "failed_call_rate": [mean()],
        "invalid_tool_calls": [mean()],
        "command_exit_nonzero": [mean()],
        "workspace_escapes": [mean()],
        "turns": [mean()],
    }
)
def agent_behaviour() -> Scorer:
    """Score one sample on solving, stopping and the quality of its tool calls."""

    async def score(state: TaskState, target: Target) -> Score:
        run = state.metadata["agent"]
        expected = state.metadata["expected"]
        within_calls = run["max_calls"] is None or run["calls"] <= run["max_calls"]
        solved = int(set(expected) <= set(run["passed"]) and within_calls and not run["protected_changed"])
        stopped = int(run["self_stop"])
        hit_failure = bool(run["invalid_tool_calls"] or run["failed_calls"] or run["command_exit_nonzero"])
        clean = int(solved and stopped and not run["workspace_escapes"] and not run["invalid_tool_calls"])
        value = {
            "clean": clean,
            "solved": solved,
            "self_stop": stopped,
            "premature_stop": int(stopped and not solved),  # gave up, or believed it was done, unsolved
            "overrun": int(solved and not stopped),  # solved, then kept going
            "looped": int(run["ending"] == LOOPED),
            # recovery: a sample that hit an invalid or failed call, or a failing command, and still solved the task;
            # recovered / hit_failure is the share of samples that recovered from a failure
            "hit_failure": int(hit_failure),
            "recovered": int(hit_failure and bool(solved)),
            # the model got the call itself wrong, as a share of all attempted calls
            "invalid_call_rate": run["invalid_tool_calls"] / run["calls"] if run["calls"] else 0.0,
            # a valid call whose operation did not work, as a share of the calls that ran
            "failed_call_rate": run["failed_calls"] / ran if (ran := run["calls"] - run["invalid_tool_calls"]) else 0.0,
            "invalid_tool_calls": run["invalid_tool_calls"],
            "command_exit_nonzero": run["command_exit_nonzero"],
            "workspace_escapes": run["workspace_escapes"],
            "turns": run["turns"],
        }
        tools = ", ".join(f"{n} {t['calls']} ({t['invalid']}/{t['failed']})" for n, t in run["by_tool"].items())
        explanation = (
            f"ended {run['ending']} after {run['turns']} turns; passed {len(run['passed'])}/{len(expected)} tests; "
            f"calls (invalid/failed): {tools or 'none'}"
            + (f"; changed protected {run['protected_changed']}" if run["protected_changed"] else "")
            + ("" if within_calls else f"; over the {run['max_calls']}-call limit")
        )
        return Score(value=value, explanation=explanation, metadata=run)

    return score


@task
def agent_eval(
    tasks_file: str | None = None,
    tasks: list[str] | None = None,
    max_turns: int = MAX_TURNS,
    loop_repeats: int = LOOP_REPEATS,
) -> Task:
    """Build the agent-behaviour eval over every task in tasks_file, or only the named `tasks`."""
    tasks_file = tasks_file or str(TASKS_FILE)
    samples = []
    for line in Path(tasks_file).read_text().splitlines():
        agent_task = AgentTask.from_json(line)
        if tasks is None or agent_task.name in tasks:
            metadata = {"expected": agent_task.expected, "category": agent_task.category}
            samples.append(Sample(id=agent_task.name, input=agent_task.contract, metadata=metadata))
    solver = agent_loop(tasks_file, max_turns, loop_repeats)
    return Task(dataset=MemoryDataset(samples), solver=solver, scorer=agent_behaviour())
