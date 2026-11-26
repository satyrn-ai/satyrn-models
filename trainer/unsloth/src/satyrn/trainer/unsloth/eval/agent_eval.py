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

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageTool, get_model
from inspect_ai.scorer import Score, Scorer, Target, grouped, mean, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import ToolDef, ToolParams
from jsonschema import Draft202012Validator  # a dependency of inspect_ai
from jsonschema.exceptions import best_match

# The tasks kept with this module; SATYRN_EVALS_TASKS may point at a satyrn-evals checkout instead
AGENT_TASKS = Path(__file__).resolve().parent / "agent_tasks"
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
# pi's read tool: "output is truncated to 2000 lines or 50KB (whichever is hit first)"
READ_MAX_LINES = 2000
READ_MAX_BYTES = 50 * 1024
BASH_TIMEOUT = 120
TEXT_TOOL_CALL = re.compile(r"<tool_call>|<\|tool_call>|\"name\"\s*:\s*\"(read|bash|edit|write)\"")
TOOL_NAMES = ("read", "bash", "edit", "write")
# Greedy decoding repeats itself exactly once it starts looping, so the same turn this many times in a row ends it
LOOP_REPEATS = 3
# Bounds the long tail: a model that wanders without repeating itself exactly would otherwise set the eval's run time
# (one such sample took 30 turns and doubled the eval to 14 minutes); 90% of agentic SFT sessions take 11 turns or fewer
MAX_TURNS = 15
# How a sample ended
STOPPED, TEXT_TOOL_CALL_END, LOOPED, TURN_CAP = "stopped", "text_tool_call", "looped", "turn_cap"


@dataclass(frozen=True)
class AgentTask:
    """One task: the prompt, its starting files and how it is graded.

    Beyond the satyrn-evals manifest, a task may set `category` (finish, recover or judgement), `max_calls` (solved
    only within that many tool calls) and `protected_paths` (solved only if those files are left as in `base/`), for
    behaviour that hidden tests cannot see, such as leaving finished work alone. `on_first_touch` maps a path to
    text replacements made right after the model's first tool call that names that file, standing in for a
    teammate's change landing mid-task, so an edit built from the earlier read fails and has to be redone.
    """

    name: str
    contract: str
    base: Path
    overlay: Path | None
    expected: list[str]
    oracle_env: dict[str, str] = field(default_factory=dict)
    category: str = "other"
    max_calls: int | None = None
    protected: dict[str, str] = field(default_factory=dict)  # path -> sha256 of the file in base/
    on_first_touch: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


def file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_task(task_dir: Path) -> AgentTask:
    """Read a task directory in the satyrn-evals layout."""
    manifest = json.loads((task_dir / "manifest.json").read_text())
    overlay = task_dir / manifest["grader_overlay"] if manifest.get("grader_overlay") else None
    oracle = manifest.get("oracle") or []
    # an oracle such as `env PYTHONPATH=scripts python -m pytest` names the environment its tests need
    oracle_env = dict(arg.split("=", 1) for arg in oracle[1:] if "=" in arg) if oracle[:1] == ["env"] else {}
    base = task_dir / "base"
    protected = {path: file_digest(base / path) for path in manifest.get("protected_paths", [])}
    return AgentTask(
        manifest["name"],
        manifest["contract"],
        base,
        overlay,
        manifest["expected_test_ids"],
        oracle_env,
        manifest.get("category", "other"),
        manifest.get("max_calls"),
        protected,
        {path: [tuple(pair) for pair in pairs] for path, pairs in manifest.get("on_first_touch", {}).items()},
    )


# Never passed to the model's commands or to grading: the trainer's secrets (they would end up in transcripts
# logged to MLflow), and settings of the training host that change how Python and uv behave in a task's repository
# (Molab sets UV_NO_SYNC and UV_PYTHON, so `uv run` skipped installing a task's dependencies; PYTHONPATH, which
# leaked the trainer's packages into the task; and PYTHONSAFEPATH, so `python -m pytest` could not import the
# project's own modules)
HIDDEN_ENV = re.compile(
    r"^(UV_NO_SYNC|UV_PYTHON|UV_FROZEN|UV_OFFLINE|UV_PROJECT_ENVIRONMENT|PYTHONPATH|PYTHONHOME|PYTHONSAFEPATH|VIRTUAL_ENV"
    r"|VIRTUAL_ENV_PROMPT)$|^(HF_|HUGGING_FACE|MLFLOW_)|TOKEN|KEY|PASSWORD|SECRET|CREDENTIAL",
    re.IGNORECASE,
)


def task_env() -> dict[str, str]:
    """The environment for the model's commands and for grading: the host's, minus HIDDEN_ENV."""
    return {name: value for name, value in os.environ.items() if not HIDDEN_ENV.search(name)}


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return f"{text[: MAX_OUTPUT // 2]}\n...[{len(text) - MAX_OUTPUT} characters cut]...\n{text[-MAX_OUTPUT // 2 :]}"


@dataclass
class ToolStats:
    """Calls to one tool: how many, and how many were invalid or failed."""

    calls: int = 0
    invalid: int = 0
    failed: int = 0


@dataclass
class Workspace:
    """A sample's working folder and the tool calls made in it, executed the way the recording harness did.

    Every call is one of three kinds. *Invalid*: the model got the call itself wrong (an unknown tool, arguments
    that break the tool's schema, or a call that could not be parsed); it is not run. *Failed*: a valid call whose
    operation did not work (a missing file, an edit whose oldText does not match exactly once, a path outside the
    workspace, a command that timed out). *OK*: everything else. A shell command that exits non-zero is OK, since
    a failing test run or a grep with no match is often what the model meant to do; it is counted separately.
    """

    root: Path
    schemas: dict[str, dict] = field(default_factory=dict)
    calls: int = 0
    invalid: int = 0
    failed: int = 0
    escapes: int = 0
    command_exit_nonzero: int = 0
    by_tool: dict[str, ToolStats] = field(default_factory=dict)
    pending_changes: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    changes_made: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, agent_task: AgentTask, runs_dir: Path, schemas: dict[str, dict] | None = None) -> Workspace:
        root = runs_dir / f"satyrn-agent-eval-{uuid.uuid4().hex[:12]}" / agent_task.name / "project-workspace"
        shutil.copytree(agent_task.base, root, ignore=COPY_IGNORE)
        return cls(root.resolve(), schemas or {}, pending_changes=dict(agent_task.on_first_touch))

    def _apply_pending_changes(self, name: str, arguments: dict) -> None:
        """Make each pending change once the model has touched its file: named it in a path, or in a command."""
        for path in list(self.pending_changes):
            named = arguments.get("path") and self.resolve(str(arguments["path"])) == self.root / path
            if named or (name == "bash" and Path(path).name in str(arguments.get("command", ""))):
                target = self.root / path
                text = target.read_text()
                for old, new in self.pending_changes.pop(path):
                    text = text.replace(old, new)
                target.write_text(text)
                self.changes_made.append(path)

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
        end = min(len(lines), start + int(limit) if limit else len(lines), start + READ_MAX_LINES)
        size = 0
        for index in range(start, end):
            size += len(lines[index].encode())
            if size > READ_MAX_BYTES:
                end = max(index, start + 1)
                break
        text = "".join(lines[start:end])
        if end < len(lines):  # pi's own notice, as the model saw it in training
            text += f"\n\n[{len(lines) - end} more lines in file. Use offset={end + 1} to continue.]"
        return text, False

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
            done = subprocess.run(
                command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=limit, env=task_env()
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {limit:g}s", True
        output = _clip((done.stdout + done.stderr).strip())
        if done.returncode:
            self.command_exit_nonzero += 1
            return f"{output}\n\nCommand exited with code {done.returncode}", False
        return output or "(no output)", False

    def _stats(self, name: str) -> ToolStats:
        self.calls += 1
        stats = self.by_tool.setdefault(name, ToolStats())
        stats.calls += 1
        return stats

    def reject(self, name: str, why: str) -> str:
        """Count an invalid call, which is not run, and return the error the model sees."""
        self._stats(name).invalid += 1
        self.invalid += 1
        return f"Error: {why}"

    def problem(self, name: str, arguments: dict) -> str | None:
        """Why a call is invalid (an unknown tool, or arguments that break the tool's schema), or None."""
        if name not in (self.schemas or TOOL_NAMES):
            return f"unknown tool {name}"
        schema = self.schemas.get(name)
        error = best_match(Draft202012Validator(schema).iter_errors(arguments)) if schema else None
        if error is None:
            return None
        where = ".".join(str(part) for part in error.absolute_path)
        return f"invalid arguments for {name}{f' at {where}' if where else ''}: {error.message}"

    def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Run one tool call; an invalid call or failed operation is an error result, never an exception."""
        if why := self.problem(name, arguments):
            return self.reject(name, why), True
        stats = self._stats(name)
        try:
            if name == "read":
                out, failed = self.read(arguments["path"], arguments.get("offset"), arguments.get("limit"))
            elif name == "write":
                out, failed = self.write(arguments["path"], arguments["content"])
            elif name == "edit":
                out, failed = self.edit(arguments["path"], arguments["edits"])
            else:
                out, failed = self.bash(arguments["command"], arguments.get("timeout"))
        except (KeyError, TypeError, ValueError, AttributeError) as bad:
            # without schemas (a bare Workspace) a malformed call surfaces here instead; it is still invalid
            stats.invalid += 1
            self.invalid += 1
            return f"Error: bad arguments for {name}: {bad}", True
        stats.failed += failed
        self.failed += failed
        self._apply_pending_changes(name, arguments)
        return out, failed


def grade(workspace: Workspace, agent_task: AgentTask) -> set[str]:
    """Expected test ids that pass on a copy of the workspace with the hidden overlay added."""
    if not agent_task.expected:
        return set()
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
        schemas = {spec["function"]["name"]: spec["function"]["parameters"] for spec in recorded_session()[1]}
        ws = Workspace.create(agent_task, Path(runs_dir or tempfile.gettempdir()), schemas)
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
            "protected_changed": sorted(
                path for path, digest in agent_task.protected.items() if file_digest(ws.root / path) != digest
            ),
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
    tasks_dir: str | None = None,
    tasks: list[str] | None = None,
    max_turns: int = MAX_TURNS,
    loop_repeats: int = LOOP_REPEATS,
) -> Task:
    """Build the agent-behaviour eval: every task in AGENT_TASKS, or the named `tasks`, or ["all"].

    `tasks_dir` (or SATYRN_EVALS_TASKS) points at another task directory, such as a satyrn-evals checkout, where
    only DEFAULT_TASKS run unless `tasks` says otherwise.
    """
    root = Path(tasks_dir or os.environ.get(TASKS_ENV) or AGENT_TASKS)
    present = sorted(p.parent.name for p in root.glob("*/manifest.json"))
    default = present if root == AGENT_TASKS else DEFAULT_TASKS
    names = present if tasks == ["all"] else [name for name in tasks or default if name in present]
    samples = []
    for name in names:
        agent_task = load_task(root / name)
        samples.append(
            Sample(
                id=agent_task.name,
                input=agent_task.contract,
                metadata={
                    "task_dir": str(root / name),
                    "expected": agent_task.expected,
                    "category": agent_task.category,
                },
            )
        )
    solver = agent_loop(max_turns, None, loop_repeats)
    return Task(dataset=MemoryDataset(samples), solver=solver, scorer=agent_behaviour())
