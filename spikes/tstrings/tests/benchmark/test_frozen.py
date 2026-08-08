import hashlib
import json
from collections import Counter
from pathlib import Path

from satyrn_model.contracts import TaskRecord

BENCHMARK_DIR = Path(__file__).parents[2] / "benchmark"


def test_frozen_benchmark_matches_review_record() -> None:
    tasks_bytes = (BENCHMARK_DIR / "tasks.jsonl").read_bytes()
    tasks = [
        TaskRecord.from_dict(json.loads(line))
        for line in tasks_bytes.decode("utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(
        (BENCHMARK_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    review = json.loads(
        (BENCHMARK_DIR / "review.json").read_text(encoding="utf-8")
    )
    fingerprint = hashlib.sha256(tasks_bytes).hexdigest()

    assert len(tasks) == 100
    assert len({task.id for task in tasks}) == 100
    assert {entry["task_id"] for entry in manifest} == {
        task.id for task in tasks
    }
    assert Counter(entry["role"] for entry in manifest) == {
        "consumer": 70,
        "author": 30,
    }
    assert {entry["review_status"] for entry in manifest} == {
        "reviewed_and_frozen"
    }
    assert review["qualification"] == {
        "failed": 0,
        "policy": "tstring-v1",
        "qualified": 100,
        "sandbox_backend": "macos-seatbelt",
        "sandbox_profile_version": "1",
    }
    assert review["disjointness"] == {
        "exact_overlap": 0,
        "semantic_overlap": 0,
        "sp5_generated_candidates": 242,
        "structural_skeleton_overlap": 0,
    }
    assert review["fingerprint"] == fingerprint
    assert (BENCHMARK_DIR / "fingerprint.txt").read_text().strip() == fingerprint
