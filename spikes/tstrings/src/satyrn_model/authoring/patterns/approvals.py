"""Pattern approvals: the audit ledger for reviewed patterns.

``patterns/approvals.jsonl`` records one entry per audited pattern, keyed by
``pattern_input_fingerprint``. Generation refuses a pattern whose current
fingerprint is stale or missing; editing any declared input (helpers,
templates, renderer deps, versions) invalidates approval wholesale.
"""

import dataclasses
import datetime
import json
from pathlib import Path

from .registry import Pattern, pattern_input_fingerprint, validate_pattern

__all__ = [
    "ApprovalError",
    "PatternApproval",
    "audit_pattern",
    "approved_fingerprint",
    "read_approvals",
    "require_approval",
    "write_approvals",
]


class ApprovalError(RuntimeError):
    """A pattern lacks an approval, or its approval is stale."""


@dataclasses.dataclass(frozen=True)
class PatternApproval:
    """An audited pattern pinned to its input fingerprint."""

    pattern_id: str
    pattern_input_fingerprint: str
    approved_at: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


def write_approvals(approvals: list[PatternApproval], path: Path) -> None:
    """Write approvals as deterministic JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for a in approvals:
            f.write(json.dumps(dataclasses.asdict(a), sort_keys=True))
            f.write("\n")


def read_approvals(path: Path) -> list[PatternApproval]:
    """Read approvals from JSON Lines, ignoring blank lines."""
    approvals: list[PatternApproval] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            approvals.append(PatternApproval(**json.loads(line)))
    return approvals


def approved_fingerprint(
    pattern_id: str, approvals: list[PatternApproval]
) -> str | None:
    """The most recently approved fingerprint for *pattern_id*, if any."""
    matches = [a for a in approvals if a.pattern_id == pattern_id]
    if not matches:
        return None
    return max(matches, key=lambda a: a.approved_at).pattern_input_fingerprint


def require_approval(
    pattern: Pattern,
    approvals: list[PatternApproval],
    fingerprint: str,
) -> None:
    """Raise ``ApprovalError`` when *pattern* has no matching approval."""
    approved = approved_fingerprint(pattern.id, approvals)
    if approved is None:
        raise ApprovalError(
            f"pattern {pattern.id!r} has no approval; run "
            f"`authoring audit-pattern {pattern.id}` first"
        )
    if approved != fingerprint:
        raise ApprovalError(
            f"pattern {pattern.id!r} approval is stale: inputs changed "
            f"(approved {approved[:12]}, current {fingerprint[:12]})"
        )


def audit_pattern(
    pattern: Pattern,
    path: Path,
    *,
    blast_radius: int = 0,
    **versions: object,
) -> PatternApproval:
    """Record an approval for *pattern* at its current input fingerprint.

    ``blast_radius`` is the number of generated rows the pattern currently
    affects (seeds consumed); ``versions`` may override generator/policy/
    config/render-contract versions for the fingerprint.
    """
    validate_pattern(pattern)
    fingerprint = pattern_input_fingerprint(pattern, **versions)
    approval = PatternApproval(
        pattern_id=pattern.id,
        pattern_input_fingerprint=fingerprint,
    )
    approvals = (
        [item for item in read_approvals(path) if item.pattern_id != pattern.id]
        if path.exists()
        else []
    )
    approvals.append(approval)
    write_approvals(approvals, path)
    if blast_radius:
        print(
            f"audited {pattern.id} fingerprint={fingerprint[:12]} "
            f"blast_radius={blast_radius}"
        )
    return approval
