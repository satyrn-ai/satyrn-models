"""Versioned, sandboxed subprocess execution for reference and candidate code."""

from .protocol import (
    Accepted,
    ExecutionError,
    InfrastructureFailure,
    NameMissing,
    NameValue,
    NullSandbox,
    Observations,
    OSProfileSandbox,
    ReferenceOutcome,
    Rejection,
    SandboxBackend,
)
from .reference import materialize_reference

__all__ = [
    "Accepted",
    "ExecutionError",
    "InfrastructureFailure",
    "NameMissing",
    "NameValue",
    "NullSandbox",
    "OSProfileSandbox",
    "Observations",
    "ReferenceOutcome",
    "Rejection",
    "SandboxBackend",
    "materialize_reference",
]
