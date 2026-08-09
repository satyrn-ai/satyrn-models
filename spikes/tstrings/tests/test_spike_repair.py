"""Regression tests for the two repairs named in STRATIFIED_BATCHING_REVIEW.md.

The review found that benchmark framing was a function of task position, so
capability scores partly measured wording, and that the stratified trainer
silently withheld a different remainder from every epoch.  These tests pin
both properties.
"""

import collections

import numpy as np
import pytest
from spike.build_benchmark_v2 import (
    CELLS,
    FRAMING_IDS,
    VARIANTS_PER_CELL,
    build_repair_v1,
)
from spike.train_lora_stratified import (
    BATCHINGS,
    _batch_indices,
    batch_diversity,
    build_batches,
    stratum_of,
)

from satyrn_model.execution.protocol import Accepted, NullSandbox
from satyrn_model.execution.reference import materialize_reference


def test_framing_is_crossed_with_capability_not_derived_from_position() -> None:
    """Every capability is measured under every framing the same number of times."""
    _, manifest = build_repair_v1()

    cells = collections.Counter(
        (entry["capability"], entry["framing"]) for entry in manifest
    )

    assert len(manifest) == len(CELLS) * len(FRAMING_IDS) * VARIANTS_PER_CELL
    assert set(cells) == {
        (cell.capability, framing) for cell in CELLS for framing in FRAMING_IDS
    }
    assert set(cells.values()) == {VARIANTS_PER_CELL}


def test_repair_benchmark_constants_are_fresh_per_task() -> None:
    """No two tasks reuse a constant, so no family is a near-identical sweep."""
    tasks, manifest = build_repair_v1()

    assert len({task.id for task in tasks}) == len(tasks)
    assert len({task.reference for task in tasks}) == len(tasks)
    assert {entry["review_status"] for entry in manifest} == {"needs_human_review"}


def test_repair_benchmark_references_materialize() -> None:
    """The generator never emits an unexecutable reference program."""
    tasks, _ = build_repair_v1()
    sandbox = NullSandbox()

    outcomes = [
        materialize_reference(task, sandbox=sandbox, timeout=15) for task in tasks
    ]

    assert all(isinstance(outcome, Accepted) for outcome in outcomes)


def test_every_row_is_trained_on_exactly_once_per_epoch() -> None:
    """450 rows at batch size 8 must cover all rows, not the first 448."""
    operations = [f"op-{index % 9}" for index in range(450)]
    rng = np.random.default_rng(42)

    batches = _batch_indices(operations, 8, rng)
    flat = [index for batch in batches for index in batch]

    assert len(batches) == 57
    assert all(len(batch) == 8 for batch in batches)
    assert set(flat) == set(range(450))
    padded = [index for index, count in collections.Counter(flat).items() if count > 1]
    assert len(padded) == 6


def test_no_row_is_withheld_from_any_epoch() -> None:
    """The old batcher dropped a different pair of rows on each epoch."""
    operations = [f"op-{index % 9}" for index in range(450)]
    rng = np.random.default_rng(42)

    epochs = [_batch_indices(operations, 8, rng) for _ in range(3)]

    for batches in epochs:
        assert set(index for batch in batches for index in batch) == set(range(450))


def _strata(count: int = 454) -> list[str]:
    """Role x capability x prompt-family keys with a realistic role imbalance."""
    families = ("direct", "pep750-request", "python-program")
    keys = []
    for index in range(count):
        role = "author" if index % 10 < 3 else "consumer"
        capability = f"cap-{index % 17}"
        keys.append(f"{role}|{capability}|{families[index % 3]}")
    return keys


@pytest.mark.parametrize("mode", BATCHINGS)
def test_every_ordering_covers_every_row_once(mode: str) -> None:
    """Whatever the ordering, an epoch may not withhold rows."""
    strata = _strata()
    operations = [key.split("|")[1] for key in strata]

    batches = build_batches(
        mode,
        strata=strata,
        operations=operations,
        batch_size=8,
        rng=np.random.default_rng(42),
    )
    flat = [index for batch in batches for index in batch]

    assert len(batches) == 57
    assert all(len(batch) == 8 for batch in batches)
    assert set(flat) == set(range(len(strata)))


@pytest.mark.parametrize("mode", BATCHINGS)
def test_orderings_are_deterministic_given_a_seed(mode: str) -> None:
    strata = _strata()
    operations = [key.split("|")[1] for key in strata]

    def run() -> list[list[int]]:
        return build_batches(
            mode,
            strata=strata,
            operations=operations,
            batch_size=8,
            rng=np.random.default_rng(7),
        )

    assert run() == run()


def _batches(mode: str, strata: list[str], seed: int = 42) -> list[list[int]]:
    return build_batches(
        mode,
        strata=strata,
        operations=[key.split("|")[1] for key in strata],
        batch_size=8,
        rng=np.random.default_rng(seed),
    )


def test_interleaved_batches_never_repeat_a_stratum() -> None:
    """The design guarantee: a batch spans `batch_size` distinct cells."""
    strata = _strata()

    batches = _batches("interleaved", strata)

    spans = [len({strata[index] for index in batch}) for batch in batches]
    assert set(spans) == {8}


def test_interleaving_spans_more_strata_than_shuffling() -> None:
    strata = _strata()

    interleaved = batch_diversity(_batches("interleaved", strata), strata)
    shuffled = batch_diversity(_batches("shuffled", strata), strata)

    assert interleaved["mean_distinct_strata"] > shuffled["mean_distinct_strata"]
    assert interleaved["min_distinct_strata"] > shuffled["min_distinct_strata"]


def test_single_role_batches_are_confined_to_the_epoch_tail() -> None:
    """Role mixing may only degenerate once a role has run out.

    Shuffling scatters single-role batches through the epoch; interleaving
    holds the global role share per batch until one role is exhausted, so any
    degeneration is confined to the final batches. This does not assert a
    lower *count* than shuffling — with one role at 30% of rows, shuffling can
    happen to produce fewer — it asserts the stronger structural property.
    """
    strata = _strata()

    batches = _batches("interleaved", strata)
    single_role = [
        position
        for position, batch in enumerate(batches)
        if len({strata[index].split("|")[0] for index in batch}) == 1
    ]

    assert all(position >= len(batches) * 0.9 for position in single_role), single_role


def test_unknown_batching_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown batching mode"):
        build_batches(
            "length-sorted",
            strata=["a"],
            operations=["a"],
            batch_size=1,
            rng=np.random.default_rng(0),
        )


def test_stratum_falls_back_for_pre_repair_selections() -> None:
    """Selections predating the curriculum repair carry no capability."""
    old = {"role": "consumer", "operation": "strings", "prompt_family": "direct"}
    new = {
        "cell_role": "author",
        "capability": "author_strings",
        "operation": "strings",
        "prompt_family": "direct",
    }

    assert stratum_of(old) == "consumer|strings|direct"
    assert stratum_of(new) == "author|author_strings|direct"
