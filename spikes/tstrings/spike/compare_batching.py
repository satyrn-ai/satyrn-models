"""Compare batch orderings structurally, before spending a training run.

Repair step 5 asks for deterministic interleaving over role x capability x
prompt-family windows, compared against ordinary shuffling. The comparison has
two halves, and only one of them is cheap:

* **Structural** — what a batch actually contains. That is what this script
  measures, over the real handoff, for all three orderings.
* **Empirical** — whether interleaving trains a better adapter. That needs
  paired runs and a score on ``benchmark/repair-v1``, and is repair step 6.

Reporting the structural half alone is not evidence that interleaving helps.
It establishes only that the ordering does what it claims, which is the
precondition for the empirical comparison being worth running at all.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np
from train_lora_stratified import (
    BATCHINGS,
    batch_diversity,
    build_batches,
    stratum_of,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def compare(
    data: Path, selection_path: Path, batch_size: int, seeds: tuple[int, ...]
) -> dict:
    train_rows = _read_jsonl(data / "train.jsonl")
    selection = {row["row_id"]: row for row in _read_jsonl(selection_path)}
    missing = [row["task_id"] for row in train_rows if row["task_id"] not in selection]
    if missing:
        raise SystemExit(f"{len(missing)} train rows absent from the selection")

    strata = [stratum_of(selection[row["task_id"]]) for row in train_rows]
    operations = [selection[row["task_id"]]["operation"] for row in train_rows]
    counts = collections.Counter(strata)

    report: dict = {
        "rows": len(train_rows),
        "batch_size": batch_size,
        "distinct_strata": len(counts),
        "smallest_stratum": min(counts.values()),
        "seeds": list(seeds),
        "orderings": {},
    }
    for mode in BATCHINGS:
        per_seed = []
        for seed in seeds:
            batches = build_batches(
                mode,
                strata=strata,
                operations=operations,
                batch_size=batch_size,
                rng=np.random.default_rng(seed),
            )
            covered = collections.Counter(index for batch in batches for index in batch)
            per_seed.append(
                {
                    "seed": seed,
                    "batches": len(batches),
                    "rows_covered": len(covered),
                    "repeated_rows": sum(1 for n in covered.values() if n > 1),
                    **batch_diversity(batches, strata),
                }
            )
        report["orderings"][mode] = per_seed
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path, help="Handoff directory with train.jsonl")
    parser.add_argument("selection", type=Path, help="selection.jsonl for those rows")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    args = parser.parse_args()

    report = compare(args.data, args.selection, args.batch_size, tuple(args.seeds))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
