"""Trusted policy registry that resolves ``PolicyRef`` to ``FeaturePolicy``.

Dataset files ship only a ``PolicyRef``, never executable policy code. The
registry maps (id, version) to a concrete ``FeaturePolicy`` implementation
registered by the provider. A ``PolicyRef`` whose id is absent, or whose
version is not registered, is rejected at ingest (Task 1) or at qualification
time (Task 3).
"""

from __future__ import annotations

from satyrn_model.contracts import ContractError, FeaturePolicy, PolicyRef


class TrustedPolicyRegistry:
    """Maps (policy_id, version) to a concrete ``FeaturePolicy``.

    Dataset files reference policies declaratively; the provider registers
    the implementation. This is a concrete registry, not the ``PolicyRegistry``
    Protocol — it implements that Protocol and adds registration.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, int], FeaturePolicy] = {}

    def register(self, implementation: FeaturePolicy) -> None:
        """Register a policy implementation at its declared version."""
        key = (implementation.policy_id, implementation.version)
        self._entries[key] = implementation

    def registered_policy_ids(self) -> frozenset[str]:
        return frozenset(pid for pid, _ in self._entries)

    def known_versions(self, policy_id: str) -> frozenset[int]:
        return frozenset(ver for pid, ver in self._entries if pid == policy_id)

    def resolve(self, ref: PolicyRef) -> FeaturePolicy:
        """Return the registered implementation for a policy reference.

        Raises ``ContractError`` if the (id, version) is not registered.
        """
        key: tuple[str, int] = (ref.id, ref.version)
        impl = self._entries.get(key)
        if impl is None:
            raise ContractError(
                f"policy {ref.id!r} version {ref.version} is not registered"
            )
        return impl

    def __bool__(self) -> bool:
        return bool(self._entries)


__all__ = ["TrustedPolicyRegistry"]
