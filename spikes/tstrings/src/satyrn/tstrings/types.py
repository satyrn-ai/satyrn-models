"""Data shapes shared across the t-strings pipeline."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import tomllib

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, kw_only=True)
class SourceSpec:
    """A pinned source to mine t-string usage from."""

    id: str
    repo: str
    tag: str
    commit: str
    license: str
    paths: list[str]


@dataclass(frozen=True, kw_only=True)
class Seed:
    """A t-string usage mined from pinned source."""

    text: str
    source_id: str
    path: str
    line: int


def load_source_specs(toml_path: Path) -> list[SourceSpec]:
    """Read and validate every source entry in a sources.toml file."""
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    specs: list[SourceSpec] = []
    for key, entry in data.items():
        commit = entry.get("commit")
        if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
            raise ValueError(f"source {key!r} must pin a full 40-hex commit SHA")
        for field in ("repo", "license"):
            if not entry.get(field):
                raise ValueError(f"source {key!r} must declare {field!r}")
        if not entry.get("paths"):
            raise ValueError(f"source {key!r} must list paths to mine")
        specs.append(
            SourceSpec(
                id=key,
                repo=entry["repo"],
                tag=entry.get("tag", ""),
                commit=commit,
                license=entry["license"],
                paths=[str(path) for path in entry["paths"]],
            )
        )
    return specs


@dataclass(frozen=True, kw_only=True)
class Provenance:
    """Where a task came from, for audit and licensing."""

    source_id: str
    path: str
    line: int
    license: str


@dataclass(frozen=True, kw_only=True)
class Check:
    """One assertion a candidate program must satisfy."""

    kind: str  # "expected_value" | "expected_stdout" | "uses_feature"
    expected: str  # for uses_feature, the required module or node name


@dataclass(frozen=True, kw_only=True)
class Task:
    """One teachable unit: a prompt, a known-good solution, and its checks."""

    prompt: str
    reference: str
    checks: tuple[Check, ...]
    role: str
    operation: str
    provenance: Provenance
    task_id: str
    semantic_id: str


@dataclass(frozen=True, kw_only=True)
class Accepted:
    """A candidate that passed every check."""

    observations: dict


@dataclass(frozen=True, kw_only=True)
class Rejection:
    """A candidate that failed at a known stage."""

    stage: str  # "syntax" | "import_policy" | "runtime" | "semantic_check"
    detail: str


@dataclass(frozen=True, kw_only=True)
class InfrastructureFailure:
    """A harness failure that says nothing about the candidate."""

    detail: str  # timeout, harness crash, unparseable verdict


Outcome = Accepted | Rejection | InfrastructureFailure


def _canonical_json(obj: object) -> str:
    """Return a canonical JSON string with sorted keys and compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _hash(fields: dict, *, exclude: frozenset[str]) -> str:
    """Return the sha256 of the canonical JSON of fields minus the excluded keys."""
    data = {k: v for k, v in fields.items() if k not in exclude}
    return hashlib.sha256(_canonical_json(data).encode()).hexdigest()


def task_id(fields: dict) -> str:
    """Return the sha256 of every field except task_id and semantic_id."""
    return _hash(fields, exclude=frozenset({"task_id", "semantic_id"}))


def semantic_id(fields: dict) -> str:
    """Return the sha256 of the same fields minus provenance."""
    return _hash(fields, exclude=frozenset({"task_id", "semantic_id", "provenance"}))
