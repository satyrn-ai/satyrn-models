# Live Phase 7 training and evaluation procedure

The Phase 7 code is unit-tested with a mocked `mlx_lm`; the live run is
environment-gated (requires the base model downloaded and hours of compute).
This document is the exact procedure to satisfy the Phase 7 acceptance
(`PREREGISTRATION.md` committed first — done; ≥5 adapters; `REPORT.md` with a
decision-rule verdict).

## 1. Prerequisites

- Apple Silicon (MLX). `uv sync` from `spikes/tstrings/` (installs the pinned
  `mlx-lm`).
- The base model cache: first training/generation downloads
  `jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit` (~12 GB 8-bit).
- The adapters were **never committed** to the integration branch, so provision
  them from the local worktree:
  ```sh
  mkdir -p .cache/adapters
  cp -R ../../integration-tstrings-spike/spikes/tstrings/adapters/m2i-runA-* .cache/adapters/
  ```

## 2. Train (5 seeds)

```sh
for seed in 1 2 3 4 5; do
  uv run satyrn-tstrings train -i corpus-sft/train.jsonl -o adapters --seed "$seed" --iters 200
done
```

Each run produces `adapters/seed<N>/adapters.safetensors`.

## 3. Evaluate all arms

```sh
uv run satyrn-tstrings reproduce -o reports
```

This scores the bare base, the docs-in-context arm, and the reference adapters.
For the trained adapters, use `evaluate_arms` (or a future `eval` command) over
`adapters/seed1..5` and write `REPORT.md` via `write_report`.

## 4. Interpret

`REPORT.md` states the verdict line: `decision rule met — POSITIVE` iff the
adapter mean `summary.score` exceeds the docs arm's score in the same run;
otherwise `decision rule not met — NEGATIVE`, reported plainly.

## Caveats

- The corpus is small (16 train rows, mock `trace`). Power is limited to large
  effects. A negative result is a valid outcome.
- The bar is this harness's docs score, not the historical 0.61 (that is a
  Phase 6 reproduction target, not the Phase 7 bar).
