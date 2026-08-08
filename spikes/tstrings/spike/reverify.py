"""Re-run the oracle over candidates already on disk, without re-inference.

Every eval run stores the candidate program it extracted, so a change to the
oracle can be applied to past results for the cost of executing them again —
seconds per arm rather than minutes of generation. That matters when the change
is a bug fix, because the alternative is leaving old numbers in place and
comparing them against new ones.

Written for exactly that case: `verify_candidate` parsed the whole of the
collector's stdout as JSON, so any candidate that printed something was filed
as an infrastructure failure. On `ood-v2` that hit 7 candidates, all in the
untrained control arm, deflating the baseline every adapter was measured
against.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.contracts import TaskRecord
from satyrn_model.execution.protocol import Accepted, NullSandbox
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.verify import VerifyAccepted, verify_candidate
from satyrn_model.policies.tstring import TStringPolicy

_SANDBOX = NullSandbox()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument(
        "--write", action="store_true", help="Overwrite the result files in place."
    )
    args = parser.parse_args()

    tasks = {}
    for raw in args.tasks.read_text().splitlines():
        if raw.strip():
            task = TaskRecord.from_dict(json.loads(raw))
            tasks[task.id] = task

    refs = {}
    for task_id, task in tasks.items():
        out = materialize_reference(task, sandbox=_SANDBOX, timeout=20)
        if not isinstance(out, Accepted):
            raise RuntimeError(f"reference {task_id[:12]} failed: {out}")
        refs[task_id] = out.observations

    # Lenient per spike/PREREGISTRATION.md, decided and committed before this
    # was run: a candidate fails only when it builds no Template where the
    # reference builds one.
    policy = TStringPolicy(strict_old_form=False)
    print(f"{'arm':22}{'was':>6}{'now':>6}{'delta':>7}   changed tasks")
    for path in args.results:
        payload = json.loads(path.read_text())
        before = sum(1 for row in payload["results"] if row["passed"])
        flipped = []
        for row in payload["results"]:
            task = tasks[row["id"]]
            outcome = verify_candidate(
                task,
                row["candidate"],
                ref_observations=refs[task.id],
                policy=policy,
                sandbox=_SANDBOX,
                timeout=20,
            )
            passed = isinstance(outcome, VerifyAccepted)
            if passed != row["passed"]:
                flipped.append((row["id"][:8], row["passed"], passed))
            row["passed"] = passed
            row["stage"] = (
                None if passed else getattr(outcome, "stage", type(outcome).__name__)
            )
            row["reason"] = None if passed else getattr(outcome, "reason", "")
        after = sum(1 for row in payload["results"] if row["passed"])
        payload["summary"] = payload.get("summary", {}) | {
            "passed": after,
            "total": len(payload["results"]),
        }
        if args.write:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tag = payload.get("tag", path.stem)
        marks = " ".join(f"{i}{'+' if n else '-'}" for i, _, n in flipped) or "none"
        print(f"{tag:22}{before:>6}{after:>6}{after - before:>+7}   {marks}")


if __name__ == "__main__":
    main()
