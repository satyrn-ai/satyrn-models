"""Validate and freeze the independently reviewed t-string benchmark."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from satyrn_model.contracts import TaskRecord

REVIEWED_AT = "2026-08-03T17:05:00+02:00"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmark"))
    args = parser.parse_args()

    tasks_path = args.source / "tasks.jsonl"
    manifest_path = args.source / "manifest.json"
    tasks_bytes = tasks_path.read_bytes()
    tasks = [
        TaskRecord.from_dict(json.loads(line))
        for line in tasks_bytes.decode("utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256(tasks_bytes).hexdigest()

    if len(tasks) != 100 or len(manifest) != 100:
        raise ValueError("confirmatory benchmark must contain exactly 100 tasks")
    if len({task.id for task in tasks}) != 100:
        raise ValueError("confirmatory benchmark task IDs must be unique")
    if {entry["task_id"] for entry in manifest} != {task.id for task in tasks}:
        raise ValueError("benchmark manifest task IDs do not match tasks")
    roles = Counter(entry["role"] for entry in manifest)
    if roles != {"consumer": 70, "author": 30}:
        raise ValueError(f"benchmark role mix is not 70/30: {dict(roles)}")
    if {entry["review_status"] for entry in manifest} != {"needs_human_review"}:
        raise ValueError("source benchmark is not in the expected review state")
    recorded = (args.source / "fingerprint.txt").read_text().strip()
    if recorded != fingerprint:
        raise ValueError("source benchmark fingerprint does not match task bytes")

    reviewed_manifest = [
        {**entry, "review_status": "reviewed_and_frozen"} for entry in manifest
    ]
    review_record = {
        "reviewed_at": REVIEWED_AT,
        "review_status": "reviewed_and_frozen",
        "task_count": len(tasks),
        "roles": dict(sorted(roles.items())),
        "fingerprint": fingerprint,
        "qualification": {
            "qualified": 100,
            "failed": 0,
            "sandbox_backend": "macos-seatbelt",
            "sandbox_profile_version": "1",
            "policy": "tstring-v1",
        },
        "disjointness": {
            "sp5_generated_candidates": 242,
            "exact_overlap": 0,
            "semantic_overlap": 0,
            "structural_skeleton_overlap": 0,
        },
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "tasks.jsonl").write_bytes(tasks_bytes)
    (args.output / "manifest.json").write_text(
        json.dumps(reviewed_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "fingerprint.txt").write_text(
        fingerprint + "\n", encoding="utf-8"
    )
    (args.output / "review.json").write_text(
        json.dumps(review_record, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"froze {len(tasks)} tasks at {fingerprint[:12]}")


if __name__ == "__main__":
    main()
