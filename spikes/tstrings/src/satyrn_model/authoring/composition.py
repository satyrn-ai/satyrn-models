"""Composition-profile loading and pre-pilot capacity gates."""

from __future__ import annotations

import dataclasses
import hashlib
import math
import tomllib
from collections import Counter, defaultdict, deque
from pathlib import Path

from .sampling import SampleRow

DIMENSIONS = ("property", "source_kind", "role", "domain", "operation")


@dataclasses.dataclass(frozen=True)
class CompositionProfile:
    """Versioned marginal targets from ``composition.toml``."""

    version: int
    targets: dict[str, dict[str, float]]


@dataclasses.dataclass(frozen=True)
class CapacityDeficit:
    """One target stratum that the qualified pool cannot fill."""

    dimension: str
    stratum: str
    required: int
    available: int


class CompositionSelectionError(RuntimeError):
    """No exact selection was found for the committed marginal targets."""


def load_composition_profile(path: Path) -> CompositionProfile:
    """Load and validate the profile's supported marginal targets."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    targets = {
        dimension: dict(data.get("targets", {}).get(dimension, {}))
        for dimension in DIMENSIONS
        if data.get("targets", {}).get(dimension)
    }
    for dimension, strata in targets.items():
        total = sum(strata.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"composition targets for {dimension!r} sum to {total}, not 1.0"
            )
        if any(value < 0 for value in strata.values()):
            raise ValueError(f"composition targets for {dimension!r} are negative")
    return CompositionProfile(version=int(data["profile"]["version"]), targets=targets)


def target_counts(target_rows: int, proportions: dict[str, float]) -> dict[str, int]:
    """Allocate an integer target with deterministic largest remainders."""
    raw = {label: target_rows * fraction for label, fraction in proportions.items()}
    counts = {label: math.floor(value) for label, value in raw.items()}
    remainder = target_rows - sum(counts.values())
    ranked = sorted(
        raw,
        key=lambda label: (raw[label] - counts[label], label),
        reverse=True,
    )
    for label in ranked[:remainder]:
        counts[label] += 1
    return counts


def capacity_deficits(
    rows: list[SampleRow], profile: CompositionProfile, target_rows: int
) -> list[CapacityDeficit]:
    """Return every marginal quota that the qualified pool cannot supply."""
    deficits: list[CapacityDeficit] = []
    if len({row.row_id for row in rows}) < target_rows:
        deficits.append(
            CapacityDeficit(
                dimension="pool",
                stratum="unique_rows",
                required=target_rows,
                available=len({row.row_id for row in rows}),
            )
        )
    for dimension, proportions in profile.targets.items():
        available = Counter(getattr(row, dimension) for row in rows)
        for stratum, required in target_counts(target_rows, proportions).items():
            count = available[stratum]
            if count < required:
                deficits.append(
                    CapacityDeficit(
                        dimension=dimension,
                        stratum=stratum,
                        required=required,
                        available=count,
                    )
                )
    return deficits


def capacity_report(
    rows: list[SampleRow], profile: CompositionProfile, target_rows: int
) -> str:
    """Render an auditable capacity report for the next pilot attempt."""
    deficits = capacity_deficits(rows, profile, target_rows)
    lines = [
        "# Pilot capacity",
        "",
        f"- profile version: {profile.version}",
        f"- target rows: {target_rows}",
        f"- qualified unique rows: {len({row.row_id for row in rows})}",
        f"- insufficient strata: {len(deficits)}",
        "",
        "## Deficits",
        "",
    ]
    if not deficits:
        lines.append("- none")
    else:
        for deficit in deficits:
            lines.append(
                f"- {deficit.dimension}.{deficit.stratum}: "
                f"requires {deficit.required}, available {deficit.available}, "
                f"short {deficit.required - deficit.available}"
            )
    return "\n".join(lines) + "\n"


def _selection_score(
    row: SampleRow,
    dimensions: tuple[str, ...],
    remaining: dict[str, dict[str, int]],
    availability: dict[str, Counter],
    seen_seeds: set[str],
    seen_patterns: set[str],
    attempt: int,
) -> tuple[float, int]:
    scarcity = sum(
        remaining[dimension][getattr(row, dimension)]
        / availability[dimension][getattr(row, dimension)]
        for dimension in dimensions
    )
    diversity = (row.seed_id not in seen_seeds) + (
        row.pattern_id not in seen_patterns
    )
    tie = int.from_bytes(
        hashlib.sha256(f"{attempt}:{row.row_id}".encode()).digest()[:8]
    )
    return scarcity + diversity * 0.001, tie


def select_composed_pilot(
    rows: list[SampleRow],
    profile: CompositionProfile,
    target_rows: int,
    *,
    attempts: int = 64,
) -> list[SampleRow]:
    """Select rows matching every profile marginal exactly.

    The qualified pool is a sparse four-dimensional contingency table, so a
    nested sampler can silently make impossible early choices. This bounded,
    deterministic greedy search prioritizes the scarcest remaining strata and
    retries with stable hash tie-breaks. A result is returned only when every
    marginal reaches its exact integer quota.
    """
    deficits = capacity_deficits(rows, profile, target_rows)
    if deficits:
        raise CompositionSelectionError(
            f"qualified pool has {len(deficits)} marginal capacity deficit(s)"
        )
    four_dimensions = ("property", "source_kind", "role", "domain")
    if set(profile.targets) == set(four_dimensions):
        exact = _select_four_marginals(rows, profile, target_rows, attempts)
        if exact is not None:
            return exact
        raise CompositionSelectionError(
            f"could not select {target_rows} rows: profile marginals are not "
            "jointly feasible under qualified category capacities"
        )
    quotas = {
        dimension: target_counts(target_rows, proportions)
        for dimension, proportions in profile.targets.items()
    }
    unique_rows = list({row.row_id: row for row in rows}.values())

    for attempt in range(attempts):
        remaining = {dimension: dict(counts) for dimension, counts in quotas.items()}
        available_rows = list(unique_rows)
        selected: list[SampleRow] = []
        seen_seeds: set[str] = set()
        seen_patterns: set[str] = set()

        while len(selected) < target_rows:
            eligible = [
                row
                for row in available_rows
                if all(
                    remaining[dimension].get(getattr(row, dimension), 0) > 0
                    for dimension in profile.targets
                )
            ]
            if not eligible:
                break
            availability = {
                dimension: Counter(getattr(row, dimension) for row in eligible)
                for dimension in profile.targets
            }

            chosen = max(
                eligible,
                key=lambda row: _selection_score(
                    row,
                    tuple(profile.targets),
                    remaining,
                    availability,
                    seen_seeds,
                    seen_patterns,
                    attempt,
                ),
            )
            selected.append(chosen)
            available_rows.remove(chosen)
            seen_seeds.add(chosen.seed_id)
            seen_patterns.add(chosen.pattern_id)
            for dimension in profile.targets:
                remaining[dimension][getattr(chosen, dimension)] -= 1

        if len(selected) == target_rows and all(
            count == 0
            for counts in remaining.values()
            for count in counts.values()
        ):
            return selected

    raise CompositionSelectionError(
        f"could not select {target_rows} rows matching all profile marginals "
        f"after {attempts} deterministic attempts"
    )


def _bipartite_flow(
    supplies: dict[tuple, int],
    demands: dict[tuple, int],
    capacities: dict[tuple[tuple, tuple], int],
    *,
    attempt: int,
) -> dict[tuple[tuple, tuple], int] | None:
    """Solve a small integer bipartite flow with Edmonds-Karp."""
    source = ("__source__",)
    sink = ("__sink__",)
    residual: dict[tuple, dict[tuple, int]] = defaultdict(dict)
    adjacency: dict[tuple, list[tuple]] = defaultdict(list)

    def add_edge(left: tuple, right: tuple, capacity: int) -> None:
        if right not in residual[left]:
            adjacency[left].append(right)
            adjacency[right].append(left)
            residual[right][left] = 0
        residual[left][right] = capacity

    for left, supply in supplies.items():
        add_edge(source, left, supply)
    ordered_edges = sorted(
        capacities,
        key=lambda edge: hashlib.sha256(
            f"{attempt}:{edge!r}".encode()
        ).digest(),
    )
    for left, right in ordered_edges:
        add_edge(left, right, capacities[(left, right)])
    for right, demand in demands.items():
        add_edge(right, sink, demand)

    flow = 0
    target = sum(demands.values())
    while flow < target:
        parent: dict[tuple, tuple | None] = {source: None}
        queue = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for neighbor in adjacency[node]:
                if neighbor not in parent and residual[node].get(neighbor, 0) > 0:
                    parent[neighbor] = node
                    queue.append(neighbor)
        if sink not in parent:
            return None
        increment = target - flow
        path: list[tuple[tuple, tuple]] = []
        node = sink
        while node != source:
            previous = parent[node]
            assert previous is not None
            path.append((previous, node))
            increment = min(increment, residual[previous][node])
            node = previous
        for previous, node in path:
            residual[previous][node] -= increment
            residual[node][previous] = residual[node].get(previous, 0) + increment
        flow += increment

    return {
        edge: capacity - residual[edge[0]][edge[1]]
        for edge, capacity in capacities.items()
        if capacity - residual[edge[0]][edge[1]] > 0
    }


def _select_four_marginals(
    rows: list[SampleRow],
    profile: CompositionProfile,
    target_rows: int,
    attempts: int,
) -> list[SampleRow] | None:
    """Solve source/role/property/domain marginals as two exact flows."""
    quotas = {
        dimension: target_counts(target_rows, profile.targets[dimension])
        for dimension in ("property", "source_kind", "role", "domain")
    }
    cells: dict[tuple[str, str, str, str], list[SampleRow]] = defaultdict(list)
    for row in {row.row_id: row for row in rows}.values():
        cells[(row.source_kind, row.role, row.property, row.domain)].append(row)

    source_target = quotas["source_kind"]
    role_target = quotas["role"]
    authored = source_target.get("authored", 0)
    extracted = source_target.get("extracted", 0)
    author = role_target.get("author", 0)
    consumer = role_target.get("consumer", 0)
    available_left = Counter((key[0], key[1]) for key in cells for _ in cells[key])
    property_supplies = {
        ("property", key): value for key, value in quotas["property"].items()
    }
    domain_demands = {
        ("domain", key): value for key, value in quotas["domain"].items()
    }
    property_domain_capacity: Counter = Counter()
    for (_source, _role, property_name, domain), category_rows in cells.items():
        property_domain_capacity[
            (("property", property_name), ("domain", domain))
        ] += len(category_rows)

    lower = max(0, authored - consumer, author - extracted)
    upper = min(authored, author)
    for authored_author in range(lower, upper + 1):
        left_supplies = {
            ("left", "authored", "author"): authored_author,
            ("left", "authored", "consumer"): authored - authored_author,
            ("left", "extracted", "author"): author - authored_author,
            ("left", "extracted", "consumer"): extracted
            - (author - authored_author),
        }
        if any(
            supply < 0
            or supply > available_left[(left[1], left[2])]
            for left, supply in left_supplies.items()
        ):
            continue
        for attempt in range(attempts):
            property_domain = _bipartite_flow(
                property_supplies,
                domain_demands,
                dict(property_domain_capacity),
                attempt=attempt,
            )
            if property_domain is None:
                return None
            right_demands = {
                ("right", edge[0][1], edge[1][1]): count
                for edge, count in property_domain.items()
            }
            assignment_capacity: dict[tuple[tuple, tuple], int] = {}
            for key, category_rows in cells.items():
                source_kind, role, property_name, domain = key
                assignment_capacity[
                    (
                        ("left", source_kind, role),
                        ("right", property_name, domain),
                    )
                ] = len(category_rows)
            assignment = _bipartite_flow(
                left_supplies,
                right_demands,
                assignment_capacity,
                attempt=attempt,
            )
            if assignment is None:
                continue
            selected: list[SampleRow] = []
            for (left, right), count in assignment.items():
                category = (left[1], left[2], right[1], right[2])
                ordered = sorted(
                    cells[category],
                    key=lambda row: hashlib.sha256(row.row_id.encode()).digest(),
                )
                selected.extend(ordered[:count])
            if len(selected) == target_rows:
                return selected
    return None
