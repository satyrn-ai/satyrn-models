"""inspect_ai task scoring agent behaviour: correct tool calls and knowing when to stop (issue #69).

Each sample is a satyrn-evals task (`manifest.json`, `base/`, an optional hidden `overlay/`). The model works
in a fresh copy of `base/` through the coding tools of the agentic SFT data (read, bash, edit, write) for at most
`max_turns` turns.
The working folder is long and unique per sample, never a short fixed path such as `/workspace`, so a model
that learned to build absolute paths from one fixed folder is caught writing outside its workspace.

The model sees the system prompt and tool schemas it was trained with: both are read from the first row of the
agentic SFT data (`SATYRN_AGENTIC_DATA`, by default `datasets/python3.15/sft-agentic.jsonl`) when the eval runs,
with `<cwd>` naming the sample's real folder. Nothing about the recording harness is kept in code, so the eval
follows the training data if that harness changes.

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
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageTool, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import ToolDef, ToolParams

TASKS_ENV = "SATYRN_EVALS_TASKS"
# Short tasks, so the eval fits after every training stage; pass tasks=["all"] for every task in the directory
DEFAULT_TASKS = [
    "format_number",
    "agentclinic-complaint-lifecycle",
    "agentclinic-repair-depth-2",
    "selfhost-review-script",
]
AGENTIC_DATA_ENV = "SATYRN_AGENTIC_DATA"
AGENTIC_DATA = Path(__file__).resolve().parents[7] / "datasets" / "python3.15" / "sft-agentic.jsonl"
CWD_BLOCK = re.compile(r"<cwd>\n.*?\n</cwd>", re.DOTALL)
COPY_IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.pyc", ".git")
MAX_OUTPUT = 20_000
BASH_TIMEOUT = 120
TEXT_TOOL_CALL = re.compile(r"<tool_call>|<\|tool_call>|\"name\"\s*:\s*\"(read|bash|edit|write)\"")
# Greedy decoding repeats itself exactly once it starts looping, so the same turn this many times in a row ends it
LOOP_REPEATS = 3
# How a sample ended
STOPPED, TEXT_TOOL_CALL_END, LOOPED, TURN_CAP = "stopped", "text_tool_call", "looped", "turn_cap"


@dataclass(frozen=True)
class AgentTask:
    """One satyrn-evals task: the prompt, its starting files and how it is graded."""

    name: str
    contract: str
    base: Path
    overlay: Path | None
    expected: list[str]
    oracle_env: dict[str, str] = field(default_factory=dict)


def load_task(task_dir: Path) -> AgentTask:
    """Read a satyrn-evals task directory."""
    manifest = json.loads((task_dir / "manifest.json").read_text())
    overlay = task_dir / manifest["grader_overlay"] if manifest.get("grader_overlay") else None
    oracle = manifest.get("oracle") or []
    # an oracle such as `env PYTHONPATH=scripts python -m pytest` names the environment its tests need
    oracle_env = dict(arg.split("=", 1) for arg in oracle[1:] if "=" in arg) if oracle[:1] == ["env"] else {}
    return AgentTask(
        manifest["name"], manifest["contract"], task_dir / "base", overlay, manifest["expected_test_ids"], oracle_env
    )


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return f"{text[: MAX_OUTPUT // 2]}\n...[{len(text) - MAX_OUTPUT} characters cut]...\n{text[-MAX_OUTPUT // 2 :]}"


@dataclass
class Workspace:
    """A sample's working folder and the tool calls made in it, executed the way the recording harness did."""

    root: Path
    calls: int = 0
    errors: int = 0
    escapes: int = 0
    invalid: int = 0
    by_tool: dict[str, int] = field(default_factory=dict)

    @classmethod
    def create(cls, agent_task: AgentTask, runs_dir: Path) -> Workspace:
        root = runs_dir / f"satyrn-agent-eval-{uuid.uuid4().hex[:12]}" / agent_task.name / "project-workspace"
        shutil.copytree(agent_task.base, root, ignore=COPY_IGNORE)
        return cls(root.resolve())

    def resolve(self, path: str) -> Path | None:
        """The file a path names, or None if it is outside the workspace."""
        target = (self.root / path).resolve()
        return target if target.is_relative_to(self.root) else None

    def _target(self, path: str) -> tuple[Path | None, str]:
        target = self.resolve(path)
        if target is None:
            self.escapes += 1
            return None, f"Error: {path} is outside the working directory {self.root}"
        return target, ""

    def read(self, path: str, offset: int | None = None, limit: int | None = None) -> tuple[str, bool]:
        target, why = self._target(path)
        if target is None:
            return why, True
        if not target.is_file():
            return f"Error: no such file: {path}", True
        lines = target.read_text(errors="replace").splitlines(keepends=True)
        start = max(int(offset or 1), 1) - 1
        end = start + int(limit) if limit else len(lines)
        return _clip("".join(lines[start:end])), False

    def write(self, path: str, content: str) -> tuple[str, bool]:
        target, why = self._target(path)
        if target is None:
            return why, True
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} characters to {path}", False

    def edit(self, path: str, edits: list[dict]) -> tuple[str, bool]:
        target, why = self._target(path)
        if target is None:
            return why, True
        if not target.is_file():
            return f"Error: no such file: {path}", True
        text = target.read_text(errors="replace")
        for one in edits:
            old, new = one.get("oldText"), one.get("newText", "")
            if not old or text.count(old) != 1:
                found = "nothing" if not old or old not in text else f"{text.count(old)} matches"
                return f"Error: oldText must match exactly once in {path}; found {found}", True
            text = text.replace(old, new, 1)
        target.write_text(text)
        return f"Edited {path}", False

    def bash(self, command: str, timeout: float | None = None) -> tuple[str, bool]:
        limit = min(float(timeout or BASH_TIMEOUT), BASH_TIMEOUT)
        try:
            done = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=limit)
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {limit:g}s", True
        output = _clip((done.stdout + done.stderr).strip())
        if done.returncode:
            return f"{output}\n\nCommand exited with code {done.returncode}", True
        return output or "(no output)", False

    def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Run one tool call; an unknown tool or missing argument is an error result, never an exception."""
        self.calls += 1
        self.by_tool[name] = self.by_tool.get(name, 0) + 1
        try:
            if name == "read":
                out, err = self.read(arguments["path"], arguments.get("offset"), arguments.get("limit"))
            elif name == "write":
                out, err = self.write(arguments["path"], arguments["content"])
            elif name == "edit":
                out, err = self.edit(arguments["path"], arguments["edits"])
            elif name == "bash":
                out, err = self.bash(arguments["command"], arguments.get("timeout"))
            else:
                out, err = f"Error: unknown tool {name}", True
        except (KeyError, TypeError, ValueError) as missing:
            out, err = f"Error: bad arguments for {name}: {missing}", True
        self.errors += err
        return out, err


def grade(workspace: Workspace, agent_task: AgentTask) -> set[str]:
    """Expected test ids that pass on a copy of the workspace with the hidden overlay added."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "grade"
        shutil.copytree(workspace.root, tree, ignore=COPY_IGNORE)
        if agent_task.overlay:
            shutil.copytree(agent_task.overlay, tree, dirs_exist_ok=True)
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
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"} | {"PYTHONPATH": str(tree)}
        for key, value in agent_task.oracle_env.items():
            env[key] = (
                os.pathsep.join(str(tree / part) for part in value.split(os.pathsep)) + os.pathsep + str(tree)
                if key == "PYTHONPATH"
                else value
            )
        done = subprocess.run([*command, *files], cwd=tree, capture_output=True, text=True, env=env)
    output = done.stdout + done.stderr
    return {test_id for test_id in agent_task.expected if f"PASSED {test_id}" in output}


def recorded_session() -> tuple[str, list[dict]]:
    """The system prompt and tool schemas from the first row of the agentic SFT data."""
    path = Path(os.environ.get(AGENTIC_DATA_ENV) or AGENTIC_DATA)
    with path.open() as fh:
        first = fh.readline()
    if first.startswith("version https://git-lfs"):
        raise RuntimeError(f"{path} is a git-lfs pointer: run `git lfs pull` to fetch the agentic SFT data")
    row = json.loads(first)
    return row["prompt"][0]["content"], row["tools"]


def system_prompt(root: Path) -> str:
    """The recorded system prompt, with its <cwd> block naming the sample's real working folder."""
    system, _tools = recorded_session()
    return CWD_BLOCK.sub(lambda _match: f"<cwd>\n{root}\n</cwd>", system)


async def _executed_by_workspace(**_arguments: object) -> str:
    raise NotImplementedError  # the solver executes calls through its Workspace


def agent_tools() -> list[ToolDef]:
    """The recorded tools, with the exact names, descriptions and parameter schemas of the training data."""
    return [
        ToolDef(
            _executed_by_workspace,
            name=spec["function"]["name"],
            description=spec["function"]["description"],
            parameters=ToolParams.model_validate(spec["function"]["parameters"]),
        )
        for spec in recorded_session()[1]
    ]


def turn_signature(tool_calls: list) -> tuple:
    """What a turn asked for: its calls' names and arguments, in order, ignoring call ids."""
    return tuple((call.function, json.dumps(call.arguments, sort_keys=True, default=str)) for call in tool_calls)


@solver
def agent_loop(max_turns: int, runs_dir: str | None, loop_repeats: int = LOOP_REPEATS) -> Solver:
    """Let the model call tools until it answers without one, repeats itself, or reaches max_turns turns."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        agent_task = load_task(Path(state.metadata["task_dir"]))
        ws = Workspace.create(agent_task, Path(runs_dir or tempfile.gettempdir()))
        state.messages.insert(0, ChatMessageSystem(content=system_prompt(ws.root)))
        tools, model = agent_tools(), get_model()
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
                    ws.calls += 1
                    ws.invalid += 1
                    result = f"Error: could not parse the tool call arguments: {call.parse_error}"
                else:
                    result, _err = ws.call(call.function, call.arguments)
                state.messages.append(ChatMessageTool(content=result, tool_call_id=call.id, function=call.function))
        state.metadata["agent"] = {
            "workspace": str(ws.root),
            "turns": turns,
            "ending": ending,
            "self_stop": ending == STOPPED,
            "calls": ws.calls,
            "errors": ws.errors,
            "workspace_escapes": ws.escapes,
            "invalid_tool_calls": ws.invalid + text_calls,
            "by_tool": ws.by_tool,
            "passed": sorted(grade(ws, agent_task)),
        }
        return state

    return solve


@scorer(
    metrics={
        "clean": [mean()],
        "solved": [mean()],
        "self_stop": [mean()],
        "premature_stop": [mean()],
        "overrun": [mean()],
        "looped": [mean()],
        "tool_error_rate": [mean()],
        "workspace_escapes": [mean()],
        "invalid_tool_calls": [mean()],
        "turns": [mean()],
    }
)
def agent_behaviour() -> Scorer:
    """Score one sample on solving, stopping and the quality of its tool calls."""

    async def score(state: TaskState, target: Target) -> Score:
        run = state.metadata["agent"]
        expected = state.metadata["expected"]
        solved = int(set(expected) <= set(run["passed"]))
        stopped = int(run["self_stop"])
        clean = int(solved and stopped and not run["workspace_escapes"] and not run["invalid_tool_calls"])
        value = {
            "clean": clean,
            "solved": solved,
            "self_stop": stopped,
            "premature_stop": int(stopped and not solved),  # gave up, or believed it was done, unsolved
            "overrun": int(solved and not stopped),  # solved, then kept going
            "looped": int(run["ending"] == LOOPED),
            "tool_error_rate": run["errors"] / run["calls"] if run["calls"] else 0.0,
            "workspace_escapes": run["workspace_escapes"],
            "invalid_tool_calls": run["invalid_tool_calls"],
            "turns": run["turns"],
        }
        explanation = (
            f"ended {run['ending']} after {run['turns']} turns; passed {len(run['passed'])}/{len(expected)} tests; "
            f"tools {run['by_tool']}"
        )
        return Score(value=value, explanation=explanation, metadata=run)

    return score


@task
def agent_eval(
    tasks_dir: str | None = None, tasks: list[str] | None = None, max_turns: int = 30, loop_repeats: int = LOOP_REPEATS
) -> Task:
    """Build the agent-behaviour eval over satyrn-evals tasks: DEFAULT_TASKS, the named `tasks`, or ["all"]."""
    root = Path(tasks_dir or os.environ[TASKS_ENV])
    present = sorted(p.parent.name for p in root.glob("*/manifest.json"))
    names = present if tasks == ["all"] else [name for name in tasks or DEFAULT_TASKS if name in present]
    samples = []
    for name in names:
        agent_task = load_task(root / name)
        samples.append(
            Sample(
                id=agent_task.name,
                input=agent_task.contract,
                metadata={"task_dir": str(root / name), "expected": agent_task.expected},
            )
        )
    solver = agent_loop(max_turns, None, loop_repeats)
    return Task(dataset=MemoryDataset(samples), solver=solver, scorer=agent_behaviour())
