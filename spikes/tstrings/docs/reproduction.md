# Reproducing the reference scores

The `reproduce` command re-runs the Cycle 6.1 scorer plus the mlx-lm generator over the
seven tiers — bare base, base + docs in context, and one per LoRA adapter — and
compares each tier's `summary.score` to the inherited targets within ±0.03.

This is a manual, environment-gated procedure: it downloads the ~12B base model, needs
the ~3.2 GB of reference adapters, and runs ~700 greedy generations (100 tasks × 7 tiers)
on Apple Silicon. The scorer + extraction logic itself is unit-tested with a mocked
generator in `tests/test_eval.py`.

## 1. Ensure `.cache/adapters/` is populated

The six reference adapters (`m2i-runA-repair-v2`, `m2i-runA-seed43` … `m2i-runA-seed47`)
are ~3.2 GB and were never committed to the `integration/tstrings-spike` branch — only the
`results/` scores are in history, so there is no `git archive` path for them. Copy them
from the integration spike's local worktree into `.cache/adapters/` (run from
`spikes/tstrings/`):

    cp -R ../../../integration-tstrings-spike/spikes/tstrings/adapters/. .cache/adapters/

Adjust the source to your checkout layout (e.g. a sibling worktree under
`.claude/worktrees/`, or a backup copy of the six `m2i-runA-*` directories).

Verify one directory per adapter, each holding `adapters.safetensors`, `adapter_config.json`,
and `lora-config.yaml`:

    ls .cache/adapters

Only the `m2i-runA-seed*` directories participate in the reproduction; `m2i-runA-repair-v2`
was scored on a different 25-task set and is ignored.

## 2. Run the reproduction

    uv run satyrn-tstrings reproduce --model jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit

The first run downloads the base model (an 8-bit MLX checkpoint) from Hugging Face. It
then scores the 100 benchmark tasks per tier (greedy decode, `max_tokens=700`,
temperature 0) — a long run. The per-tier summary is printed and written to
`reports/reproduction.md`.

## 3. Interpret the ±0.03 result

The command prints one line per tier — `base` (target 0.05), `docs` (target 0.61), and
one per adapter (targets from `results/eval-v2-runA-seed*.json`, 0.47–0.58) — and emits a
`warning:` for any score more than ±0.03 from its target.

- Inside ±0.03: the harness (scorer + generator wiring) agrees with the reference run at
  that tier.
- Outside ±0.03: the reproduced score drifted from the inherited target — investigate
  before training.

**This is a sanity check, not an exact gate.** The inherited `results/` are internally
inconsistent (the prior iteration's successive scoring instruments disagreed on the same
completions), so the comparison validates the *logic* of the instrument — that the three
arms are wired correctly and the extremes (the 0.05 base floor and the 0.61 docs bar)
land where they should — rather than a bit-for-bit match against historical numbers.
