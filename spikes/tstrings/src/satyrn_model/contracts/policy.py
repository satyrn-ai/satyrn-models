"""Policy reference and the trusted domain-policy protocol.

A dataset carries only a ``PolicyRef`` — an identifier, a version, and a
declarative (JSON-serializable) config. It carries no executable code and no
inlined expected value. The reference resolves to a real ``FeaturePolicy``
implementation only through an explicitly registered, trusted registry owned
by the provider (Task 3). Ingest (Task 1) checks registration and version
against a ``PolicyRegistry`` it is handed; it never imports a producer's
package.

``FeaturePolicy`` is the domain protocol the t-string-data project implements
(``TStringPolicy``). Its analysis and degenerate-generation methods are
exercised from Task 2 onward; the protocol is published here so the contract
and the seam exist before either side is built, and so the cross-boundary
adversarial gate (Task 4) can run the *real* policy in CI rather than a stub.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .task import TaskRecord  # noqa: F811

from ._common import ContractError, reject_unknown_keys, require_object

_ALLOWED_POLICY_CONFIG_VALUE: tuple[type, ...] = (str, int, float, bool, type(None))


@dataclasses.dataclass(frozen=True, kw_only=True)
class PolicyRef:
    """A declarative, code-free reference to a registered domain policy.

    ``config`` is a frozen mapping of JSON primitives; it may not contain
    nested containers of code or arbitrary callables. A dataset file cannot
    ship policy behaviour, only a name and parameters for behaviour the
    provider has already registered.
    """

    id: str
    version: int
    config: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ContractError("policy id must be a non-empty string")
        if (
            not isinstance(self.version, int)
            or isinstance(self.version, bool)
            or self.version < 1
        ):
            raise ContractError("policy version must be a positive integer")
        frozen = dict(self.config)
        _validate_policy_config(frozen)
        # Read-only view; the underlying dict is private to this instance.
        object.__setattr__(self, "config", dict(frozen))

    @classmethod
    def from_dict(cls, data: object) -> PolicyRef:
        data = require_object(data, "policy")
        if "id" not in data or "version" not in data:
            raise ContractError("policy ref missing 'id' or 'version'")
        reject_unknown_keys(data, frozenset({"id", "version", "config"}), "policy ref")
        config = data.get("config", {})
        if not isinstance(config, Mapping):
            raise ContractError("policy 'config' must be an object")
        return cls(id=data["id"], version=data["version"], config=dict(config))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "config": dict(self.config)}


def _validate_policy_config(config: Mapping[str, Any]) -> None:
    for key, value in config.items():
        if not isinstance(key, str) or not key:
            raise ContractError("policy config keys must be non-empty strings")
        _validate_policy_config_value(value, f"config[{key!r}]")


def _validate_policy_config_value(value: Any, path: str) -> None:
    if isinstance(value, _ALLOWED_POLICY_CONFIG_VALUE):
        return
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if not isinstance(key, str) or not key:
                raise ContractError(f"policy {path} keys must be non-empty strings")
            _validate_policy_config_value(sub, f"{path}[{key!r}]")
        return
    if isinstance(value, list):
        for index, sub in enumerate(value):
            _validate_policy_config_value(sub, f"{path}[{index}]")
        return
    raise ContractError(
        f"policy {path} must be a JSON primitive/object/list, "
        f"got {type(value).__name__}"
    )


@dataclasses.dataclass(frozen=True)
class PolicyResult:
    """Result of a domain policy's candidate analysis.

    Use ``PolicyResult(passed=True)`` for pass and
    ``PolicyResult(passed=False, reason="...")`` for failure.
    """

    passed: bool
    reason: str | None = None


class FeaturePolicy(Protocol):
    """Trusted domain policy: versioned reference/candidate analysis."""

    @property
    def policy_id(self) -> str: ...

    @property
    def version(self) -> int: ...

    def analyze_reference(self, task: TaskRecord) -> None:
        """Pre-compute per-task state for candidate analysis."""
        ...

    def analyze_candidate(self, task: TaskRecord, candidate: str) -> PolicyResult:
        """Check whether ``candidate`` meets feature requirements."""
        ...

    def degenerate_candidates(self, task: TaskRecord) -> list[str]:
        """Return degenerate candidates for anti-vacuity qualification."""
        ...


class PolicyRegistry(Protocol):
    """The injectable lookup ingest uses to check policy registration.

    The real trusted registry is Task 3's ``src/satyrn_model/policies/``.
    Task 1 ingest only needs to know whether a (id, version) is registered and
    which versions exist for an id, so it can distinguish an unregistered policy
    from a version mismatch. ``resolve`` is part of the protocol so the seam is
    complete, but ingest does not call it.
    """

    def registered_policy_ids(self) -> frozenset[str]: ...

    def known_versions(self, policy_id: str) -> frozenset[int]: ...

    def resolve(self, ref: PolicyRef) -> FeaturePolicy: ...


__all__ = [
    "PolicyRef",
    "FeaturePolicy",
    "PolicyRegistry",
    "PolicyResult",
]
