"""Composition floor over the deduplicated, diversified corpus."""

from collections import Counter

from satyrn.tstrings.types import Task


def cell_counts(tasks: list[Task]) -> dict[tuple[str, str], int]:
    """Return the number of tasks per (role, operation) cell."""
    return dict(Counter((task.role, task.operation) for task in tasks))


def check_composition(tasks: list[Task], floors: dict[tuple[str, str], int]) -> None:
    """Raise ValueError naming any cell whose task count is below its floor."""
    counts = cell_counts(tasks)
    for (role, operation), floor in floors.items():
        if counts.get((role, operation), 0) < floor:
            raise ValueError(
                f"cell ({role}, {operation}) has {counts.get((role, operation), 0)} tasks, below floor {floor}"
            )
