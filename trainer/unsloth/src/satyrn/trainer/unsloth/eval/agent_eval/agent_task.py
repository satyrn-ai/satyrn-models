"""The tasks of the agent eval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


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
    system_prompt: str
    tools: list[dict]
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
        manifest["system_prompt"],
        manifest["tools"],
        oracle_env,
        manifest.get("category", "other"),
        manifest.get("max_calls"),
        protected,
        {path: [tuple(pair) for pair in pairs] for path, pairs in manifest.get("on_first_touch", {}).items()},
    )
