"""Render the committed SP5 pilot through the provider training contract."""

import json
from collections import defaultdict
from pathlib import Path

from satyrn_model.contracts import TaskRecord, load_snapshot
from satyrn_model.policies.registry import TrustedPolicyRegistry
from satyrn_model.policies.tstring import TStringPolicy
from satyrn_model.training import (
    PYTHON_CODE_SYSTEM_PROMPT,
    LineagedTask,
    render_training_handoff,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = TrustedPolicyRegistry()
    registry.register(TStringPolicy())
    snapshot = load_snapshot(root / "corpus/tstrings.jsonl", registry=registry)
    tasks = {task.id: task for task in snapshot.tasks}
    pilot = [
        json.loads(line)
        for line in (root / "reports/pilot.jsonl").read_text().splitlines()
        if line
    ]
    seed_ids: dict[str, set[str]] = defaultdict(set)
    for line in (root / "reports/lineage.jsonl").read_text().splitlines():
        if line:
            record = json.loads(line)
            seed_ids[record["row_id"]].update(record.get("seed_ids", ()))
    selected_ids = [row["row_id"] for row in pilot]
    prompt_families = {
        row["row_id"]: row.get("prompt_family", "default") for row in pilot
    }
    missing = [task_id for task_id in selected_ids if task_id not in tasks]
    if missing:
        raise RuntimeError(f"pilot references {len(missing)} missing task(s)")
    rows = [
        LineagedTask(
            task=tasks[task_id],
            seed_ids=tuple(sorted(seed_ids[task_id]))
            or (f"seed-independent:{task_id}",),
            prompt_family=prompt_families[task_id],
        )
        for task_id in selected_ids
    ]
    benchmark = tuple(
        TaskRecord.from_dict(json.loads(line))
        for line in (root / "benchmark/tasks.jsonl").read_text().splitlines()
        if line
    )
    handoff = render_training_handoff(
        rows,
        benchmark=benchmark,
        validation_fraction=0.10,
        split_seed=17,
        output_dir=root / "handoff/500-chat",
        system_prompt=PYTHON_CODE_SYSTEM_PROMPT,
    )
    print(
        f"rendered {handoff.train_rows} train / {handoff.validation_rows} "
        f"validation rows at {handoff.rendered_fingerprint[:12]}"
    )


if __name__ == "__main__":
    main()
