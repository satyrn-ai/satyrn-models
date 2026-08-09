"""Leakage-safe train/validation grouping.

Rows form connected components when they share either provenance-free
semantic task identity or any producer-supplied seed lineage. A connected
component is indivisible, so prompt rewrites and seed siblings cannot cross
the train/validation boundary.
"""

import dataclasses
import hashlib
import json

from satyrn_model.contracts import TaskRecord, semantic_content_id


class SplitError(ValueError):
    """A leakage-safe split cannot be constructed from the supplied rows."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class LineagedTask:
    task: TaskRecord
    seed_ids: tuple[str, ...]
    prompt_family: str = "default"


@dataclasses.dataclass(frozen=True, kw_only=True)
class SplitGroup:
    id: str
    partition: str
    task_ids: tuple[str, ...]
    semantic_ids: tuple[str, ...]
    seed_ids: tuple[str, ...]
    prompt_families: tuple[str, ...]


@dataclasses.dataclass(frozen=True, kw_only=True)
class SplitManifest:
    split_seed: int
    requested_validation_fraction: float
    train_task_ids: tuple[str, ...]
    validation_task_ids: tuple[str, ...]
    groups: tuple[SplitGroup, ...]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def split_by_semantics_and_lineage(
    rows: list[LineagedTask],
    *,
    validation_fraction: float,
    split_seed: int,
) -> SplitManifest:
    """Assign connected semantic/seed groups to train or validation."""
    if not 0.0 < validation_fraction < 1.0:
        raise SplitError("validation_fraction must be between zero and one")
    if len({row.task.id for row in rows}) != len(rows):
        raise SplitError("task ids must be unique")
    if len(rows) < 2:
        raise SplitError("at least two rows are required")

    components = _connected_components(rows)
    if len(components) < 2:
        raise SplitError("all rows belong to one indivisible leakage group")

    target = round(len(rows) * validation_fraction)
    target = min(max(target, 1), len(rows) - 1)
    validation_components = _closest_component_subset(components, target, split_seed)

    groups: list[SplitGroup] = []
    train_ids: list[str] = []
    validation_ids: list[str] = []
    for index, component in enumerate(components):
        partition = "validation" if index in validation_components else "train"
        task_ids = tuple(sorted(rows[item].task.id for item in component))
        semantic_ids = tuple(
            sorted({semantic_content_id(rows[item].task) for item in component})
        )
        seed_ids = tuple(
            sorted({seed for item in component for seed in rows[item].seed_ids})
        )
        prompt_families = tuple(
            sorted({rows[item].prompt_family for item in component})
        )
        group_id = _digest(
            {"tasks": task_ids, "semantics": semantic_ids, "seeds": seed_ids}
        )
        groups.append(
            SplitGroup(
                id=group_id,
                partition=partition,
                task_ids=task_ids,
                semantic_ids=semantic_ids,
                seed_ids=seed_ids,
                prompt_families=prompt_families,
            )
        )
        (validation_ids if partition == "validation" else train_ids).extend(task_ids)

    return SplitManifest(
        split_seed=split_seed,
        requested_validation_fraction=validation_fraction,
        train_task_ids=tuple(sorted(train_ids)),
        validation_task_ids=tuple(sorted(validation_ids)),
        groups=tuple(groups),
    )


def _connected_components(rows: list[LineagedTask]) -> list[tuple[int, ...]]:
    parents = list(range(len(rows)))

    def find(item: int) -> int:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    owners: dict[str, int] = {}
    for index, row in enumerate(rows):
        keys = (f"semantic:{semantic_content_id(row.task)}",) + tuple(
            f"seed:{seed_id}" for seed_id in row.seed_ids
        )
        for key in keys:
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index

    grouped: dict[int, list[int]] = {}
    for index in range(len(rows)):
        grouped.setdefault(find(index), []).append(index)
    return sorted(
        (tuple(items) for items in grouped.values()),
        key=lambda items: tuple(rows[item].task.id for item in items),
    )


def _closest_component_subset(
    components: list[tuple[int, ...]], target: int, split_seed: int
) -> frozenset[int]:
    ranked = sorted(
        range(len(components)),
        key=lambda index: _digest(
            {"split_seed": split_seed, "component": components[index]}
        ),
    )
    reachable: dict[int, tuple[int, ...]] = {0: ()}
    for index in ranked:
        size = len(components[index])
        additions = {
            count + size: chosen + (index,)
            for count, chosen in tuple(reachable.items())
            if count + size < sum(map(len, components))
        }
        for count, chosen in additions.items():
            reachable.setdefault(count, chosen)
    best = min(
        (count for count in reachable if count > 0),
        key=lambda count: (abs(count - target), count),
    )
    return frozenset(reachable[best])


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
