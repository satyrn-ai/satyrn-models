"""Provider facts: determinism, decision persistence, and sandbox refusal.

SP5's qualification decisions: a rendered task is materialized twice through
the provider; differing observations mark it non-deterministic. Decisions
persist as JSONL keyed by intent-content hash + environment fingerprint.
Third-party-derived material is refused (fail-closed) when no real OS sandbox
profile is available — CPython ``Lib/`` material and generated provenance
carve out.

No oracle logic lives here: determinism and refusal are SP5-side decisions
over the provider's materialized observations.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

from satyrn_model.contracts import TaskRecord
from satyrn_model.contracts.provenance import HarvestedProvenance
from satyrn_model.execution.protocol import (
    Accepted,
    InfrastructureFailure,
    Observations,
    Rejection,
    SandboxBackend,
)
from satyrn_model.execution.reference import materialize_reference

__all__ = [
    "Deterministic",
    "FactRecord",
    "MaterializeOutcome",
    "NonDeterministic",
    "decide",
    "environment_fingerprint",
    "intent_content_hash",
    "materialize_twice",
    "read_facts",
    "sandbox_refusal",
    "write_facts",
]


@dataclasses.dataclass(frozen=True)
class Deterministic:
    """Both materializations agreed; observations are stable."""

    observations: Observations
    interpreter_version: str


@dataclasses.dataclass(frozen=True)
class NonDeterministic:
    """Two runs produced differing observations."""

    first: Observations
    second: Observations


MaterializeOutcome = (
    Deterministic | NonDeterministic | Rejection | InfrastructureFailure
)


def materialize_twice(
    task: TaskRecord,
    *,
    sandbox: SandboxBackend,
    timeout: int = 30,
) -> MaterializeOutcome:
    """Materialize *task* twice; pass through any non-Accepted outcome."""
    first = materialize_reference(task, sandbox=sandbox, timeout=timeout)
    if not isinstance(first, Accepted):
        return first
    second = materialize_reference(task, sandbox=sandbox, timeout=timeout)
    if not isinstance(second, Accepted):
        return second
    if first.observations != second.observations:
        return NonDeterministic(first=first.observations, second=second.observations)
    return Deterministic(
        observations=first.observations,
        interpreter_version=first.interpreter_version,
    )


def environment_fingerprint(policy_version: int = 1) -> str:
    """Provider contract/environment fingerprint for decision keying."""
    return f"cpython-{sys.version.split()[0]}|tstring-v{policy_version}"


def intent_content_hash(task: TaskRecord) -> str:
    """Short content hash of the rendered task, independent of provenance."""
    material = json.dumps(
        {
            "prompt": task.prompt,
            "reference": task.reference,
            "policy_id": task.policy.id,
            "policy_config": task.policy.config,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def sandbox_refusal(provenance: object, sandbox: SandboxBackend) -> str | None:
    """Return a refusal reason if *provenance* needs a sandbox we lack.

    Third-party-derived harvest requires a real OS confinement profile
    (anything other than the null sandbox).  Trusted CPython-derived harvest
    (source files under ``Lib/``) and generated provenance do not.
    """
    if not isinstance(provenance, HarvestedProvenance):
        return None
    if provenance.source_file.startswith("Lib/"):
        return None
    if sandbox.backend_name == "null":
        return (
            f"third-party harvest from {provenance.source_file!r} requires a "
            f"real OS sandbox profile; got backend {sandbox.backend_name!r}"
        )
    return None


@dataclasses.dataclass(frozen=True)
class FactRecord:
    """One qualification decision, keyed by intent content + environment."""

    intent_hash: str
    fingerprint: str
    deterministic: bool
    observations_repr: str
    interpreter_version: str
    refusal: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.intent_hash, self.fingerprint)

    @classmethod
    def from_outcome(
        cls,
        task: TaskRecord,
        outcome: Deterministic | NonDeterministic,
        *,
        fingerprint: str,
    ) -> FactRecord:
        if isinstance(outcome, Deterministic):
            return cls(
                intent_hash=intent_content_hash(task),
                fingerprint=fingerprint,
                deterministic=True,
                observations_repr=repr(outcome.observations),
                interpreter_version=outcome.interpreter_version,
            )
        return cls(
            intent_hash=intent_content_hash(task),
            fingerprint=fingerprint,
            deterministic=False,
            observations_repr=f"{outcome.first!r} != {outcome.second!r}",
            interpreter_version="unknown",
        )


def decide(
    task: TaskRecord,
    *,
    sandbox: SandboxBackend,
    timeout: int = 30,
    policy_version: int = 1,
) -> FactRecord:
    """Produce the qualification decision for *task*: refusal or determinism.

    Fails closed: a sandbox refusal short-circuits before materialization.
    """
    fingerprint = environment_fingerprint(policy_version)
    refusal = sandbox_refusal(task.provenance, sandbox)
    if refusal is not None:
        return FactRecord(
            intent_hash=intent_content_hash(task),
            fingerprint=fingerprint,
            deterministic=False,
            observations_repr="",
            interpreter_version="unknown",
            refusal=refusal,
        )

    outcome = materialize_twice(task, sandbox=sandbox, timeout=timeout)
    if isinstance(outcome, (Deterministic, NonDeterministic)):
        return FactRecord.from_outcome(task, outcome, fingerprint=fingerprint)

    reason = getattr(outcome, "reason", type(outcome).__name__)
    return FactRecord(
        intent_hash=intent_content_hash(task),
        fingerprint=fingerprint,
        deterministic=False,
        observations_repr="",
        interpreter_version="unknown",
        refusal=f"materialization failed: {reason}",
    )


def write_facts(records: list[FactRecord], path: Path) -> None:
    """Write fact records as JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(dataclasses.asdict(r), sort_keys=True))
            f.write("\n")


def read_facts(path: Path) -> list[FactRecord]:
    """Read fact records from JSON Lines, ignoring blank lines."""
    records: list[FactRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(FactRecord(**json.loads(line)))
    return records
