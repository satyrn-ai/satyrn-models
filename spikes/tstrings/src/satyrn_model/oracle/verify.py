"""Candidate oracle: verify candidate source against materialized observations."""

import dataclasses
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from satyrn_model.contracts import NameEquals, Raises, TaskRecord
from satyrn_model.contracts.policy import FeaturePolicy
from satyrn_model.execution.protocol import (
    ExecutionError,
    InfrastructureFailure,
    NameValue,
    Observations,
    Rejection,
    SandboxBackend,
)
from satyrn_model.execution.reference import (
    write_collector_file,
    write_reference_file,
)


@dataclasses.dataclass(frozen=True)
class VerifyAccepted:
    """Candidate passed all verification stages."""

    observations: Observations
    interpreter_version: str


VerificationOutcome = VerifyAccepted | Rejection | InfrastructureFailure


def verify_candidate(
    task: TaskRecord,
    candidate_source: str,
    *,
    ref_observations: Observations,
    policy: FeaturePolicy,
    sandbox: SandboxBackend,
    timeout: int = 30,
) -> VerificationOutcome:
    """Verify a candidate against pre-materialized reference observations.

    Stages: candidate_parse, policy, candidate_execute, semantic_check.
    """
    try:
        compile(candidate_source, "<candidate>", "exec")
    except SyntaxError as exc:
        return Rejection(stage="candidate_parse", reason=f"syntax error: {exc}")

    policy.analyze_reference(task)
    result = policy.analyze_candidate(task, candidate_source)
    if not result.passed:
        return Rejection(stage="policy", reason=result.reason or "policy rejected")

    raw = _execute(candidate_source, sandbox, timeout)
    if isinstance(raw, InfrastructureFailure):
        return raw

    return _compare(task.checks, ref_observations, raw)


def _execute(
    source: str, sandbox: SandboxBackend, timeout: int
) -> dict[str, Any] | InfrastructureFailure:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ref_path = write_reference_file(tmp_path, source)
        collector_path = write_collector_file(tmp_path)
        try:
            command = sandbox.command(
                [
                    str(Path(sys.executable).resolve()),
                    str(collector_path),
                    str(ref_path),
                ],
                readable_paths=(collector_path, ref_path),
                writable_paths=(tmp_path,),
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except RuntimeError as exc:
            return InfrastructureFailure(stage="sandbox", reason=str(exc))
        except subprocess.TimeoutExpired as exc:
            return InfrastructureFailure(stage="timeout", reason=str(exc))
        except OSError as exc:
            return InfrastructureFailure(stage="subprocess", reason=str(exc))
        if result.returncode != 0:
            return InfrastructureFailure(
                stage="subprocess",
                reason=f"collector exited {result.returncode}",
            )
        return _decode(result.stdout)


def _decode(stdout: str) -> dict[str, Any] | InfrastructureFailure:
    """Read the collector's verdict from stdout the candidate also writes to.

    The candidate runs in the collector's process, so anything it prints lands
    on the same stream, ahead of the verdict. Parsing the whole of stdout
    therefore fails on any program that ends with a demonstrative ``print()``
    — and marks it an infrastructure failure, which scores as wrong.

    That is not evenly distributed across arms. Printing a result is an
    untrained habit: on `ood-v2` it hit 7 candidates, **all of them in the
    untrained control arm and none in any of the six adapter arms**, which
    silently deflated the baseline that every adapter was compared against.

    The verdict is the last JSON object on the stream, so scan backwards.
    """
    lines = stdout.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict) and "status" in decoded:
            return decoded
    return InfrastructureFailure(
        stage="subprocess",
        reason=f"non-JSON output: {stdout[:200]}",
    )


def _interpreter_version() -> str:
    return sys.version.split()[0]


def _compare(
    checks: tuple[NameEquals | Raises, ...],
    ref: Observations,
    raw: dict[str, Any],
) -> VerifyAccepted | Rejection:
    ref_raises = any(isinstance(o, ExecutionError) for o in ref)
    c_status = raw.get("status")
    if ref_raises:
        return _compare_raises(ref, c_status, raw)
    return _compare_names(checks, ref, c_status, raw)


def _compare_names(
    checks: tuple[NameEquals | Raises, ...],
    ref: Observations,
    c_status: object,
    raw: dict[str, Any],
) -> VerifyAccepted | Rejection:
    if c_status != "ok":
        exc = raw.get("exception", {})
        return Rejection(
            stage="candidate_execute",
            reason=f"candidate raised {exc.get('type', '?')}",
        )
    c_ns = raw.get("namespace", {})
    ref_map: dict[str, str] = {}
    for o in ref:
        if isinstance(o, NameValue):
            ref_map[o.name] = o.repr

    for check in checks:
        if isinstance(check, Raises):
            return Rejection(
                stage="semantic_check",
                reason=f"expected raise {check.exception!r}, candidate succeeded",
            )
        if check.name not in c_ns:
            return Rejection(
                stage="semantic_check",
                reason=f"candidate namespace missing {check.name!r}",
            )
        if check.name in ref_map and c_ns[check.name] != ref_map[check.name]:
            return Rejection(
                stage="semantic_check",
                reason=f"{check.name!r} mismatch",
                evidence={
                    "candidate": c_ns[check.name],
                    "reference": ref_map[check.name],
                },
            )

    return VerifyAccepted(
        observations=tuple(
            NameValue(name=name, repr=val) for name, val in c_ns.items()
        ),
        interpreter_version=_interpreter_version(),
    )


def _compare_raises(
    ref: Observations,
    c_status: object,
    raw: dict[str, Any],
) -> VerifyAccepted | Rejection:
    if c_status == "ok":
        return Rejection(
            stage="semantic_check",
            reason="expected exception, candidate succeeded",
        )
    exc = raw.get("exception", {})
    c_type = exc.get("type", "")
    ref_type: str | None = None
    for o in ref:
        if isinstance(o, ExecutionError):
            ref_type = o.exception_type
            break
    if ref_type is None:
        return Rejection(stage="semantic_check", reason="no expected exception in ref")
    if c_type != ref_type:
        return Rejection(
            stage="semantic_check",
            reason=f"expected {ref_type!r}, candidate raised {c_type!r}",
        )
    return VerifyAccepted(
        observations=(
            ExecutionError(exception_type=c_type, message=exc.get("message")),
        ),
        interpreter_version=_interpreter_version(),
    )


__all__ = ["VerifyAccepted", "VerificationOutcome", "verify_candidate"]
