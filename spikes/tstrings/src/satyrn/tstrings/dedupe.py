"""Deduplicate mined tasks on their content hash."""

from satyrn.tstrings.types import Task


def deduplicate(tasks: list[Task]) -> tuple[list[Task], int]:
    """Return tasks with one entry per semantic_id plus the number removed."""
    kept: list[Task] = []
    seen: set[str] = set()
    removed = 0
    for task in tasks:
        if task.semantic_id in seen:
            removed += 1
            continue
        seen.add(task.semantic_id)
        kept.append(task)
    return kept, removed
