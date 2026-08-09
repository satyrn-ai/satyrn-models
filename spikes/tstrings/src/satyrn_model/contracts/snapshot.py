"""DatasetSnapshot: the immutable, versioned dataset a producer ships.

A snapshot is an immutable manifest plus an ordered tuple of task records. The
manifest carries the contract version, the task count, and a content
fingerprint over all tasks. Ingest validates the manifest and every task
*before executing anything*: contract version, duplicate ids, id/content
mismatch, policy registration and version, completion mode, check/provenance
shape, and the absence of any caller-supplied expected value. Only after all
of those pass does the provider move on to reference materialization (Task 2).

The canonical fixture (``tests/fixtures/contracts/v1/snapshot.json``) is the
single byte-identical round-trip witness; both this checkout and, after this
branch lands, the data project's checkout validate against it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

from ._common import ContractError, reject_unknown_keys, require_object, require_str
from .policy import PolicyRegistry
from .task import TaskRecord, semantic_content_id
from .versions import DATASET_CONTRACT_VERSION


def _tasks_fingerprint(tasks: tuple[TaskRecord, ...]) -> str:
    """SHA-256 over the canonical, sorted JSON of all task records (incl. ids)."""
    payload = json.dumps(
        [task.to_dict() for task in tasks], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True, kw_only=True)
class Manifest:
    contract_version: str
    task_count: int
    fingerprint: str

    @classmethod
    def from_dict(cls, data: object) -> Manifest:
        data = require_object(data, "manifest")
        for field in ("contract_version", "task_count", "fingerprint"):
            if field not in data:
                raise ContractError(f"manifest missing field: {field}")
        reject_unknown_keys(
            data,
            frozenset({"contract_version", "task_count", "fingerprint"}),
            "manifest",
        )
        contract_version = require_str(
            data["contract_version"], "manifest contract_version"
        )
        task_count = data["task_count"]
        if (
            not isinstance(task_count, int)
            or isinstance(task_count, bool)
            or task_count < 0
        ):
            raise ContractError("manifest task_count must be a non-negative integer")
        fingerprint = require_str(data["fingerprint"], "manifest fingerprint")
        return cls(
            contract_version=contract_version,
            task_count=task_count,
            fingerprint=fingerprint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "task_count": self.task_count,
            "fingerprint": self.fingerprint,
        }


@dataclasses.dataclass(frozen=True, kw_only=True)
class DatasetSnapshot:
    tasks: tuple[TaskRecord, ...]
    manifest: Manifest

    @classmethod
    def from_tasks(
        cls, tasks: tuple[TaskRecord, ...] | list[TaskRecord]
    ) -> DatasetSnapshot:
        """Build a snapshot, deriving the manifest from the tasks."""
        tasks_tuple = tuple(tasks)
        return cls(
            tasks=tasks_tuple,
            manifest=Manifest(
                contract_version=DATASET_CONTRACT_VERSION,
                task_count=len(tasks_tuple),
                fingerprint=_tasks_fingerprint(tasks_tuple),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "tasks": [task.to_dict() for task in self.tasks],
        }


def ingest_snapshot(data: object, *, registry: PolicyRegistry) -> DatasetSnapshot:
    """Validate and parse a snapshot dict before any execution.

    Raises ``ContractError`` for any contract violation. ``registry`` is the
    injectable trusted policy lookup; ingest only checks registration and
    version, it never resolves executable policy behaviour (Task 2/3).
    """
    snapshot_dict = require_object(data, "snapshot")
    if "manifest" not in snapshot_dict:
        raise ContractError("snapshot missing 'manifest'")
    if "tasks" not in snapshot_dict:
        raise ContractError("snapshot missing 'tasks'")
    reject_unknown_keys(snapshot_dict, frozenset({"manifest", "tasks"}), "snapshot")

    manifest = Manifest.from_dict(snapshot_dict["manifest"])
    if manifest.contract_version != DATASET_CONTRACT_VERSION:
        raise ContractError(
            f"contract version mismatch: snapshot is {manifest.contract_version!r}, "
            f"provider expects {DATASET_CONTRACT_VERSION!r}"
        )

    raw_tasks = snapshot_dict["tasks"]
    if not isinstance(raw_tasks, list):
        raise ContractError("snapshot 'tasks' must be a list")

    tasks: list[TaskRecord] = []
    seen_ids: dict[str, int] = {}
    seen_semantic_ids: dict[str, int] = {}
    for index, raw in enumerate(raw_tasks):
        task = TaskRecord.from_dict(raw)
        _check_policy(task, registry, index)
        tasks.append(task)
        if task.id in seen_ids:
            raise ContractError(
                "duplicate task id "
                f"{task.id!r} at index {index} (first at {seen_ids[task.id]})"
            )
        seen_ids[task.id] = index
        semantic_id = semantic_content_id(task)
        if semantic_id in seen_semantic_ids:
            raise ContractError(
                "duplicate semantic task content "
                f"{semantic_id!r} at index {index} "
                f"(first at {seen_semantic_ids[semantic_id]})"
            )
        seen_semantic_ids[semantic_id] = index

    if manifest.task_count != len(tasks):
        raise ContractError(
            "manifest task_count "
            f"{manifest.task_count} does not match {len(tasks)} task(s)"
        )
    if manifest.fingerprint != _tasks_fingerprint(tuple(tasks)):
        raise ContractError("manifest fingerprint does not match task content")

    return DatasetSnapshot(tasks=tuple(tasks), manifest=manifest)


def _check_policy(task: TaskRecord, registry: PolicyRegistry, index: int) -> None:
    ref = task.policy
    if ref.id not in registry.registered_policy_ids():
        raise ContractError(f"task {index}: unregistered policy {ref.id!r}")
    if ref.version not in registry.known_versions(ref.id):
        raise ContractError(
            f"task {index}: policy version mismatch: "
            f"{ref.id!r} has no version {ref.version}"
        )


def load_snapshot(path: Path, *, registry: PolicyRegistry) -> DatasetSnapshot:
    """Read a JSON snapshot file and ingest it."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read snapshot at {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(f"malformed json at {path}: {exc}") from exc
    return ingest_snapshot(data, registry=registry)


def dump_snapshot(snapshot: DatasetSnapshot) -> str:
    """Canonical, byte-stable JSON text (sorted keys, 2-space indent, trailing newline).

    The canonical fixture is exactly this output, so loading and re-dumping a
    snapshot is an identity operation on the text.
    """
    return (
        json.dumps(snapshot.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)
        + "\n"
    )


__all__ = [
    "Manifest",
    "DatasetSnapshot",
    "ingest_snapshot",
    "load_snapshot",
    "dump_snapshot",
]
