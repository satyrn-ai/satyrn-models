"""Versioned, sandboxed reference execution and observation materialization.

Runs the reference program in an isolated subprocess, collects the resulting
namespace (or exception), and evaluates every ``CheckSpec`` against it. Returns
a closed ``ReferenceOutcome`` that clearly separates accepted observations from
infrastructure failures and reference-level rejections.

Materialized observations are internal evidence — never a public row
constructor and never accepted as trusted input from a dataset producer.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from satyrn_model.contracts import NameEquals, Raises, TaskRecord

from .protocol import (
    Accepted,
    ExecutionError,
    InfrastructureFailure,
    NameMissing,
    NameValue,
    ReferenceOutcome,
    Rejection,
    SandboxBackend,
)

# ---------------------------------------------------------------------------
# Collector — a self-contained Python script that exec's reference code in a
# subprocess and returns the resulting namespace or exception as JSON.
# Written to a temp file to avoid shell-quoting the reference code.
# ---------------------------------------------------------------------------

_COLLECTOR_SCRIPT = """\
import json, sys, traceback

def _collect(ref_path: str) -> dict:
    with open(ref_path, encoding="utf-8") as fh:
        code = fh.read()
    namespace: dict = {}
    try:
        exec(compile(code, ref_path, "exec"), namespace)
        public = {
            k: repr(v)
            for k, v in namespace.items()
            if not k.startswith("_")
        }
        return {"status": "ok", "namespace": public}
    except Exception as exc:
        return {
            "status": "error",
            "exception": {"type": type(exc).__name__, "message": str(exc)},
        }

if __name__ == "__main__":
    sys.stdout.write(json.dumps(_collect(sys.argv[1])))
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def materialize_reference(
    task: TaskRecord,
    *,
    sandbox: SandboxBackend,
    timeout: int = 30,
) -> ReferenceOutcome:
    """Execute the reference program and evaluate its ``CheckSpec`` entries.

    Returns an ``Accepted`` with materialized observations only when every
    check evaluates cleanly. Partial results (swallowed import, missing name,
    repr error, execution crash) are returned as ``Rejection``, never
    silently truncated. Subprocess and sandbox failures return
    ``InfrastructureFailure``.
    """

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ref_path = write_reference_file(tmp_path, task.reference)
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
                reason=f"collector exited {result.returncode}: {result.stderr.strip()}",
            )

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return InfrastructureFailure(
                stage="subprocess",
                reason=f"collector produced non-JSON output: {result.stdout[:200]}",
            )

        return _evaluate(task, raw, sandbox)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def write_reference_file(tmp_dir: Path, reference: str) -> Path:
    """Write the reference code to a temp .py file, return its path."""
    path = tmp_dir / "_reference.py"
    path.write_text(reference, encoding="utf-8")
    return path


def write_collector_file(tmp_dir: Path) -> Path:
    """Write the collector script to a temp .py file, return its path."""
    path = tmp_dir / "_collector.py"
    path.write_text(_COLLECTOR_SCRIPT, encoding="utf-8")
    return path


def _evaluate(
    task: TaskRecord,
    raw: dict[str, Any],
    sandbox: SandboxBackend,
) -> ReferenceOutcome:
    """Evaluate every check against the subprocess output."""

    status = raw.get("status")
    if status == "ok":
        return _evaluate_success(task, raw, sandbox)
    if status == "error":
        return _evaluate_error(task, raw, sandbox)
    return InfrastructureFailure(
        stage="subprocess", reason=f"collector returned unknown status {status!r}"
    )


def _interpreter_version() -> str:
    return sys.version.split()[0]


def _evaluate_success(
    task: TaskRecord,
    raw: dict[str, Any],
    sandbox: SandboxBackend,
) -> ReferenceOutcome:
    namespace = raw.get("namespace", {})
    observations: list[Any] = []

    for check in task.checks:
        if isinstance(check, Raises):
            # Execution succeeded but a Raises check expected an exception.
            return Rejection(
                stage="collect",
                reason=(
                    f"expected exception {check.exception!r} but execution succeeded"
                ),
                evidence={"check": check.to_dict()},
            )
        if isinstance(check, NameEquals):
            name = check.name
            if name not in namespace:
                observations.append(NameMissing(name=name))
            else:
                observations.append(NameValue(name=name, repr=namespace[name]))

    # Any missing or error observations → Rejection
    for obs in observations:
        if isinstance(obs, NameMissing):
            return Rejection(
                stage="collect",
                reason=f"name {obs.name!r} not found in reference namespace",
                evidence={"name": obs.name, "available": sorted(namespace)},
            )

    return Accepted(
        observations=tuple(observations),
        interpreter_version=_interpreter_version(),
        sandbox_backend=sandbox.backend_name,
        sandbox_profile_version=sandbox.profile_version,
    )


def _evaluate_error(
    task: TaskRecord,
    raw: dict[str, Any],
    sandbox: SandboxBackend,
) -> ReferenceOutcome:
    exc = raw.get("exception", {})
    exc_type = exc.get("type", "Unknown")
    exc_msg = exc.get("message", "")

    for check in task.checks:
        if isinstance(check, NameEquals):
            # Execution raised, but a NameEquals check expected a namespace.
            return Rejection(
                stage="execute",
                reason=f"reference raised {exc_type}: {exc_msg}",
                evidence={"exception": exc, "failing_check": check.to_dict()},
            )

    # All checks must be Raises at this point (execution raised).
    for check in task.checks:
        if isinstance(check, Raises):
            if check.exception == exc_type:
                return Accepted(
                    observations=(
                        ExecutionError(exception_type=exc_type, message=exc_msg),
                    ),
                    interpreter_version=_interpreter_version(),
                    sandbox_backend=sandbox.backend_name,
                    sandbox_profile_version=sandbox.profile_version,
                )
            else:
                return Rejection(
                    stage="collect",
                    reason=f"expected exception {check.exception!r}, got {exc_type!r}",
                    evidence={"expected": check.exception, "got": exc_type},
                )

    # No checks? (Shouldn't happen — ingest enforces non-empty.)
    return Rejection(stage="collect", reason="no checks to evaluate")
