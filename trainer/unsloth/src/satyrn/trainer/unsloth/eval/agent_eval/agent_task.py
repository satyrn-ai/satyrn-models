"""The tasks of the agent eval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

DirectorySnapshot = dict[str, str]  # relative path -> file text


@dataclass(frozen=True)
class AgentTask:
    """One task: its prompt, its files and how it is graded."""

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
    protected: dict[str, str] = field(default_factory=dict)  # path -> sha256 of the file in base/
    on_first_touch: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: dict, files: DirectorySnapshot) -> AgentTask:
        """Build a task from its manifest and its other files."""
        oracle = manifest.get("oracle") or []
        # an oracle such as `env PYTHONPATH=scripts python -m pytest` names the environment its tests need
        oracle_env = dict(arg.split("=", 1) for arg in oracle[1:] if "=" in arg) if oracle[:1] == ["env"] else {}
        protected = {
            path: hashlib.sha256(files[f"base/{path}"].encode()).hexdigest()
            for path in manifest.get("protected_paths", [])
        }
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
            protected=protected,
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

    def write_files(self, destination: Path, folder: str = "") -> None:
        """Write the files under folder, or all files, to destination."""
        prefix = f"{folder}/" if folder else ""
        for relative_path, text in self.files.items():
            if relative_path.startswith(prefix):
                path = destination / relative_path.removeprefix(prefix)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)


def file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
