"""TaskRecord: one verified unit of a dataset snapshot.

A task carries the prompt, the reference program, the declarative checks, the
policy reference, the candidate-assembly mode, and provenance. Its ``id`` is a
content-derived digest computed over everything *except* the id itself, so two
producers that author the same content produce the same id, and a mismatch
between a supplied id and the derived content is a hard reject at ingest.

There is deliberately no field for a trusted expected value: the provider
derives every expected observation by executing the reference (Task 2).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ._common import ContractError, reject_unknown_keys, require_object, require_str
from .checks import CheckSpec, checks_from_list
from .completion import CompletionSpec, completion_from_dict
from .policy import PolicyRef
from .provenance import Provenance, provenance_from_dict


def _content_payload(task: TaskRecord) -> dict[str, Any]:
    """The canonical dict used for content-id derivation (excludes ``id``)."""
    return {
        "prompt": task.prompt,
        "reference": task.reference,
        "checks": [check.to_dict() for check in task.checks],
        "policy": task.policy.to_dict(),
        "completion": task.completion.to_dict(),
        "provenance": task.provenance.to_dict(),
    }


def content_id(task: TaskRecord) -> str:
    """Stable SHA-256 digest of a task's content, excluding the id field.

    Deterministic: keys are sorted and separators are compact, so the digest
    does not depend on dict insertion order or whitespace.
    """
    payload = json.dumps(_content_payload(task), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_content_id(task: TaskRecord) -> str:
    """Stable digest of the task content used for learning, not provenance.

    A task's regular ``id`` deliberately includes provenance, so its lineage
    remains immutable and auditable. This separate identity lets consumers
    detect two differently sourced rows that would teach exactly the same
    prompt, reference, checks, policy, and completion behaviour.
    """
    payload = {
        "prompt": task.prompt,
        "reference": task.reference,
        "checks": [check.to_dict() for check in task.checks],
        "policy": task.policy.to_dict(),
        "completion": task.completion.to_dict(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True, kw_only=True)
class TaskRecord:
    prompt: str
    reference: str
    checks: tuple[CheckSpec, ...]
    policy: PolicyRef
    completion: CompletionSpec
    provenance: Provenance
    id: str = dataclasses.field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", content_id(self))

    @classmethod
    def from_dict(cls, data: object) -> TaskRecord:
        data = require_object(data, "task")
        require_task_fields(data)
        reject_unknown_keys(
            data,
            frozenset(
                {
                    "id",
                    "prompt",
                    "reference",
                    "checks",
                    "policy",
                    "completion",
                    "provenance",
                }
            ),
            "task",
        )
        supplied_id = _coerce_str_id(data.get("id"))
        task = cls(
            id=supplied_id,
            prompt=require_str(data["prompt"], "task prompt"),
            reference=require_str(data["reference"], "task reference"),
            checks=checks_from_list(data["checks"]),
            policy=PolicyRef.from_dict(data["policy"]),
            completion=completion_from_dict(data["completion"]),
            provenance=provenance_from_dict(data["provenance"]),
        )
        if supplied_id and supplied_id != content_id(task):
            raise ContractError(
                f"task id does not match content: supplied {supplied_id!r} "
                f"derived {content_id(task)!r}"
            )
        return task

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "reference": self.reference,
            "checks": [check.to_dict() for check in self.checks],
            "policy": self.policy.to_dict(),
            "completion": self.completion.to_dict(),
            "provenance": self.provenance.to_dict(),
        }


def require_task_fields(data: Mapping[str, Any]) -> None:
    missing = [
        field
        for field in (
            "prompt",
            "reference",
            "checks",
            "policy",
            "completion",
            "provenance",
        )
        if field not in data
    ]
    if missing:
        raise ContractError(f"task missing field(s): {', '.join(missing)}")


def _coerce_str_id(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractError(f"task id must be a string, got {type(value).__name__}")
    return value


__all__ = ["TaskRecord", "content_id", "semantic_content_id"]
