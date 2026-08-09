"""Build a deployment-aligned pilot that isolates semantic intent wording."""

import argparse
import collections
import json
import sys
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _marginals(rows: list[dict]) -> dict[str, collections.Counter]:
    return {
        dimension: collections.Counter(row[dimension] for row in rows)
        for dimension in (
            "operation",
            "role",
            "source_kind",
            "domain",
            "prompt_family",
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sp5_root", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    root = args.sp5_root.resolve()
    sys.path.insert(0, str(root / "src"))

    from satyrn_model.training import (
        PYTHON_CODE_SYSTEM_PROMPT,
        LineagedTask,
        render_training_handoff,
    )

    from satyrn_model.contracts import TaskRecord, load_snapshot
    from satyrn_model.policies.registry import TrustedPolicyRegistry
    from satyrn_model.policies.tstring import TStringPolicy

    selected = _read_jsonl(root / "reports/pilot.jsonl")
    candidates = _read_jsonl(root / "reports/pilot-candidates.jsonl")
    before = _marginals(selected)
    used = {row["row_id"] for row in selected}
    replacements: list[dict[str, str]] = []
    pattern_for = {"strings": "intro-strings", "values": "intro-values"}

    for operation, pattern_id in pattern_for.items():
        pool = sorted(
            (
                row
                for row in candidates
                if row["operation"] == operation
                and row["role"] == "consumer"
                and row["pattern_id"] == pattern_id
                and row["row_id"] not in used
            ),
            key=lambda row: row["row_id"],
        )
        for index, original in enumerate(selected):
            if original["operation"] != operation or original["role"] != "consumer":
                continue
            match_index = next(
                (
                    candidate_index
                    for candidate_index, candidate in enumerate(pool)
                    if all(
                        candidate[dimension] == original[dimension]
                        for dimension in (
                            "source_kind",
                            "domain",
                            "prompt_family",
                        )
                    )
                ),
                None,
            )
            if match_index is None:
                raise RuntimeError(
                    f"no semantic bridge for {operation} stratum "
                    f"{original['source_kind']}/{original['domain']}/"
                    f"{original['prompt_family']}"
                )
            replacement = pool.pop(match_index)
            used.remove(original["row_id"])
            used.add(replacement["row_id"])
            selected[index] = replacement
            replacements.append(
                {"from": original["row_id"], "to": replacement["row_id"]}
            )

    after = _marginals(selected)
    if before != after:
        raise RuntimeError("semantic bridge changed a protected marginal")
    if len(selected) != 500 or len({row["row_id"] for row in selected}) != 500:
        raise RuntimeError("semantic bridge selection is not 500 unique rows")

    registry = TrustedPolicyRegistry()
    registry.register(TStringPolicy())
    snapshot = load_snapshot(root / "corpus/tstrings.jsonl", registry=registry)
    tasks = {task.id: task for task in snapshot.tasks}
    seed_ids: dict[str, set[str]] = collections.defaultdict(set)
    for record in _read_jsonl(root / "reports/lineage.jsonl"):
        seed_ids[record["row_id"]].update(record.get("seed_ids", ()))
    rows = [
        LineagedTask(
            task=tasks[item["row_id"]],
            seed_ids=tuple(sorted(seed_ids[item["row_id"]]))
            or (f"seed-independent:{item['row_id']}",),
            prompt_family=item["prompt_family"],
        )
        for item in selected
    ]
    benchmark = tuple(
        TaskRecord.from_dict(record)
        for record in _read_jsonl(root / "benchmark/tasks.jsonl")
    )
    handoff = render_training_handoff(
        rows,
        benchmark=benchmark,
        validation_fraction=0.10,
        split_seed=17,
        output_dir=args.destination,
        system_prompt=PYTHON_CODE_SYSTEM_PROMPT,
    )
    (args.destination / "selection.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected)
    )
    probe_manifest = {
        "base_rendered_fingerprint": (
            "a60a5cc4e774cd710af89bf87c94c2ed79493090105d9ce7a1da1de5690d8b5e"
        ),
        "protected_marginals": {
            dimension: dict(sorted(counts.items()))
            for dimension, counts in after.items()
        },
        "rendered_fingerprint": handoff.rendered_fingerprint,
        "replacements": replacements,
        "replacement_count": len(replacements),
    }
    (args.destination / "probe-manifest.json").write_text(
        json.dumps(probe_manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(probe_manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
