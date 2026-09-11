# Preregistration — t-strings fine-tuning experiment

Frozen **before any training run**. This document is the decision contract; it
must not be edited after the first training run without re-registering.

## Hypothesis

Fine-tuning `jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit` on the t-strings
SFT corpus teaches t-strings (PEP 750) beyond what documentation-in-context
alone provides.

## Arms

| Arm | Definition |
|---|---|
| `base` | The untrained base model, no context |
| `docs` | The base model with the PEP 750 documentation block in context (**the comparator / bar**) |
| `adapter` | The base model + a trained LoRA adapter (5 seeds) |

## Metric

`summary.score` — the fraction of the 100-task `benchmark/ood-v2` benchmark on
which the completion is **correct** (passes the `name_equals` check) **and**
**mechanism** (its AST contains a `TemplateStr`), as computed by the Phase 6
harness. Correctness alone is never reported.

## Seeds

**5** training seeds (1–5). A single-seed number is not a result.

## Decision rule

The result is **POSITIVE** if and only if the **mean** `summary.score` of the
5 adapter arms exceeds the `docs` arm's `summary.score` **measured by the same
harness in the same run**. Otherwise the result is **NEGATIVE**, and it is
reported as such, plainly.

## Notes (fixed, not adjustable post hoc)

- **The bar is this harness's `docs` score, not the historical 0.61.** The 0.61
  is a Phase 6 reproduction target for validating the instrument; comparing an
  adapter to a comparator scored by a different instrument would reintroduce
  the measured instrument-mismatch error. Both the `docs` arm and the adapter
  arms are scored by the same harness in the same run.
- **The corpus is small** (16 training rows; mock `trace` field pending a live
  `DEEPSEEK_API_KEY` re-freeze). Power is limited to large effects (BRIEF §8/§9).
- A negative result is a valid outcome and will be reported as clearly as a
  positive one.
