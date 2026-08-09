"""Unattended experiment sequence for the t-string training question.

The repair sequence established that a LoRA at rank 8 over 8 of 28 layers,
one epoch, 443 rows and 150 distinct answer bodies does not beat a page of
documentation in the prompt. It did *not* establish that training cannot work:
across two iterations only the composition of a fixed ~500-row sample and the
batch ordering ever varied. Data volume, epochs, rank, layer count, learning
rate, quantization and seed were all held fixed at their original values.

This script varies them, in an order chosen so that a crash at 3am still
leaves the most valuable results on disk.

Ordering rationale
------------------
1. ``docs-v3`` first — five minutes, and it moves the bar every adapter is
   judged against.
2. **Noise floor** second. There is currently no variance estimate for the
   adapter arm at all, so no later comparison is interpretable without it.
   Running it early means that if the night dies, we at least learn what
   effect size this setup can resolve.
3. **Volume sweep** third: the main hypothesis, and the one lever that is free
   because the approved pool already holds the rows.
4. **Held-out framing**: a validity check on every adapter number, since
   training and benchmark share all three prompt families by design.
5. **Capacity**: only meaningful once there is data to justify it.
6. **bf16 / full fine-tune**: last, because it needs a download and its
   throughput is unknown. The full-tune step is deliberately capped.

Every step is fail-isolated: a step that raises is recorded and the sequence
continues. Every step is skipped if its result artifact already exists, so the
script can be re-run to resume.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SP5 = ROOT.parent / "sp5-corpus-brainstorm"
BENCH = "benchmark/repair-v1/tasks.jsonl"
Q8 = "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit"
Q8_REV = "b292f3cb59a1dea859013fad96af2640ce15ba9e"
BF16 = "mlx-community/Qwen2.5-Coder-7B-Instruct-bf16"
BF16_REV = "3eb9ff2cf5d6384083c82ef04738a0f10765cd38"


@dataclasses.dataclass
class Step:
    """One experiment: build a curriculum, train, evaluate."""

    name: str
    kind: str  # "eval-only" | "train-eval"
    scale: float = 1.0
    seed: int = 42
    epochs: int = 1
    num_layers: int = 8
    rank: int = 8
    model: str = Q8
    model_rev: str = Q8_REV
    docs: str | None = None
    fine_tune_type: str = "lora"
    max_iters: int | None = None
    families: str | None = None  # hold out a prompt family from training
    note: str = ""

    @property
    def result(self) -> Path:
        return ROOT / f"results/eval-{self.name}.json"

    @property
    def adapter(self) -> Path:
        return ROOT / f"adapters/{self.name}"

    @property
    def data(self) -> Path:
        return ROOT / f"handoff/curriculum-{self.name}"


def sh(args: list[str], log: Path, timeout: int) -> None:
    """Run a command, streaming to *log*, raising on failure."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n$ {' '.join(args)}\n")
        stream.flush()
        subprocess.run(
            args,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=timeout,
        )


def build_curriculum(step: Step, log: Path) -> None:
    args = [
        "uv",
        "run",
        "python",
        "spike/build_curriculum.py",
        str(SP5),
        str(step.data),
        "--scale",
        str(step.scale),
    ]
    sh(args, log, timeout=3600)
    if step.families:
        _hold_out_family(step, log)


def _hold_out_family(step: Step, log: Path) -> None:
    """Drop one prompt family from train.jsonl only; the benchmark keeps all.

    This measures how much of an adapter's score is familiarity with wording it
    was trained on, which the curriculum design otherwise makes unmeasurable.
    """
    selection = {
        json.loads(line)["row_id"]: json.loads(line)
        for line in (step.data / "selection.jsonl").read_text().splitlines()
        if line
    }
    path = step.data / "train.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    kept = [
        row
        for row in rows
        if selection[row["task_id"]]["prompt_family"] != step.families
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in kept))
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"held out {step.families}: {len(rows)} -> {len(kept)} rows\n")


def train(step: Step, log: Path) -> None:
    args = [
        "uv",
        "run",
        "python",
        "spike/train_lora_stratified.py",
        "--data",
        str(step.data),
        "--selection",
        str(step.data / "selection.jsonl"),
        "--adapter",
        str(step.adapter),
        "--seed",
        str(step.seed),
        "--epochs",
        str(step.epochs),
        "--batching",
        "interleaved",
        "--model",
        step.model,
        "--num-layers",
        str(step.num_layers),
        "--rank",
        str(step.rank),
        "--fine-tune-type",
        step.fine_tune_type,
    ]
    if step.max_iters:
        args += ["--max-iters", str(step.max_iters)]
    sh(args, log, timeout=8 * 3600)


def evaluate(step: Step, log: Path) -> None:
    args = [
        "uv",
        "run",
        "python",
        "spike/run_eval.py",
        "--model",
        step.model,
        "--model-revision",
        step.model_rev,
        "--tokenizer-revision",
        step.model_rev,
        "--bench",
        BENCH,
        "--tag",
        step.name,
    ]
    if step.kind == "train-eval":
        args += ["--adapter", str(step.adapter), "--adapter-revision", step.name]
    if step.docs:
        args += ["--docs", step.docs]
    sh(args, log, timeout=3 * 3600)


def run(step: Step, logs: Path) -> dict:
    log = logs / f"{step.name}.log"
    started = time.time()
    if step.result.exists():
        return {"step": step.name, "status": "skipped (result exists)"}
    try:
        if step.kind == "train-eval":
            # Resume at training granularity, not just at result granularity.
            # A crash during evaluation would otherwise re-run the curriculum
            # build and the whole training run — tolerable for a 30-minute LoRA
            # arm, expensive for a multi-hour full fine-tune.
            # The sentinel is written only after train() returns cleanly.
            # Checking for adapters.safetensors instead would be wrong: mlx
            # writes it at every --save-every checkpoint, so an interrupted run
            # leaves one behind and resume would silently evaluate a
            # half-trained adapter as though it were finished.
            done = step.adapter / "TRAINED"
            if done.exists():
                with (logs / f"{step.name}.log").open("a", encoding="utf-8") as s:
                    s.write("training already completed; skipping to evaluation\n")
            else:
                build_curriculum(step, log)
                train(step, log)
                done.write_text(f"{step.name}\n")
        evaluate(step, log)
        summary = json.loads(step.result.read_text())["summary"]
        return {
            "step": step.name,
            "status": "ok",
            "passed": summary["passed"],
            "total": summary["total"],
            "score": summary["score"],
            "minutes": round((time.time() - started) / 60, 1),
            "note": step.note,
        }
    except subprocess.TimeoutExpired:
        return {
            "step": step.name,
            "status": "timeout",
            "minutes": round((time.time() - started) / 60, 1),
        }
    except subprocess.CalledProcessError as error:
        tail = log.read_text(errors="ignore")[-600:] if log.exists() else ""
        return {
            "step": step.name,
            "status": f"failed rc={error.returncode}",
            "minutes": round((time.time() - started) / 60, 1),
            "tail": tail,
        }
    except Exception as error:  # noqa: BLE001 - unattended run must not die here
        return {"step": step.name, "status": f"error: {type(error).__name__}: {error}"}


def plan() -> list[Step]:
    steps = [
        Step(
            "docs-v3",
            "eval-only",
            docs="spike/pep750-docs-context-v3.md",
            note="define-before-use instruction; moves the comparison bar",
        ),
    ]
    # The docs arms have no variance estimate at all, and review of docs-v3
    # found that 4 of its 11 gains over docs-v2 were on tasks the added text
    # never mentions — greedy decoding flipping borderline completions on an
    # unrelated prompt perturbation. These two are semantically identical
    # paraphrases of docs-v3, so their spread measures the instrument's own
    # noise. Without it, the bar every adapter is judged against is a single
    # unreplicated sample.
    steps += [
        Step(
            "docs-v3a",
            "eval-only",
            docs="spike/pep750-docs-context-v3a.md",
            note="docs noise floor: paraphrase of v3 (structure prose)",
        ),
        Step(
            "docs-v3b",
            "eval-only",
            docs="spike/pep750-docs-context-v3b.md",
            note="docs noise floor: paraphrase of v3 (API prose)",
        ),
        # Disambiguates the volume sweep. vol8 is ~433 updates over 3462 rows
        # that are largely paraphrase-multiplication of the pool's 54 seeds;
        # vol1 at 8 epochs is ~448 updates over 492 rows. Without this arm, a
        # rise across the sweep cannot be attributed to more distinct data
        # rather than simply more gradient steps.
        Step(
            "vol1-epochs8",
            "train-eval",
            scale=1.0,
            seed=42,
            epochs=8,
            note="same update count as vol8, one eighth the data",
        ),
    ]
    # Noise floor: same config as the completed seed-42 run, different seeds.
    # Note this is training-order and init variance only — build_curriculum is
    # fully deterministic, so all three seeds train on byte-identical data.
    steps += [
        Step(
            f"vol1-seed{seed}",
            "train-eval",
            scale=1.0,
            seed=seed,
            note="noise floor at the reference configuration",
        )
        for seed in (43, 44)
    ]
    # Volume sweep. Stops at scale 8: beyond that patterns saturate their
    # 132-row cap and the domain/role marginals drift past 10pp, which would
    # confound volume with a composition change.
    steps += [
        Step(
            f"vol{int(scale)}-seed42",
            "train-eval",
            scale=scale,
            seed=42,
            note=f"volume sweep x{int(scale)}",
        )
        for scale in (2.0, 4.0, 8.0)
    ]
    steps += [
        Step(
            "holdout-family",
            "train-eval",
            scale=4.0,
            seed=42,
            families="python-program",
            note="train on 2 prompt families, score all 3",
        ),
        Step(
            "cap-rank32",
            "train-eval",
            scale=8.0,
            seed=42,
            rank=32,
            note="capacity: rank 8 -> 32",
        ),
        Step(
            "cap-layers28",
            "train-eval",
            scale=8.0,
            seed=42,
            num_layers=28,
            note="capacity: 8 -> 28 layers",
        ),
        Step(
            "bf16-lora",
            "train-eval",
            scale=8.0,
            seed=42,
            model=BF16,
            model_rev=BF16_REV,
            note="removes the 8-bit training confound",
        ),
        Step(
            "bf16-full",
            "train-eval",
            scale=8.0,
            seed=42,
            model=BF16,
            model_rev=BF16_REV,
            fine_tune_type="full",
            max_iters=300,
            note="full tune of 8 layers (24% of params); bounded probe",
        ),
        # Last on purpose. Measured at 8 layers: 1.86B trainable, 29.5GB peak.
        # All 28 layers is roughly 6.5B trainable and an estimated 60-65GB,
        # which fits 128GB but is the least certain step of the night. If it
        # fails it costs nothing, because everything else has already run.
        Step(
            "bf16-full-deep",
            "train-eval",
            scale=8.0,
            seed=42,
            model=BF16,
            model_rev=BF16_REV,
            fine_tune_type="full",
            num_layers=28,
            max_iters=200,
            note="full tune of all 28 layers; the hard thing",
        ),
    ]
    return steps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", type=Path, default=ROOT / "results/overnight")
    parser.add_argument("--only", nargs="*", help="Run only these step names.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.logs.mkdir(parents=True, exist_ok=True)

    steps = plan()
    if args.only:
        steps = [s for s in steps if s.name in set(args.only)]
    if args.dry_run:
        for step in steps:
            print(
                f"{step.name:18} {step.kind:11} scale={step.scale:<5} "
                f"seed={step.seed} rank={step.rank} layers={step.num_layers} "
                f"{step.fine_tune_type:5} {step.note}"
            )
        return

    results: list[dict] = []
    summary_path = args.logs / "summary.json"
    for step in steps:
        outcome = run(step, args.logs)
        results.append(outcome)
        summary_path.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(outcome), flush=True)
    print("\n=== overnight summary ===")
    for outcome in results:
        score = outcome.get("score")
        shown = (
            f"{outcome['passed']}/{outcome['total']} ({score:.1%})"
            if score is not None
            else outcome["status"]
        )
        print(f"  {outcome['step']:18} {shown:22} {outcome.get('note', '')}")


if __name__ == "__main__":
    sys.exit(main())
