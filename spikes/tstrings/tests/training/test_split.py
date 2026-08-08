"""Semantic and seed-lineage groups cannot leak across partitions."""

import dataclasses

import pytest

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    TaskRecord,
)
from satyrn_model.training import (
    LineagedTask,
    SplitError,
    split_by_semantics_and_lineage,
)


def _task(name: str, *, prompt: str | None = None) -> TaskRecord:
    return TaskRecord(
        prompt=prompt or f"task {name}",
        reference=f"result = {name!r}\n",
        checks=(NameEquals(name="result"),),
        policy=PolicyRef(id="test", version=1, config={}),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="test", generator_version="1", seed_id=name
        ),
    )


def test_shared_seed_lineage_is_indivisible() -> None:
    rows = [
        LineagedTask(task=_task("a"), seed_ids=("shared",)),
        LineagedTask(task=_task("b"), seed_ids=("shared",)),
        LineagedTask(task=_task("c"), seed_ids=("other",)),
        LineagedTask(task=_task("d"), seed_ids=("last",)),
    ]

    manifest = split_by_semantics_and_lineage(
        rows, validation_fraction=0.25, split_seed=7
    )

    partitions = {
        task_id: group.partition
        for group in manifest.groups
        for task_id in group.task_ids
    }
    assert partitions[rows[0].task.id] == partitions[rows[1].task.id]
    assert manifest.train_task_ids
    assert manifest.validation_task_ids


def test_semantically_identical_rows_are_indivisible() -> None:
    first = _task("same")
    second = dataclasses.replace(
        first,
        provenance=GeneratedProvenance(
            generator="other", generator_version="2", seed_id="other"
        ),
        id="",
    )
    rows = [
        LineagedTask(task=first, seed_ids=("a",)),
        LineagedTask(task=second, seed_ids=("b",)),
        LineagedTask(task=_task("independent"), seed_ids=("c",)),
    ]

    manifest = split_by_semantics_and_lineage(
        rows, validation_fraction=0.34, split_seed=11
    )

    matching = [
        group
        for group in manifest.groups
        if first.id in group.task_ids or second.id in group.task_ids
    ]
    assert len(matching) == 1
    assert set(matching[0].task_ids) == {first.id, second.id}


def test_single_connected_group_refuses_split() -> None:
    rows = [
        LineagedTask(task=_task("a"), seed_ids=("shared",)),
        LineagedTask(task=_task("b"), seed_ids=("shared",)),
    ]

    with pytest.raises(SplitError, match="indivisible"):
        split_by_semantics_and_lineage(rows, validation_fraction=0.5, split_seed=1)
