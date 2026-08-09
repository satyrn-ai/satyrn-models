"""Seed normalization: many occurrences → one Seed per unique content.

Splitting models from operations keeps the frozen dataclasses in ``models.py``
and the grouping/round-trip logic here.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .models import Seed, SeedOccurrence, SourceOrigin

__all__ = [
    "normalize_seeds",
    "read_occurrences_jsonl",
    "read_seeds_jsonl",
    "write_occurrences_jsonl",
    "write_seeds_jsonl",
]


def normalize_seeds(
    occurrences: list[SeedOccurrence],
) -> list[Seed]:
    """Group occurrences by seed_id; each group becomes one ``Seed``.

    All occurrences with the same content-derived ``seed_id`` share one
    ``Seed``, preserving every origin rather than picking one.
    """
    by_sid: dict[str, list[SeedOccurrence]] = {}
    for occ in occurrences:
        by_sid.setdefault(occ.seed_id, []).append(occ)

    seeds: list[Seed] = []
    for _sid, occs in by_sid.items():
        first = occs[0]
        domains = {occ.domain for occ in occs}
        if len(domains) != 1:
            raise ValueError(
                f"seed {first.seed_id!r} has conflicting domains: "
                f"{sorted(domains)}"
            )
        seeds.append(
            Seed(
                id=first.seed_id,
                literal=first.literal,
                free_names=first.free_names,
                bindings=first.bindings,
                occurrence_ids=tuple(occ.id for occ in occs),
                kind=first.kind,
                domain=first.domain,
            )
        )
    return seeds


def write_seeds_jsonl(seeds: list[Seed], path: Path) -> None:
    """Write seeds as deterministic JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for seed in seeds:
            f.write(json.dumps(dataclasses.asdict(seed), sort_keys=True))
            f.write("\n")


def write_occurrences_jsonl(
    occurrences: list[SeedOccurrence], path: Path
) -> None:
    """Write source-resolved occurrence records as deterministic JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for occurrence in occurrences:
            f.write(json.dumps(dataclasses.asdict(occurrence), sort_keys=True))
            f.write("\n")


def read_seeds_jsonl(path: Path) -> list[Seed]:
    """Read and validate seeds from JSON Lines, ignoring blank lines."""
    seeds: list[Seed] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            seeds.append(Seed(**data))
    return seeds


def read_occurrences_jsonl(path: Path) -> list[SeedOccurrence]:
    """Read occurrence records with their source-manifest foreign keys."""
    occurrences: list[SeedOccurrence] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            data["origin"] = SourceOrigin(**data["origin"])
            data["free_names"] = tuple(data["free_names"])
            data["bindings"] = tuple(tuple(pair) for pair in data["bindings"])
            occurrences.append(SeedOccurrence(**data))
    return occurrences
