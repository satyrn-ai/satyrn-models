# Mellum 2 technical report: what it fixes in our methodology

Source: *Mellum 2 Technical Report*, v1.0, May 2026 — [arXiv:2605.31268](https://arxiv.org/abs/2605.31268).

Read after the report, not before it: several conclusions in
[REPAIR_STATUS.md](REPAIR_STATUS.md) and [MELLUM_ISSUES.md](MELLUM_ISSUES.md)
were formed without it and are corrected here.

## The published decoding protocol

> All benchmarks run at 0.0 temperature, except for BFCL at 0.01 and
> LiveCodeBench at 0.2. All models use greedy decoding.

No pass@k anywhere in the post-training suite; coding scores are pass@1.

This **matches our harness**, which the team's informal guidance had led me to
treat as wrong. Their advice — temperature in [0.5, 1], pass@k, a forced
`</think>` at budget exhaustion — describes what they intend to move to and
described as "on the eval backlog", not the protocol the report ran. Our
temperature-0 greedy pass@1 numbers are therefore directly comparable to the
report's tables. Retaining T=0 is the right default until the team's backlog
lands; there is nothing to change in `run_eval.py` on this axis.

**Scope of the earlier retraction.** The token-budget critique still stands,
but it only ever touched *thinking* generations. On released Instruct our probe
measured clean-stop 1.00, 0/10 unterminated `<think>`, 0/10 repetition, mean
output 634 chars — the 1500-token cap was never within an order of magnitude of
binding. **Every Mellum number we currently hold is an Instruct number and is
unaffected.** The retraction applies to the 2.1 step-200 and released-Thinking
measurements only.

## Our task shape sits in the model's strongest regime

The report separates the three coding benchmarks by ability, and our benchmarks
land squarely on one of them:

| benchmark | ability probed | Mellum 2-RL Instruct | best baseline |
| --- | --- | --- | --- |
| **EvalPlus** (HumanEval+/MBPP+) | robust **function-level synthesis** | **78.4** | Qwen3.5-9B 71.8, Seed-Coder-8B 73.8 |
| LiveCodeBench v6 | multi-step algorithmic reasoning | 37.2 | Qwen3.5-9B 63.7 |
| MultiPL-E (7 langs) | cross-lingual breadth | 67.1 | Seed-Coder-8B 77.0 |

`repair-v1` and `ood-v1` are function-level synthesis — EvalPlus territory,
where the report says "this is the regime our pre-training mix targets
directly" and where Mellum leads its whole comparison panel. Two consequences:

- **Building on Instruct rather than Thinking was correct for our task shape**,
  and now has a published justification rather than a convenience argument. The
  thinking variant's advantage is concentrated in algorithmic reasoning
  (LiveCodeBench 37.2 → 75.1), which our tasks do not exercise.
- We are not fighting a weakness of the model. A poor score on our benchmarks
  cannot be explained away as "wrong regime".

## The knowledge gap is the model's known weak axis

> weakest on broad world knowledge

MMLU-Redux 78.1 against Qwen3.5-9B's 91.1; GPQA Diamond likewise mid-pack. A
post-cutoff language feature is exactly this kind of knowledge, which is
consistent with 0/84 bare on `repair-v1` and with each checkpoint confabulating
a *different* wrong PEP 750 API.

This is the strongest argument yet that the work is worth doing on this target:
the deficiency our corpus addresses is on the axis the report itself names as
the model's weakest, and it is an axis a 2.5B-active MoE cannot brute-force
with scale.

**The report describes no method for teaching post-cutoff APIs or libraries.**
Nothing in the SFT or RLVR sections covers acquiring new language surface after
pre-training. That is a genuine gap rather than a solved problem we are
duplicating.

## The delivery format for training data

Every SFT example is stored in a unified schema:

- `messages` — role/content turns
- `tools` — optional, function-call signatures
- `reasoning` — optional, chain-of-thought for the final assistant turn
  (populated for the Thinking variant, **discarded for Instruct**)

Our curriculum rows are flat prompt/completion pairs. If the corpus is to be
handed over, it should be emitted in this schema. Our data belongs in their
**single-turn coding** category — their *agentic coding* split is long-horizon
repository-edit trajectories, which is not what we generate.

Their own SFT runs three epochs at peak LR 3e-5 decaying cosine to 3e-6. Our
Mellum LoRA has had one epoch at 2e-5, one seed. Not directly comparable
(LoRA vs full SFT), but it confirms one epoch is below their own practice.

## Corrections this forces on earlier write-ups

1. "Mellum 2's use case is IDE completion, so docs-in-context may be
   unavailable" — **wrong**. The report lists "agentic coding, tool use and
   function calling, conversational programming assistance". Context is
   available. The surviving argument for training is coverage, not
   availability: you cannot preload docs for every feature an agentic session
   might touch.
2. "Our T=0 evaluation was methodologically wrong" — **overstated**. It is the
   report's own protocol. Only the thinking-budget half of that critique holds.
