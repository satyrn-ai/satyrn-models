"""The working folder of one sample and the tool calls the model makes in it."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from jsonschema import Draft202012Validator  # a dependency of inspect_ai
from jsonschema.exceptions import best_match

if TYPE_CHECKING:
    from satyrn.trainer.unsloth.eval.agent_eval.agent_task import AgentTask

COPY_IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.pyc", ".git")
MAX_OUTPUT = 20_000
# pi's read tool: "output is truncated to 2000 lines or 50KB (whichever is hit first)"
READ_MAX_LINES = 2000
READ_MAX_BYTES = 50 * 1024
BASH_TIMEOUT = 120
TOOL_NAMES = ("read", "bash", "edit", "write")

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
