"""Execution protocol types for the versioned subprocess reference executor.

Defines the closed ``ReferenceOutcome`` union, the materialized observation
types, and the sandbox-backend protocol. These are the only public types the
reference executor exposes; materialized observations are internal evidence,
never serialized directly from a producer-supplied payload.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Materialized observation types (internal evidence)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class NameValue:
    """The namespace binding was present and produced a valid repr."""

    name: str
    repr: str  # repr() of the value in the reference namespace


@dataclasses.dataclass(frozen=True)
class NameMissing:
    """The expected namespace binding was absent."""

    name: str


@dataclasses.dataclass(frozen=True)
class ExecutionError:
    """Execution raised an exception; the reference failed to complete."""

    exception_type: str
    message: str | None = None


Observations = tuple[NameValue | NameMissing | ExecutionError, ...]


# ---------------------------------------------------------------------------
# Closed outcome union
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Accepted:
    """All checks evaluated successfully against the reference execution."""

    observations: Observations
    interpreter_version: str
    sandbox_backend: str
    sandbox_profile_version: str


@dataclasses.dataclass(frozen=True)
class Rejection:
    """The reference code is invalid (producer error) or a check failed.

    Distinct from ``InfrastructureFailure``: a rejection means the reference
    itself did not satisfy the checks, not that the environment is broken.
    """

    stage: str  # parse | import | execute | collect
    reason: str
    evidence: dict[str, Any] | None = None


@dataclasses.dataclass(frozen=True)
class InfrastructureFailure:
    """The execution environment could not be established or failed.

    Never collapsed into a semantic rejection. Stages include ``sandbox``
    (profile unavailable), ``timeout``, and ``subprocess`` (cannot start).
    """

    stage: str  # sandbox | timeout | subprocess
    reason: str
    evidence: dict[str, Any] | None = None


ReferenceOutcome = Accepted | Rejection | InfrastructureFailure


# ---------------------------------------------------------------------------
# Sandbox backend
# ---------------------------------------------------------------------------


class SandboxBackend(Protocol):
    """Pluggable execution confinement.

    ``command()`` wraps a subprocess command with OS confinement. If the
    sandbox profile cannot be established, ``command()`` must raise
    ``RuntimeError``; the caller converts this to an
    ``InfrastructureFailure("sandbox", ...)`` and never falls back to
    unsandboxed execution.
    """

    @property
    def backend_name(self) -> str: ...

    @property
    def profile_version(self) -> str: ...

    def command(
        self,
        argv: list[str],
        *,
        readable_paths: tuple[Path, ...] = (),
        writable_paths: tuple[Path, ...] = (),
    ) -> list[str]:
        """Return *argv* wrapped in the configured confinement command."""
        ...


class NullSandbox:
    """Test-only sandbox that applies no confinement.

    Used for core protocol testing where OS-level sandboxing is not under
    test. Not a production path; production uses ``OSProfileSandbox`` which
    fails-closed when no profile is configured.
    """

    backend_name = "null"
    profile_version = "0"

    def command(
        self,
        argv: list[str],
        *,
        readable_paths: tuple[Path, ...] = (),
        writable_paths: tuple[Path, ...] = (),
    ) -> list[str]:
        return argv


@dataclasses.dataclass(frozen=True, kw_only=True)
class OSProfileSandbox:
    """Production sandbox backed by macOS Seatbelt confinement."""

    backend_name: str = "macos-seatbelt"
    profile_version: str = "1"
    profile_path: Path | None = None

    def command(
        self,
        argv: list[str],
        *,
        readable_paths: tuple[Path, ...] = (),
        writable_paths: tuple[Path, ...] = (),
    ) -> list[str]:
        executable = shutil.which("sandbox-exec")
        if sys.platform != "darwin" or executable is None:
            raise RuntimeError("macOS sandbox-exec is unavailable")

        configured = self.profile_path
        if configured is None and (value := os.environ.get("SATYRN_SANDBOX_PROFILE")):
            configured = Path(value)
        if configured is not None:
            if not configured.is_file():
                raise RuntimeError(f"sandbox profile does not exist: {configured}")
            return [executable, "-f", str(configured), *argv]

        profile = _seatbelt_profile(readable_paths, writable_paths)
        return [executable, "-p", profile, *argv]


def _seatbelt_profile(
    readable_paths: tuple[Path, ...], writable_paths: tuple[Path, ...]
) -> str:
    """Build the provider's fail-closed profile for one temporary execution."""
    readable = {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        *(path.resolve() for path in readable_paths),
        *(path.resolve() for path in writable_paths),
    }
    writable = {path.resolve() for path in writable_paths}
    def quote(path: Path) -> str:
        return json.dumps(str(path))
    home = Path.home().resolve()
    home_exceptions = " ".join(
        f"(require-not (subpath {quote(path)}))" for path in sorted(readable)
    )
    write_exceptions = " ".join(
        f"(require-not (subpath {quote(path)}))" for path in sorted(writable)
    )
    write_rule = (
        f"(deny file-write* (require-all {write_exceptions}))"
        if write_exceptions
        else "(deny file-write*)"
    )
    return " ".join(
        (
            "(version 1)",
            "(allow default)",
            "(deny network*)",
            f"(deny file-read* (require-all (subpath {quote(home)}) "
            f"{home_exceptions}))",
            '(deny file-read* (subpath "/private/etc"))',
            write_rule,
        )
    )


__all__ = [
    "NameValue",
    "NameMissing",
    "ExecutionError",
    "Observations",
    "Accepted",
    "Rejection",
    "InfrastructureFailure",
    "ReferenceOutcome",
    "SandboxBackend",
    "NullSandbox",
    "OSProfileSandbox",
]
