"""SP5 authoring CLI — ``authoring coverage`` and ``authoring review seeds``."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from .coverage import analyze_coverage, write_coverage_md


def cmd_coverage() -> None:
    """Run coverage analysis and write ``reports/coverage.md``."""
    # For now, build from available data: seeds/authored.jsonl if it exists.
    seeds_path = Path("seeds/authored.jsonl")
    seeds: list = []
    if seeds_path.exists():
        from .seeds import read_seeds_jsonl

        seeds = read_seeds_jsonl(seeds_path)

    # Extracted candidates would come from the extractor connected to sources.
    # For the collection checkpoint, they are loaded from a persistent store
    # (not yet implemented — coming in Task 5).
    candidates: list = []

    report = analyze_coverage(candidates, seeds)
    out = Path("reports/coverage.md")
    write_coverage_md(report, out)
    print(f"Coverage report written to {out}")


def cmd_review() -> None:
    """Manage seed review decisions (list / add)."""
    from .review import read_decisions

    path = Path("review/decisions.jsonl")
    if not path.exists():
        print("No review decisions yet (review/decisions.jsonl not found).")
        return

    decisions = read_decisions(path)
    for d in decisions:
        print(f"[{d.verdict}] {d.seed_id} — {d.reason}")
    print(f"\n{len(decisions)} decision(s)")


def cmd_audit_pattern(pattern_id: str) -> None:
    """Record approval for one pattern at its current input fingerprint,
    with its blast radius (seeds it consumes)."""
    from .patterns.approvals import audit_pattern
    from .patterns.catalog import CATALOG
    from .seeds import read_seeds_jsonl

    patterns = (
        list(CATALOG)
        if pattern_id == "all"
        else [p for p in CATALOG if p.id == pattern_id]
    )
    if not patterns:
        print(
            f"Unknown pattern {pattern_id!r}; catalog has: "
            f"{', '.join(p.id for p in CATALOG)}"
        )
        sys.exit(1)

    seeds = []
    seeds_path = Path("seeds/authored.jsonl")
    if seeds_path.exists():
        seeds = read_seeds_jsonl(seeds_path)
    from .patterns.registry import pattern_arity

    for pattern in patterns:
        blast_radius = max(0, len(seeds) - pattern_arity(pattern) + 1)
        approval = audit_pattern(
            pattern, Path("patterns/approvals.jsonl"), blast_radius=blast_radius
        )
        print(f"Approved {approval.pattern_id} at {approval.approved_at}")


def cmd_build() -> None:
    """Render, qualify, dedup, and atomically write the corpus + reports.

    Inputs: authored and extracted seeds, review decisions, pattern approvals,
    and a provider-owned benchmark.
    """
    from satyrn_model.execution.protocol import OSProfileSandbox

    from .build import build_pipeline
    from .generate import generate_all
    from .patterns.approvals import read_approvals
    from .patterns.catalog import CATALOG
    from .review import read_decisions, seed_content_sha256
    from .seeds import read_occurrences_jsonl, read_seeds_jsonl
    from .sources import load_sources

    seed_paths = (Path("seeds/authored.jsonl"), Path("seeds/extracted.jsonl"))
    seeds = [
        seed
        for path in seed_paths
        if path.exists()
        for seed in read_seeds_jsonl(path)
    ]
    if not seeds:
        print("No seeds found in seeds/authored.jsonl or seeds/extracted.jsonl.")
        sys.exit(1)

    extracted = [seed for seed in seeds if seed.kind == "extracted"]
    if extracted:
        occurrences_path = Path("seeds/occurrences.jsonl")
        if not occurrences_path.exists():
            print(
                "Extracted seed provenance is unresolved: "
                "seeds/occurrences.jsonl is missing."
            )
            sys.exit(1)
        occurrences = {
            occurrence.id: occurrence
            for occurrence in read_occurrences_jsonl(occurrences_path)
        }
        sources = {source.id: source for source in load_sources(Path("sources.toml"))}
        provenance_errors = []
        for seed in extracted:
            for occurrence_id in seed.occurrence_ids:
                occurrence = occurrences.get(occurrence_id)
                if occurrence is None:
                    provenance_errors.append(f"{seed.id}: missing {occurrence_id}")
                    continue
                source = sources.get(occurrence.origin.source_id)
                if occurrence.seed_id != seed.id:
                    provenance_errors.append(
                        f"{seed.id}: {occurrence_id} points to {occurrence.seed_id}"
                    )
                elif source is None:
                    provenance_errors.append(
                        f"{seed.id}: unknown source {occurrence.origin.source_id}"
                    )
                elif occurrence.origin.license != source.license:
                    provenance_errors.append(
                        f"{seed.id}: license mismatch for {occurrence_id}"
                    )
        if provenance_errors:
            print(
                f"Extracted seed provenance gate failed with "
                f"{len(provenance_errors)} error(s); refusing build."
            )
            sys.exit(1)

    decisions_path = Path("review/decisions.jsonl")
    if not decisions_path.exists():
        print("No seed review decisions; refusing to build an unreviewed corpus.")
        sys.exit(1)
    decisions = {
        decision.seed_id: decision for decision in read_decisions(decisions_path)
    }
    unaccepted = [
        seed.id
        for seed in seeds
        if seed.id not in decisions or decisions[seed.id].verdict != "accepted"
    ]
    stale = [
        seed.id
        for seed in seeds
        if seed.id in decisions
        and (
            seed.id != seed_content_sha256(seed)
            or decisions[seed.id].content_sha256 != seed_content_sha256(seed)
        )
    ]
    if unaccepted or stale:
        print(
            f"Seed review gate failed: {len(unaccepted)} unaccepted, "
            f"{len(stale)} stale content hash(es); refusing build."
        )
        sys.exit(1)

    approvals = []
    approvals_path = Path("patterns/approvals.jsonl")
    if approvals_path.exists():
        approvals = read_approvals(approvals_path)

    generated = generate_all(list(CATALOG), tuple(seeds), approvals)

    bench_path = Path("benchmark/tasks.jsonl")
    if not bench_path.exists():
        print("Provider benchmark missing; refusing build without contamination data.")
        sys.exit(1)
    benchmark: list[tuple[str, str]] = []
    for line in bench_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            benchmark.append((data["prompt"], data["reference"]))
    if not benchmark:
        print("Provider benchmark is empty; refusing build without contamination data.")
        sys.exit(1)

    sandbox = OSProfileSandbox()

    result = build_pipeline(
        source_rows=[],
        generated=generated,
        patterns=list(CATALOG),
        approvals=approvals,
        benchmark=benchmark,
        sandbox=sandbox,
        out_dir=Path("."),
    )
    print(
        f"Build: {result.snapshot.manifest.task_count} rows, "
        f"{len(result.dropped)} dropped"
    )


def cmd_pilot() -> None:
    """Select the pilot from built rows and derive calibration thresholds.

    Writes reports/threshold-derivation.json (machine record) and
    reports/threshold-derivation.md (human derivation). SP5 never selects
    contamination thresholds — the record's semantic-near gate stays None.
    """
    from .composition import (
        capacity_deficits,
        capacity_report,
        load_composition_profile,
        select_composed_pilot,
    )
    from .sampling import (
        SampleRow,
        SamplingPlan,
        derive_calibration,
        write_calibration,
    )

    plan = SamplingPlan.load(Path("sampling.toml"))
    profile = load_composition_profile(Path("composition.toml"))
    profile_version = profile.version
    candidates_path = Path("reports/pilot-candidates.jsonl")
    if not candidates_path.exists():
        print("Pilot candidates missing; run `authoring build` first.")
        sys.exit(1)
    candidates = [
        SampleRow(**json.loads(line))
        for line in candidates_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    capacity_path = Path("reports/pilot-capacity.md")
    capacity_path.write_text(
        capacity_report(candidates, profile, plan.target_rows), encoding="utf-8"
    )
    deficits = capacity_deficits(candidates, profile, plan.target_rows)
    if deficits:
        print(
            f"Pilot capacity gate failed with {len(deficits)} insufficient "
            f"strata; see {capacity_path}."
        )
        sys.exit(1)
    selected = select_composed_pilot(candidates, profile, plan.target_rows)
    if len(selected) != plan.target_rows:
        print(
            f"Pilot requires {plan.target_rows} unique rows; build supplied "
            f"{len(selected)}."
        )
        sys.exit(1)

    calibration = derive_calibration(
        selected,
        profile_version=profile_version,
        target_rows=plan.target_rows,
    )
    write_calibration(calibration, Path("reports/threshold-derivation.json"))
    Path("reports/pilot.jsonl").write_text(
        "".join(
            json.dumps(dataclasses.asdict(row), sort_keys=True) + "\n"
            for row in selected
        ),
        encoding="utf-8",
    )
    Path("reports/threshold-derivation.md").write_text(
        "\n".join(
            (
                "# Pilot threshold derivation",
                "",
                f"- profile version: {profile_version}",
                f"- selected rows: {len(selected)}",
                f"- distinct skeletons: {calibration.diversity['distinct_skeletons']}",
                f"- distinct prompts: {calibration.diversity['distinct_prompts']}",
                f"- review budget: {calibration.review_budget:.0%}",
                "",
            )
        ),
        encoding="utf-8",
    )
    print(f"Pilot selected: {len(selected)} rows; calibration reports written.")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "coverage":
        cmd_coverage()
    elif cmd == "review":
        cmd_review()
    elif cmd == "review-seeds":
        cmd_review()
    elif cmd == "audit-pattern":
        if len(sys.argv) < 3:
            print("Usage: authoring audit-pattern <id>")
            sys.exit(1)
        cmd_audit_pattern(sys.argv[2])
    elif cmd == "build":
        cmd_build()
    elif cmd == "pilot":
        cmd_pilot()
    else:
        print(
            "Usage: authoring "
            "{coverage|review|review-seeds|audit-pattern <id>|build|pilot}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
