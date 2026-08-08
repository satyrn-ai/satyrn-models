"""Seed review decisions: human verdicts keyed by content hash.

Decisions live in ``review/decisions.jsonl``. Content-derived keys mean
re-review is scoped to actual diffs when seeds change.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from pathlib import Path

from .models import Seed, seed_id

__all__ = [
    "ReviewDecision",
    "read_decisions",
    "seed_content_sha256",
    "write_decisions",
]


@dataclasses.dataclass(frozen=True)
class ReviewDecision:
    """A human decision about a seed: accepted, rejected, or needs-review."""

    seed_id: str
    verdict: str  # "accepted" | "rejected" | "needs-review"
    reason: str
    content_sha256: str
    decided_at: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


def seed_content_sha256(seed: Seed) -> str:
    """Hash review-relevant seed content, excluding provenance occurrences."""
    return seed_id(seed.literal, seed.bindings)


def write_decisions(decisions: list[ReviewDecision], path: Path) -> None:
    """Write review decisions as JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(dataclasses.asdict(d), sort_keys=True))
            f.write("\n")


def read_decisions(path: Path) -> list[ReviewDecision]:
    """Read review decisions from JSON Lines, ignoring blank lines."""
    decisions: list[ReviewDecision] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            decisions.append(ReviewDecision(**data))
    return decisions
