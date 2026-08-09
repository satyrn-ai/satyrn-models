"""SP5 build: render, qualify, dedup, contamination gate, atomic artifacts.

The build pipeline renders qualified source intents and generated intents
into provider ``TaskRecord``s, applies local gates and provider
qualification, performs exact dedup, and halts publication on any benchmark
contamination. Artifacts are written atomically: the corpus snapshot,
full-content ``reports/dropped.jsonl``, ``reports/build.md``, the
row→seed→occurrence lineage bundle, and a manifest of fingerprints.

No oracle logic lives here — qualification is the provider's ``qualify_task``.
"""

import dataclasses
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from satyrn_model.authoring.diversity import diversity_report, reference_skeleton
from satyrn_model.authoring.generate import generation_fingerprint
from satyrn_model.authoring.models import (
    GeneratedExercise,
    SourceExerciseCandidate,
)
from satyrn_model.authoring.patterns.approvals import (
    PatternApproval,
    require_approval,
)
from satyrn_model.authoring.patterns.registry import (
    Pattern,
    classify,
    classify_operation,
    pattern_input_fingerprint,
)
from satyrn_model.authoring.sampling import SampleRow
from satyrn_model.authoring.static_gates import (
    check_imports,
    check_third_party_names,
)
from satyrn_model.authoring.task_builder import build_task, generated_intent
from satyrn_model.contracts import (
    DatasetSnapshot,
    TaskRecord,
    dump_snapshot,
    semantic_content_id,
)
from satyrn_model.contracts.versions import DATASET_CONTRACT_VERSION
from satyrn_model.execution.protocol import InfrastructureFailure, SandboxBackend
from satyrn_model.oracle.qualify import (
    Qualified,
    qualify_task,
)
from satyrn_model.policies.tstring import TStringPolicy

__all__ = [
    "BuildResult",
    "BuildInfrastructureError",
    "ContaminationError",
    "DroppedRow",
    "atomic_write_text",
    "build_pipeline",
    "check_contamination",
]


class ContaminationError(RuntimeError):
    """A corpus row duplicates a benchmark task; publication must halt."""


class BuildInfrastructureError(RuntimeError):
    """Provider infrastructure failed; publication must halt."""


@dataclasses.dataclass(frozen=True)
class DroppedRow:
    """A rejected row, with full content and its lineage links."""

    stage: str
    reason: str
    content: dict
    links: dict


@dataclasses.dataclass(frozen=True)
class BuildResult:
    """The outcome of a build: snapshot, drops, lineage, and manifest."""

    snapshot: DatasetSnapshot
    dropped: tuple[DroppedRow, ...]
    lineage: tuple[dict, ...]
    sample_rows: tuple[SampleRow, ...]
    manifest: dict
    out_dir: Path


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* via a same-directory temp file + replace; on failure the
    prior artifact is untouched and no temp file is left behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Contamination gate
# ---------------------------------------------------------------------------


def check_contamination(
    snapshot: DatasetSnapshot, benchmark: list[tuple[str, str]]
) -> None:
    """Raise ``ContaminationError`` if any row exactly duplicates a benchmark
    task's (prompt, reference). No "small enough to drop" exception."""
    bench = {(prompt, ref) for prompt, ref in benchmark}
    for task in snapshot.tasks:
        if (task.prompt, task.reference) in bench:
            raise ContaminationError(f"task {task.id[:12]} duplicates a benchmark task")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def _outcome_stage(outcome: object) -> str:
    stage = getattr(outcome, "stage", None)
    if stage:
        return stage
    return type(outcome).__name__.lower()


def _render_source(row: SourceExerciseCandidate) -> tuple[TaskRecord, str, dict]:
    task = build_task(row.intent)
    links = {
        "source_id": row.origin.source_id,
        "path": row.origin.path,
        "span": [row.origin.line_start, row.origin.line_end],
        "license": row.origin.license,
        "source_kind": "extracted",
        "role": row.intent.role,
        "domain": "text",
        "property": _single_property_label(classify(row.intent.properties)),
        "operation": classify_operation(row.intent.properties),
        "pattern_id": "source",
        "prompt_family": "source",
        "seed_ids": [row.intent.id],
    }
    return task, "source", links


def _pattern_for(exercise: GeneratedExercise, patterns: list[Pattern]) -> Pattern:
    for pattern in patterns:
        if pattern.id == exercise.pattern_id:
            return pattern
    raise ValueError(
        f"pattern {exercise.pattern_id!r} is not in the build's pattern set"
    )


def _render_generated(
    exercise: GeneratedExercise, patterns: list[Pattern]
) -> tuple[TaskRecord, str, dict]:
    pattern = _pattern_for(exercise, patterns)
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)
    links = {
        "pattern_id": exercise.pattern_id,
        "prompt_family": exercise.prompt_family,
        "seed_ids": [s.id for s in exercise.seeds],
        "occurrence_ids": [oid for s in exercise.seeds for oid in s.occurrence_ids],
        "source_kind": _exercise_source_kind(exercise),
        "role": pattern.role,
        "domain": _exercise_domain(exercise),
        "property": _single_property_label(pattern.labels),
        "operation": classify_operation(exercise.properties),
    }
    return task, "generated", links


def _single_property_label(labels: frozenset[str]) -> str:
    if len(labels) != 1:
        raise ValueError(f"pilot rows require exactly one property label, got {labels}")
    return next(iter(labels))


def _exercise_source_kind(exercise: GeneratedExercise) -> str:
    kinds = {seed.kind for seed in exercise.seeds}
    if not kinds:
        return "authored"
    if len(kinds) != 1:
        raise ValueError(
            f"exercise {exercise.id!r} mixes seed source kinds: {sorted(kinds)}"
        )
    return next(iter(kinds))


def _exercise_domain(exercise: GeneratedExercise) -> str:
    domains = {seed.domain for seed in exercise.seeds}
    if not domains:
        return "data"
    if len(domains) != 1:
        raise ValueError(
            f"exercise {exercise.id!r} mixes seed domains: {sorted(domains)}"
        )
    return next(iter(domains))


def _primary_seed_id(links: dict) -> str:
    seed_ids = links["seed_ids"]
    return seed_ids[0] if seed_ids else f"pattern:{links['pattern_id']}"


def build_pipeline(
    *,
    source_rows: list[SourceExerciseCandidate],
    generated: list[GeneratedExercise],
    patterns: list[Pattern],
    approvals: list[PatternApproval],
    benchmark: list[tuple[str, str]],
    sandbox: SandboxBackend,
    out_dir: Path,
    timeout: int = 30,
) -> BuildResult:
    """Render, gate, qualify, dedup, gate contamination, write artifacts."""
    rendered: list[tuple[TaskRecord, str, dict]] = []
    for row in source_rows:
        rendered.append(_render_source(row))
    for exercise in generated:
        # Design gate: missing or stale pattern audit halts the build.
        pattern = _pattern_for(exercise, patterns)
        require_approval(pattern, approvals, pattern_input_fingerprint(pattern))
        rendered.append(_render_generated(exercise, patterns))

    dropped: list[DroppedRow] = []
    kept: list[tuple[TaskRecord, str, dict]] = []

    for task, kind, links in rendered:
        gate = check_imports(task.reference) or check_third_party_names(task.reference)
        if gate:
            dropped.append(
                DroppedRow(
                    stage="local_gate",
                    reason=gate,
                    content=task.to_dict(),
                    links=links,
                )
            )
            continue

        outcome = qualify_task(
            task, policy=TStringPolicy(), sandbox=sandbox, timeout=timeout
        )
        if isinstance(outcome, InfrastructureFailure):
            raise BuildInfrastructureError(
                f"provider infrastructure failed at {outcome.stage}: {outcome.reason}"
            )
        if isinstance(outcome, Qualified):
            kept.append((task, kind, links))
        else:
            dropped.append(
                DroppedRow(
                    stage=_outcome_stage(outcome),
                    reason=getattr(outcome, "reason", type(outcome).__name__),
                    content=task.to_dict(),
                    links=links,
                )
            )

    # Dedup learning-equivalent content while retaining all source/seed links
    # on the retained row's lineage records.
    seen: dict[str, int] = {}
    final: list[tuple[TaskRecord, list[dict]]] = []
    for task, kind, links in kept:
        semantic_id = semantic_content_id(task)
        if semantic_id in seen:
            final[seen[semantic_id]][1].append({"kind": kind, **links})
            dropped.append(
                DroppedRow(
                    stage="dedup",
                    reason="semantic duplicate",
                    content=task.to_dict(),
                    links=links,
                )
            )
        else:
            seen[semantic_id] = len(final)
            final.append((task, [{"kind": kind, **links}]))

    snapshot = DatasetSnapshot.from_tasks(tuple(task for task, _ in final))
    check_contamination(snapshot, benchmark)

    # -- Artifacts --------------------------------------------------------
    lineage = [
        {"row_id": task.id, **links}
        for task, link_records in final
        for links in link_records
    ]
    lineage_text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in lineage)
    sample_rows = tuple(
        SampleRow(
            row_id=task.id,
            source_kind=link_records[0]["source_kind"],
            role=link_records[0]["role"],
            domain=link_records[0]["domain"],
            property=link_records[0]["property"],
            pattern_id=link_records[0]["pattern_id"],
            prompt_family=link_records[0]["prompt_family"],
            seed_id=_primary_seed_id(link_records[0]),
            skeleton=reference_skeleton(task.reference),
            prompt=task.prompt,
            operation=link_records[0]["operation"],
        )
        for task, link_records in final
    )
    sample_rows_text = "".join(
        json.dumps(dataclasses.asdict(row), sort_keys=True) + "\n"
        for row in sample_rows
    )

    seeds = tuple(
        sorted(
            (s for ex in generated for s in ex.seeds),
            key=lambda s: s.id,
        )
    )
    manifest = {
        "provider": {
            "contract_version": DATASET_CONTRACT_VERSION,
            "interpreter": sys.version.split()[0],
        },
        "policy": {"id": "tstring", "version": 1},
        "pattern_input": generation_fingerprint(patterns, seeds),
        "composition_profile": _file_sha256(out_dir.parent / "composition.toml")
        or "none",
        "decisions": _file_sha256(out_dir.parent / "review/decisions.jsonl") or "none",
        "lineage": hashlib.sha256(lineage_text.encode("utf-8")).hexdigest()[:16],
    }

    corpus = dump_snapshot(snapshot)
    dropped_text = "".join(
        json.dumps(
            {
                "stage": d.stage,
                "reason": d.reason,
                "content": d.content,
                "links": d.links,
            },
            sort_keys=True,
        )
        + "\n"
        for d in dropped
    )

    diversity = diversity_report(snapshot)
    build_md = _build_md(snapshot, dropped, manifest, diversity, sample_rows)

    atomic_write_text(out_dir / "corpus/tstrings.jsonl", corpus)
    atomic_write_text(out_dir / "reports/dropped.jsonl", dropped_text)
    atomic_write_text(out_dir / "reports/lineage.jsonl", lineage_text)
    atomic_write_text(out_dir / "reports/pilot-candidates.jsonl", sample_rows_text)
    atomic_write_text(
        out_dir / "reports/manifest.json",
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
    )
    atomic_write_text(out_dir / "reports/build.md", build_md)

    return BuildResult(
        snapshot=snapshot,
        dropped=tuple(dropped),
        lineage=tuple(lineage),
        sample_rows=sample_rows,
        manifest=manifest,
        out_dir=Path(out_dir),
    )


def _build_md(
    snapshot: DatasetSnapshot,
    dropped: list[DroppedRow],
    manifest: dict,
    diversity: dict,
    sample_rows: tuple[SampleRow, ...],
) -> str:
    lines = [
        "# Build report",
        "",
        f"- rows: {snapshot.manifest.task_count}",
        f"- dropped: {len(dropped)}",
        f"- distinct skeletons: {diversity['distinct_skeletons']}",
        f"- distinct prompts: {diversity['distinct_prompts']}",
        f"- pattern-input fingerprint: {manifest['pattern_input'][:12]}",
        "",
        "## Composition",
        "",
    ]
    for dimension in ("source_kind", "role", "property", "domain", "pattern_id"):
        counts = Counter(getattr(row, dimension) for row in sample_rows)
        rendered = ", ".join(
            f"{label}={count}" for label, count in sorted(counts.items())
        )
        lines.append(f"- {dimension}: {rendered}")
    lines.extend(
        [
            "",
        "## Drops",
        "",
        ]
    )
    by_stage: dict[str, int] = {}
    for d in dropped:
        by_stage[d.stage] = by_stage.get(d.stage, 0) + 1
    for stage, count in sorted(by_stage.items()):
        lines.append(f"- {stage}: {count}")
    if not by_stage:
        lines.append("- none")
    return "\n".join(lines) + "\n"
