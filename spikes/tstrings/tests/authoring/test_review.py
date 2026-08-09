"""Seed-review decisions remain bound to review-relevant content."""

import dataclasses

from satyrn_model.authoring.models import Seed
from satyrn_model.authoring.review import seed_content_sha256


def _seed() -> Seed:
    return Seed(
        id="seed-a",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=("occ-a",),
        kind="authored",
    )


def test_seed_review_hash_changes_with_training_content() -> None:
    seed = _seed()

    assert seed_content_sha256(seed) != seed_content_sha256(
        dataclasses.replace(seed, literal='t"Goodbye {name}"')
    )


def test_seed_review_hash_ignores_provenance_occurrences() -> None:
    seed = _seed()

    assert seed_content_sha256(seed) == seed_content_sha256(
        dataclasses.replace(seed, occurrence_ids=("occ-b", "occ-c"))
    )
