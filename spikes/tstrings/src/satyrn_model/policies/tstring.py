"""TStringPolicy: the real t-string domain policy for the provider.

Implements the ``FeaturePolicy`` Protocol from the provider contracts. This is
the policy that SP5 ships; it does NOT import authoring internals. It reads
declarative config from ``PolicyRef.config`` and uses AST-level checks to
detect old-form fallbacks (f-strings, .format(), %) where a t-string was
required.

``analyze_reference`` reads the reference AST once per task; ``analyze_candidate``
checks the candidate against the reference's feature requirements; and
``degenerate_candidates`` returns old-form candidates that must fail the
semantic check to prove anti-vacuity.

This is the real policy, not a stub. The provider's Task 4 adversarial registry
installs and runs this exact module in CI (cross-boundary gate).
"""

from __future__ import annotations

import ast

from satyrn_model.contracts import TaskRecord
from satyrn_model.contracts.policy import PolicyResult


class TStringPolicy:
    policy_id: str = "tstring"
    version: int = 1

    def __init__(self, strict_old_form: bool = True) -> None:
        """``strict_old_form`` rejects any old-form formatting in a candidate.

        That is the shipped default, and it is probably wrong: scoring the 100
        `ood-v2` gold references against it **rejects 4 of them** — two for an
        f-string and two for `%`-formatting, in programs that also build a
        genuine `Template`. A gate that rejects the correct answer is not
        measuring correctness, and SP5 should consider changing the default.

        It is left as the default here because this policy is a cross-boundary
        contract installed by the provider's adversarial registry in CI, so
        flipping it silently would change behaviour for callers who did not ask.
        Evaluation in this spike passes ``strict_old_form=False``, which
        enforces only the requirement the check exists for: a candidate must
        build a `Template` where the reference builds one. See
        `spikes/tstrings/PREREGISTRATION.md`.
        """
        self.strict_old_form = strict_old_form
        # Per-task state populated by analyze_reference
        self._ref_uses_tstring: bool = False
        self._ref_tstring_count: int = 0

    # ------------------------------------------------------------------
    # FeaturePolicy Protocol
    # ------------------------------------------------------------------

    def analyze_reference(self, task: TaskRecord) -> None:
        """Read the reference AST to determine feature requirements."""
        self._ref_uses_tstring = False
        self._ref_tstring_count = 0
        try:
            tree = ast.parse(task.reference)
            for node in ast.walk(tree):
                if isinstance(node, ast.TemplateStr):
                    self._ref_uses_tstring = True
                    self._ref_tstring_count += 1
        except SyntaxError:
            self._ref_uses_tstring = False

    def analyze_candidate(self, task: TaskRecord, candidate: str) -> PolicyResult:
        """Check candidate for old-form fallbacks and missing t-strings."""
        if not self._ref_uses_tstring:
            # Reference doesn't use t-strings (e.g., convert()-only task).
            # No feature requirement to enforce.
            return PolicyResult(passed=True)

        has_tstring = self._count_tstrings(candidate) > 0
        has_fstring = _has_fstring(candidate)
        has_format = ".format(" in candidate
        has_percent = _has_percent_format(candidate)

        if self.strict_old_form:
            if has_fstring:
                return PolicyResult(
                    passed=False,
                    reason="old-form f-string detected where t-string required",
                )
            if has_format:
                return PolicyResult(
                    passed=False,
                    reason="old-form .format() detected where t-string required",
                )
            if has_percent:
                return PolicyResult(
                    passed=False,
                    reason="old-form %-formatting detected where t-string required",
                )
        if not has_tstring:
            return PolicyResult(
                passed=False,
                reason="no t-string literal found where reference uses one",
            )

        return PolicyResult(passed=True)

    def degenerate_candidates(self, task: TaskRecord) -> list[str]:
        """Return semantically-wrong candidates that pass policy."""
        degenerates: list[str] = []

        if self._ref_uses_tstring:
            # Same reference but with a different result — semantically
            # wrong but still uses t-string (passes policy).
            degenerates.append(task.reference.rstrip() + "\nresult = 'wrong-output'\n")

        return degenerates

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _count_tstrings(self, source: str) -> int:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return 0
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.TemplateStr):
                count += 1
        return count


def _source_slice(source: str, node: ast.AST) -> str | None:
    """Return the source text slice for a node, or None."""
    try:
        return ast.get_source_segment(source, node)
    except Exception:
        return None


def _has_fstring(source: str) -> bool:
    """True if source contains an f-string (f'...' or f\"...\")."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            seg = _source_slice(source, node)
            if seg and seg.startswith(("f'", 'f"')):
                return True
    return False


def _has_percent_format(source: str) -> bool:
    """Crude check for %-formatting in non-quoted positions."""
    import re

    # Look for patterns like "..." % ... outside of string literals
    # This is deliberately simple — the real policy can be more sophisticated
    return bool(re.search(r'"%[sd]', source) or re.search(r"'%[sd]", source))


__all__ = ["TStringPolicy"]
