"""Shared helpers for strict, rejection-style contract deserialization.

Every contract type deserializes from a plain ``dict`` and rejects unknown
keys. The "unexpected key" rule is load-bearing: it is how ingest rejects a
caller-supplied expected value on a check (defect #2's ghost) or any fictional
field on a provenance kind. Without it, a producer could smuggle a trusted
value past a closed union by adding a key the parser ignores.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ContractError(ValueError):
    """Raised when a dataset snapshot violates the versioned contract.

    Distinct from infrastructure/runtime failures: a ``ContractError`` means
    the producer shipped something the contract does not permit, and ingest
    refuses it before any execution. It is always a caller/producer fault,
    never an environment fault.
    """


def require_object(data: object, what: str) -> dict[str, Any]:
    """Return ``data`` as a dict or raise ``ContractError`` for non-objects."""
    if not isinstance(data, Mapping):
        raise ContractError(f"{what} must be an object, got {type(data).__name__}")
    return {str(key): value for key, value in data.items()}


def require_fields(data: Mapping[str, Any], fields: tuple[str, ...], what: str) -> None:
    """Raise if any required field is missing."""
    missing = [field for field in fields if field not in data]
    if missing:
        raise ContractError(f"{what} missing field(s): {', '.join(missing)}")


def reject_unknown_keys(
    data: Mapping[str, Any], allowed: frozenset[str], what: str
) -> None:
    """Raise if ``data`` contains keys outside ``allowed``.

    The message names the unexpected key so a smuggled ``expected`` value is
    visible in the failure rather than dropped silently.
    """
    extra = set(data) - allowed
    if extra:
        keys = ", ".join(sorted(extra))
        raise ContractError(f"{what} has unexpected field(s): {keys}")


def require_str(data: object, what: str) -> str:
    if not isinstance(data, str) or not data:
        raise ContractError(f"{what} must be a non-empty string")
    return data


__all__ = [
    "ContractError",
    "require_object",
    "require_fields",
    "reject_unknown_keys",
    "require_str",
]
