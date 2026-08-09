"""Spike: evaluate a model on the held-out benchmark.

Uses the provider's verify_candidate as the oracle: the model's candidate
program is executed and semantically compared against the task's reference
observations. Reports pass/fail per task with the rejection stage.

Supports in-process mlx_lm (base + optional adapter) or the oMLX endpoint.
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.contracts import TaskRecord
from satyrn_model.execution.protocol import (
    Accepted,
    ExecutionError,
    NameMissing,
    NameValue,
    NullSandbox,
    Observations,
)
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.verify import VerifyAccepted, verify_candidate
from satyrn_model.policies.tstring import TStringPolicy

_SANDBOX = NullSandbox()


def load_tasks(path: Path = Path("benchmark/tasks.jsonl")) -> list[TaskRecord]:
    tasks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            tasks.append(TaskRecord.from_dict(json.loads(line)))
    return tasks


def materialize_refs(tasks: list[TaskRecord]) -> dict[str, Observations]:
    refs = {}
    for t in tasks:
        out = materialize_reference(t, sandbox=_SANDBOX, timeout=15)
        if not isinstance(out, Accepted):
            raise RuntimeError(
                f"benchmark task {t.id[:12]} failed to materialize: {out}"
            )
        refs[t.id] = out.observations
    return refs


def serialize_observations(observations: Observations) -> list[dict[str, str | None]]:
    """Return reference evidence in a stable JSON form for run artifacts."""
    serialized: list[dict[str, str | None]] = []
    for observation in observations:
        if isinstance(observation, NameValue):
            serialized.append(
                {
                    "kind": "name_value",
                    "name": observation.name,
                    "repr": observation.repr,
                }
            )
        elif isinstance(observation, NameMissing):
            serialized.append(
                {"kind": "name_missing", "name": observation.name, "repr": None}
            )
        elif isinstance(observation, ExecutionError):
            serialized.append(
                {
                    "kind": "execution_error",
                    "name": observation.exception_type,
                    "repr": observation.message,
                }
            )
        else:  # pragma: no cover - Observations is a closed provider union.
            raise TypeError(f"unsupported observation: {observation!r}")
    return serialized


def extract_code(completion: str) -> str:
    """Pull the Python code out of a completion (markdown fences tolerated).

    The Qwen chat model can emit trailing end-token garbage; the candidate
    is the longest suffix-free prefix that compiles.

    Reasoning models emit a ``<think>`` trace before the answer. Left in place
    it is parsed as source and every task fails at ``candidate_parse``, which
    scores the harness rather than the model. An unterminated trace means the
    model never stopped reasoning, so there is no answer to extract.
    """
    if "<think>" in completion:
        closed = re.split(r"</think>", completion, maxsplit=1)
        completion = closed[1] if len(closed) > 1 else ""
    # Cut at the first chat end marker.
    completion = completion.split("<|im_end|>")[0].split("<|endoftext|>")[0]
    blocks = re.findall(r"```(?:python)?\s*\n?(.*?)```", completion, re.DOTALL)
    if blocks:
        completion = blocks[-1].strip()
    # Truncate trailing lines until the whole thing compiles.
    lines = completion.splitlines()
    for cut in range(len(lines), 0, -1):
        candidate = "\n".join(lines[:cut])
        try:
            compile(candidate, "<candidate>", "exec")
            return candidate
        except SyntaxError:
            continue
    return completion.strip()


def answer_name(task: TaskRecord) -> str:
    """The module-level name a task's checks require, defaulting to ``result``.

    Benchmarks built by this spike always used ``result``, and the evaluator's
    system prompt said so verbatim. An independently authored benchmark names
    its answer variable per task, so a hardcoded ``result`` instructed the
    model to define one name while the check looked for another — every arm
    scored zero regardless of ability.
    """
    for check in task.checks:
        name = getattr(check, "name", None)
        if name:
            return name
    return "result"


def eval_candidates(
    tasks: list[TaskRecord],
    refs: dict[str, object],
    generate_fn,
) -> list[dict]:
    """generate_fn(prompt: str, answer_name: str) -> str (completion).

    A single-argument ``generate_fn`` is still accepted for callers predating
    per-task answer names.
    """
    policy = TStringPolicy()
    results = []
    for t in tasks:
        start = time.time()
        try:
            completion = generate_fn(t.prompt, answer_name(t))
        except TypeError:
            completion = generate_fn(t.prompt)
        candidate = extract_code(completion)
        outcome = verify_candidate(
            t,
            candidate,
            ref_observations=refs[t.id],
            policy=policy,
            sandbox=_SANDBOX,
            timeout=15,
        )
        if isinstance(outcome, VerifyAccepted):
            stage, reason, passed = None, None, True
        else:
            stage = getattr(outcome, "stage", type(outcome).__name__)
            reason = getattr(outcome, "reason", "")
            passed = False
        results.append(
            {
                "id": t.id,
                "prompt": t.prompt,
                "reference": t.reference,
                "completion": completion,
                "candidate": candidate,
                "passed": passed,
                "stage": stage,
                "reason": reason,
                "elapsed": round(time.time() - start, 2),
            }
        )
    return results


def score(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    from collections import Counter

    stages = Counter(r["stage"] for r in results if not r["passed"])
    return {
        "total": total,
        "passed": passed,
        "score": round(passed / total, 3) if total else 0.0,
        "failure_stages": dict(stages),
    }
