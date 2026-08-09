"""SP5 publication: immutable, composition-matched nested snapshots.

Publishes 500 ⊂ 2k ⊂ 5k nested snapshots: the larger selection is stratified
first, then each smaller size is selected from the larger one, so row ids
nest by construction. Every snapshot is rechecked before publication —
provider qualification, benchmark contamination, and composition match
against the committed calibration bands — then written atomically with its
manifest, self-contained lineage, source/license inventory, and NOTICE.

No oracle logic lives here; qualification is the provider's ``qualify_task``.
"""

import dataclasses
import hashlib
import json
from collections import Counter
from pathlib import Path

from satyrn_model.authoring.build import (
    atomic_write_text,
    check_contamination,
)
from satyrn_model.authoring.diversity import diversity_report
from satyrn_model.authoring.sampling import (
    CalibrationError,
    CalibrationRecord,
    SampleRow,
    SamplingPlan,
    select_pilot,
)
from satyrn_model.contracts import (
    DatasetSnapshot,
    TaskRecord,
    dump_snapshot,
    semantic_content_id,
)
from satyrn_model.contracts.versions import DATASET_CONTRACT_VERSION
from satyrn_model.execution.protocol import SandboxBackend
from satyrn_model.oracle.qualify import Qualified, qualify_task
from satyrn_model.policies.tstring import TStringPolicy

_builtin_property = property

__all__ = [
    "CompositionMismatch",
    "PublishError",
    "PublishRow",
    "PublishedSnapshot",
    "publish_nested",
]


class PublishError(RuntimeError):
    """A snapshot failed a publication recheck (qualification, composition)."""


class CompositionMismatch(PublishError):
    """Observed strata fractions fall outside the committed calibration bands."""


@dataclasses.dataclass(frozen=True)
class PublishRow:
    """One qualified task with its stratum attributes and lineage links."""

    task: TaskRecord
    sample: SampleRow
    links: dict

    # The class exposes a ``property`` accessor, so the builtin decorator is
    # aliased at module scope to avoid the class-body name clash.
    @_builtin_property
    def row_id(self) -> str:
        return self.task.id

    @_builtin_property
    def source_kind(self) -> str:
        return self.sample.source_kind

    @_builtin_property
    def role(self) -> str:
        return self.sample.role

    @_builtin_property
    def domain(self) -> str:
        return self.sample.domain

    @_builtin_property
    def property(self) -> str:
        return self.sample.property

    @_builtin_property
    def pattern_id(self) -> str:
        return self.sample.pattern_id

    @_builtin_property
    def seed_id(self) -> str:
        return self.sample.seed_id


@dataclasses.dataclass(frozen=True)
class PublishedSnapshot:
    """An immutable published slice and its committed artifacts."""

    size: int
    snapshot: DatasetSnapshot
    manifest: dict
    lineage: tuple[dict, ...]
    notice: str
    inventory: list[dict]
    dir: Path


def publish_nested(
    rows: list[PublishRow],
    *,
    sizes: tuple[int, ...],
    plan: SamplingPlan,
    profile_version: int,
    calibration: CalibrationRecord | None,
    benchmark: list[tuple[str, str]],
    sandbox: SandboxBackend,
    out_dir: Path,
    timeout: int = 30,
) -> tuple[PublishedSnapshot, ...]:
    """Publish nested, stratified snapshots at *sizes* (descending, so each
    smaller selection nests inside the larger one).

    Requires a committed calibration record matching *profile_version*;
    rechecks qualification, contamination, and composition per snapshot.
    """
    if calibration is None:
        raise CalibrationError(
            "publishing requires a committed calibration record; "
            "run `authoring pilot` first"
        )
    if calibration.profile_version != profile_version:
        raise CalibrationError(
            f"calibration profile version v{calibration.profile_version} "
            f"does not match current profile version v{profile_version}; "
            "rerun calibration"
        )

    ordered = sorted(sizes, reverse=True)
    selections: dict[int, list[PublishRow]] = {}
    pool = _deduplicate_publish_rows(rows)
    for size in ordered:
        pool = select_pilot(pool, plan=plan, target_rows=size)
        selections[size] = pool

    results: list[PublishedSnapshot] = []
    for size in ordered:
        results.append(
            _publish_one(
                selections[size],
                size=size,
                profile_version=profile_version,
                calibration=calibration,
                benchmark=benchmark,
                sandbox=sandbox,
                out_dir=Path(out_dir),
                timeout=timeout,
            )
        )
    return tuple(results)


def _publish_one(
    rows: list[PublishRow],
    *,
    size: int,
    profile_version: int,
    calibration: CalibrationRecord,
    benchmark: list[tuple[str, str]],
    sandbox: SandboxBackend,
    out_dir: Path,
    timeout: int,
) -> PublishedSnapshot:
    # -- Recheck: provider qualification -----------------------------------
    for pr in rows:
        outcome = qualify_task(
            pr.task, policy=TStringPolicy(), sandbox=sandbox, timeout=timeout
        )
        if not isinstance(outcome, Qualified):
            raise PublishError(
                f"row {pr.task.id[:12]} failed re-qualification: "
                f"{getattr(outcome, 'reason', type(outcome).__name__)}"
            )

    snapshot = DatasetSnapshot.from_tasks(tuple(pr.task for pr in rows))
    check_contamination(snapshot, benchmark)
    _check_composition(rows, calibration)

    # -- Artifacts ----------------------------------------------------------
    lineage = [{"row_id": pr.task.id, **pr.links} for pr in rows]
    lineage_text = "".join(
        json.dumps(entry, sort_keys=True) + "\n" for entry in lineage
    )
    inventory = _inventory(lineage)
    notice = _notice(inventory)
    bench_fp = hashlib.sha256(
        json.dumps(sorted(benchmark), sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]

    manifest = {
        "snapshot_size": size,
        "contract_version": DATASET_CONTRACT_VERSION,
        "profile_version": profile_version,
        "snapshot_fingerprint": snapshot.manifest.fingerprint,
        "row_ids": [pr.task.id for pr in rows],
        "strata": {
            "property": dict(Counter(pr.property for pr in rows)),
            "source_kind": dict(Counter(pr.source_kind for pr in rows)),
            "role": dict(Counter(pr.role for pr in rows)),
            "domain": dict(Counter(pr.domain for pr in rows)),
        },
        "exact_duplicates": len(rows)
        - len({semantic_content_id(pr.task) for pr in rows}),
        "benchmark_fingerprint": bench_fp,
        "calibration": {
            "profile_version": calibration.profile_version,
            "review_budget": calibration.review_budget,
        },
        "diversity": diversity_report(snapshot),
        "lineage_fingerprint": hashlib.sha256(lineage_text.encode("utf-8")).hexdigest()[
            :16
        ],
    }

    snap_dir = out_dir / f"snapshots/{size}"
    atomic_write_text(snap_dir / "tstrings.jsonl", dump_snapshot(snapshot))
    atomic_write_text(
        snap_dir / "manifest.json",
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
    )
    atomic_write_text(snap_dir / "lineage.jsonl", lineage_text)
    atomic_write_text(
        snap_dir / "inventory.json",
        json.dumps(inventory, sort_keys=True, indent=2) + "\n",
    )
    atomic_write_text(snap_dir / "NOTICE", notice)

    return PublishedSnapshot(
        size=size,
        snapshot=snapshot,
        manifest=manifest,
        lineage=tuple(lineage),
        notice=notice,
        inventory=inventory,
        dir=snap_dir,
    )


def _deduplicate_publish_rows(rows: list[PublishRow]) -> list[PublishRow]:
    """Keep one learning-equivalent row and preserve all lineage links.

    The primary row keeps its regular provenance-bearing id. Additional links
    are embedded in its self-contained lineage entry, rather than published
    as duplicate training examples.
    """
    kept: list[PublishRow] = []
    seen: dict[str, int] = {}
    for row in rows:
        semantic_id = semantic_content_id(row.task)
        if semantic_id not in seen:
            seen[semantic_id] = len(kept)
            kept.append(row)
            continue

        index = seen[semantic_id]
        retained = kept[index]
        additional = list(retained.links.get("deduplicated_lineage", []))
        additional.append(
            {
                "source_kind": row.source_kind,
                "domain": row.domain,
                "property": row.property,
                "pattern_id": row.pattern_id,
                "seed_id": row.seed_id,
                "links": row.links,
            }
        )
        kept[index] = dataclasses.replace(
            retained,
            links={**retained.links, "deduplicated_lineage": additional},
        )
    return kept


def _check_composition(rows: list[PublishRow], calibration: CalibrationRecord) -> None:
    """Observed property fractions must fall inside the committed bands."""
    n = len(rows) or 1
    observed = Counter(pr.property for pr in rows)
    for prop, count in observed.items():
        fraction = count / n
        band = calibration.composition_tolerance.get(prop, [0.0, 1.0])
        if not band[0] <= fraction <= band[1]:
            raise CompositionMismatch(
                f"{prop} fraction {fraction:.3f} outside committed band {band}"
            )


def _inventory(lineage: list[dict]) -> list[dict]:
    """Distinct (source_id, path, license) entries from lineage links."""
    seen: set[tuple] = set()
    inventory: list[dict] = []
    for entry in lineage:
        key = (entry.get("source_id"), entry.get("path"), entry.get("license"))
        if key[0] and key not in seen:
            seen.add(key)
            inventory.append({"source_id": key[0], "path": key[1], "license": key[2]})
    return inventory


def _notice(inventory: list[dict]) -> str:
    lines = [
        "satyrn-model SP5 t-string training corpus",
        "",
    ]
    if inventory:
        for item in inventory:
            lines.append(
                f"Source {item['path']} ({item['source_id']}) — "
                f"License: {item['license']}"
            )
    else:
        lines.append(
            "All rows were generated by the SP5 project; no third-party "
            "source material is included."
        )
    return "\n".join(lines) + "\n"
