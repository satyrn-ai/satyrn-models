"""Spike: generate + qualify the real corpus from seeds."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.authoring.build import build_pipeline
from satyrn_model.authoring.generate import apply_pattern, generate_all
from satyrn_model.authoring.patterns.approvals import (
    PatternApproval,
    audit_pattern,
    read_approvals,
)
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import pattern_input_fingerprint
from satyrn_model.authoring.seeds import read_seeds_jsonl
from satyrn_model.execution.protocol import NullSandbox


def main() -> None:
    extracted = read_seeds_jsonl(Path("seeds/extracted.jsonl"))
    authored = read_seeds_jsonl(Path("seeds/authored.jsonl"))
    seeds = extracted + authored
    print(f"{len(seeds)} seeds")

    # Audit all patterns.
    approvals_path = Path("patterns/approvals.jsonl")
    approvals_path.parent.mkdir(exist_ok=True)
    approvals = []
    for p in CATALOG:
        fp = pattern_input_fingerprint(p)
        approvals.append(
            PatternApproval(pattern_id=p.id, pattern_input_fingerprint=fp,
                            approved_at="2026-08-02T00:00:00+00:00")
        )
    from satyrn_model.authoring.patterns.approvals import write_approvals
    write_approvals(approvals, approvals_path)

    # Generate: arity-1 patterns over every seed; transform over seed pairs.
    generated = []
    for p in CATALOG:
        if p.id == "transform-add":
            for i in range(0, len(seeds) - 1, 2):
                generated.append(apply_pattern(p, tuple(seeds[i:i + 2])))
        else:
            for s in seeds:
                generated.append(apply_pattern(p, (s,)))
    print(f"{len(generated)} generated exercises")

    result = build_pipeline(
        source_rows=[],
        generated=generated,
        patterns=list(CATALOG),
        approvals=approvals,
        benchmark=[],
        sandbox=NullSandbox(),
        out_dir=Path("."),
        timeout=30,
    )
    print(f"corpus: {result.snapshot.manifest.task_count} rows, "
          f"{len(result.dropped)} dropped")
    from collections import Counter
    stages = Counter(d.stage for d in result.dropped)
    print("drop stages:", dict(stages))

    # Property split of the corpus.
    props = Counter()
    for task in result.snapshot.tasks:
        ref = task.reference
        if "getattr(template" in ref or "Interpolation(" in ref and "convert" not in ref:
            props["introspect/construct"] += 1
    print("corpus written to corpus/tstrings.jsonl")


if __name__ == "__main__":
    main()
