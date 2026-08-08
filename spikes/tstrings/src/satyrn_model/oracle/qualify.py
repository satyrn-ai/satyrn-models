"""Task qualification: self-verification and anti-vacuity against a domain policy.

Qualifies a task for a dataset by verifying the reference against its own
checks and requiring every policy-supplied degenerate candidate to reach (and
fail at) the semantic-check stage. A degenerate that passes, crashes, times
out, or is rejected at any non-semantic stage makes the task ineligible.
"""

from __future__ import annotations

from satyrn_model.contracts import TaskRecord
from satyrn_model.contracts.policy import FeaturePolicy
from satyrn_model.execution.protocol import (
    InfrastructureFailure,
    Observations,
    Rejection,
    SandboxBackend,
)
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.verify import (
    VerifyAccepted,
    verify_candidate,
)


class Qualified:
    """Task passed self-verification and all degenerates failed at semantic check."""

    def __init__(
        self,
        ref_observations: Observations,
        interpreter_version: str,
    ) -> None:
        self.ref_observations = ref_observations
        self.interpreter_version = interpreter_version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Qualified):
            return NotImplemented
        return (
            self.ref_observations == other.ref_observations
            and self.interpreter_version == other.interpreter_version
        )


class VacuityUntested:
    """A degenerate didn't reach semantic check; task anti-vacuity is unproven."""

    def __init__(self, reason: str, evidence: dict | None = None) -> None:
        self.reason = reason
        self.evidence = evidence

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VacuityUntested):
            return NotImplemented
        return self.reason == other.reason and self.evidence == other.evidence


QualificationOutcome = Qualified | Rejection | InfrastructureFailure | VacuityUntested


def qualify_task(
    task: TaskRecord,
    *,
    policy: FeaturePolicy,
    sandbox: SandboxBackend,
    timeout: int = 30,
) -> QualificationOutcome:
    """Qualify a task: self-verify, then test every degenerate candidate.

    1. Materialize reference observations.
    2. Run reference as its own candidate (must pass).
    3. For each degenerate from policy: must reach AND fail at semantic_check.
       If a degenerate passes, crashes, times out, or is rejected at
       candidate_parse/policy/candidate_execute, the task is ``vacuity_untested``.
    """

    # -- 1. Materialize reference ---------------------------------------
    ref_outcome = materialize_reference(task, sandbox=sandbox, timeout=timeout)
    from satyrn_model.execution.protocol import Accepted as RefAccepted

    if not isinstance(ref_outcome, RefAccepted):
        if isinstance(ref_outcome, object) and hasattr(ref_outcome, "stage"):
            return Rejection(
                stage=ref_outcome.stage,
                reason=getattr(
                    ref_outcome, "reason", "reference materialization failed"
                ),
            )
        return InfrastructureFailure(
            stage="subprocess",
            reason="reference materialization failed",
        )

    ref_obs: Observations = ref_outcome.observations

    # -- 2. Self-verification -------------------------------------------
    self_check = verify_candidate(
        task,
        task.reference,
        ref_observations=ref_obs,
        policy=policy,
        sandbox=sandbox,
        timeout=timeout,
    )
    if not isinstance(self_check, VerifyAccepted):
        if isinstance(self_check, Rejection):
            return Rejection(
                stage="self_verify",
                reason=f"reference did not pass as own candidate: {self_check.reason}",
            )
        return InfrastructureFailure(
            stage="self_verify", reason="self-verification infrastructure failure"
        )

    # -- 3. Anti-vacuity ------------------------------------------------
    degenerates = policy.degenerate_candidates(task)
    for i, degenerate in enumerate(degenerates):
        result = verify_candidate(
            task,
            degenerate,
            ref_observations=ref_obs,
            policy=policy,
            sandbox=sandbox,
            timeout=timeout,
        )
        if isinstance(result, VerifyAccepted):
            return VacuityUntested(
                reason=f"degenerate {i} passed semantic check (check is vacuous)",
            )
        if isinstance(result, InfrastructureFailure):
            return VacuityUntested(
                reason=(
                    f"degenerate {i} infrastructure failure "
                    f"at {result.stage}: {result.reason}"
                ),
            )
        # Must be Rejection at semantic_check
        if result.stage != "semantic_check":
            return VacuityUntested(
                reason=(
                    f"degenerate {i} rejected at {result.stage} "
                    f"instead of semantic_check: {result.reason}"
                ),
            )

    return Qualified(
        ref_observations=ref_obs,
        interpreter_version=ref_outcome.interpreter_version,
    )


__all__ = [
    "Qualified",
    "VacuityUntested",
    "QualificationOutcome",
    "qualify_task",
]
