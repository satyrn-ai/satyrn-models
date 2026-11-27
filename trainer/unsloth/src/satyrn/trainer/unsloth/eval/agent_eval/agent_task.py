"""The tasks of the agent eval."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DirectorySnapshot = dict[str, str]  # relative path -> file text


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
    expected: list[str]
    system_prompt: str
    tools: list[dict]
    manifest: dict
    files: DirectorySnapshot
    oracle_env: dict[str, str] = field(default_factory=dict)
    category: str = "other"
    max_calls: int | None = None
    protected: list[str] = field(default_factory=list)
    on_first_touch: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: dict, files: DirectorySnapshot) -> AgentTask:
        """Build a task from its manifest and its other files."""
        oracle = manifest.get("oracle") or []
        # an oracle such as `env PYTHONPATH=scripts python -m pytest` names the environment its tests need
        oracle_env = dict(arg.split("=", 1) for arg in oracle[1:] if "=" in arg) if oracle[:1] == ["env"] else {}
        on_first_touch = {
            path: [tuple(pair) for pair in pairs] for path, pairs in manifest.get("on_first_touch", {}).items()
        }
        return cls(
            name=manifest["name"],
            contract=manifest["contract"],
            expected=manifest["expected_test_ids"],
            system_prompt=manifest["system_prompt"],
            tools=manifest["tools"],
            manifest=manifest,
            files=files,
            oracle_env=oracle_env,
            category=manifest.get("category", "other"),
            max_calls=manifest.get("max_calls"),
            protected=manifest.get("protected_paths", []),
            on_first_touch=on_first_touch,
        )

    @classmethod
    def from_directory(cls, task_dir: Path) -> AgentTask:
        """Read a task folder."""
        manifest_path = task_dir / "manifest.json"
        files = {
            path.relative_to(task_dir).as_posix(): path.read_text()
            for path in sorted(task_dir.rglob("*"))
            if path.is_file() and path != manifest_path
        }
        return cls.from_manifest(json.loads(manifest_path.read_text()), files)

    @classmethod
    def from_json(cls, line: str) -> AgentTask:
        """Read a task from one JSONL line."""
        record = json.loads(line)
        return cls.from_manifest(record["manifest"], record["files"])

    def to_json(self) -> str:
        """Return the task as one JSONL line."""
        return json.dumps({"manifest": self.manifest, "files": self.files})

    def to_directory(self, destination: Path) -> None:
        """Write the task as a folder named after it under destination."""
        task_dir = destination / self.name
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n")
        self.write_files(task_dir)

    def write_files(self, destination: Path, folder: str = "") -> None:
        """Write the files under folder, or all files, to destination."""
        prefix = f"{folder}/" if folder else ""
        for relative_path, text in self.files.items():
            if relative_path.startswith(prefix):
                path = destination / relative_path.removeprefix(prefix)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

    def changed_protected_paths(self, root: Path) -> list[str]:
        """Return the protected paths whose file under root no longer matches base/."""
        return [
            path
            for path in self.protected
            if not (root / path).is_file() or (root / path).read_bytes() != self.files[f"base/{path}"].encode()
        ]


def directories_to_jsonl(tasks_dir: Path, jsonl_path: Path) -> None:
    """Write every task folder in tasks_dir to jsonl_path, one line per task."""
    tasks = [AgentTask.from_directory(manifest.parent) for manifest in sorted(tasks_dir.glob("*/manifest.json"))]
    jsonl_path.write_text("".join(task.to_json() + "\n" for task in tasks))


def jsonl_to_directories(jsonl_path: Path, destination: Path) -> None:
    """Write each task in jsonl_path as a folder under destination."""
    for line in jsonl_path.read_text().splitlines():
        AgentTask.from_json(line).to_directory(destination)
