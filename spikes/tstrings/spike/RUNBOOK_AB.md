# Runbook: Run A and Run B

Scheduled for 2026-08-06 00:54 local. **Only these two runs and their evals.**
Everything else discussed (multi-seed, the Qwen composition eval, the GRPO
re-probe, repairing `ood-v1` prompts) is explicitly out of scope — do not start
it, even if the runs finish early.

Background and why the earlier experiment was withdrawn:
[SESSION_PLAN_1724.md](SESSION_PLAN_1724.md).

## Design

Two arms differing only in curriculum, so the difference is attributable:

| run | curriculum | rows | renderer-body share |
| --- | --- | --- | --- |
| **A** | `handoff/curriculum-repair-v2` | 443 | 11.5% |
| **B** | `handoff/curriculum-lowbody-v1` | 486 | **6.2%** |

The already-recorded `repair-v2` + old recipe run anchors the recipe change, so
**curriculum effect = B − A**.

**Primary metric: `undefined_renderer` on `ood-v1`, baseline 6** — candidates
calling the corpus's renderer without defining it. Zero on the bare model, so
it is unambiguously trained in. Do **not** use exact match: all 11 of the old
semantic failures need literals the prompts never supply.

## Commands

Train A, then B — sequentially, they contend for the same memory.

```bash
uv run python spike/train_lora_stratified.py \
  --data handoff/curriculum-repair-v2 \
  --selection handoff/curriculum-repair-v2/selection.jsonl \
  --adapter adapters/m2i-runA-repair-v2 \
  --model jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit \
  --num-layers 28 --epochs 3 --learning-rate 3e-5 --lr-schedule --seed 42
```

```bash
uv run python spike/train_lora_stratified.py \
  --data handoff/curriculum-lowbody-v1 \
  --selection handoff/curriculum-lowbody-v1/selection.jsonl \
  --adapter adapters/m2i-runB-lowbody-v1 \
  --model jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit \
  --num-layers 28 --epochs 3 --learning-rate 3e-5 --lr-schedule --seed 42
```

Then four evals — each `ood-v1` run took under a minute on this model:

```bash
for arm in runA-repair-v2 runB-lowbody-v1; do
  for docs in "" "--docs spike/pep750-docs-context-v3.md"; do
    uv run python spike/run_eval.py --backend mlx \
      --model jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit \
      --model-revision mellum2-instruct-8bit --tokenizer-revision mellum2-instruct-8bit \
      --adapter adapters/m2i-$arm --adapter-revision $arm \
      --bench benchmark/ood-v1/tasks.jsonl --max-tokens 700 \
      --tag m2i-ood-$arm$([ -n "$docs" ] && echo "-docs") $docs
  done
done
```

Score with the structural metric, never exact match:

```bash
uv run python spike/rescore_ood.py results/eval-m2i-ood-run*.json --out results/ood-rescore-ab.json
```

## Reporting

Lead with `undefined_renderer` for A and B against the baseline of 6, then the
`rendered` / `unrendered_template` columns. State plainly that this is **single
seed at n=25**, so a difference of a few tasks is not significant against the
10–19 point variance documented elsewhere in this project — multi-seed was
deliberately deferred, not overlooked.

Also carry forward: warmup clamps to 48 at these iteration counts, so this is
**not** the Mellum 2 report's 100-step ramp.

Append results to `REPAIR_STATUS.md` and commit on
`worktree-spike-tstrings-training`.

## If something fails

Training is the only expensive step. If A fails, fix and retry A before
starting B — a B-only result answers nothing, because the recipe changed too.
If both trainings succeed but evals fail, the adapters are on disk and the
evals are cheap to rerun.
