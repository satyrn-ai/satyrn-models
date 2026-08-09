"""Structural fingerprints, metrics, and intra-corpus dedup.

Three operations that must not be conflated (design §5.1):

1. **Exact-content duplicates** are a hard, linear build rejection —
   ``deduplicate_tasks``.
2. **Semantic/near duplicates** are reported only (never a gate here).
3. **Structural fingerprints** erase identifiers/constants and are a diversity
   metric, never duplicate proof.

All of it is deterministic and report-only except dedup.
"""

import hashlib
import re

from satyrn_model.contracts import DatasetSnapshot, TaskRecord, semantic_content_id

__all__ = [
    "diversity_report",
    "deduplicate_tasks",
    "prompt_fingerprint",
    "reference_skeleton",
]


def reference_skeleton(reference: str) -> str:
    """Shape retained, identifiers and constants erased (regex-based AST
    skeleton — same approach as coverage.skeleton_of, applied to code)."""
    s = re.sub(r"'[^']*'|\"[^\"]*\"", '"..."', reference)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", "N", s)
    s = re.sub(r"\b[a-z_][a-z0-9_]*\b", "x", s)
    return s


def prompt_fingerprint(prompt: str) -> str:
    """Normalized prompt text (whitespace-folded) as a distinctness key."""
    return re.sub(r"\s+", " ", prompt).strip()


def deduplicate_tasks(
    tasks: list[TaskRecord],
) -> tuple[list[TaskRecord], list[TaskRecord]]:
    """Split into kept (first occurrence) and dropped (exact duplicates).

    TaskRecord ids retain provenance. The provenance-free semantic identity is
    the dedup key, so independently sourced copies teach only one task.
    """
    seen: set[str] = set()
    kept: list[TaskRecord] = []
    dropped: list[TaskRecord] = []
    for task in tasks:
        semantic_id = semantic_content_id(task)
        if semantic_id in seen:
            dropped.append(task)
        else:
            seen.add(semantic_id)
            kept.append(task)
    return kept, dropped


def diversity_report(snapshot: DatasetSnapshot) -> dict:
    """Report-only structural diversity metrics over the snapshot."""
    skeletons: set[str] = set()
    prompts: set[str] = set()
    for task in snapshot.tasks:
        skeletons.add(reference_skeleton(task.reference))
        prompts.add(prompt_fingerprint(task.prompt))
    return {
        "rows": len(snapshot.tasks),
        "distinct_skeletons": len(skeletons),
        "distinct_prompts": len(prompts),
        "skeleton_fingerprint": hashlib.sha256(
            "|".join(sorted(skeletons)).encode("utf-8")
        ).hexdigest()[:16],
    }
