# Runbook: the explanatory-content experiment (autonomous session)

Read [PREREGISTRATION.md](PREREGISTRATION.md) section 3 first. The metrics are
fixed there and **must not be renegotiated after seeing results**.

## The experiment

`handoff/curriculum-explained-v1` — 533 train rows, of which 90 (16.9%) are
verified explanatory question/answer rows. Everything else is `repair-v2`
unchanged, so the only difference from the seed baseline is the added prose.

Three seeds, identical recipe to every run being compared against:

```bash
for S in 42 43 44; do
  uv run python spike/train_lora_stratified.py \
    --data handoff/curriculum-explained-v1 \
    --selection handoff/curriculum-explained-v1/selection.jsonl \
    --adapter adapters/m2i-explained-seed$S \
    --model jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit \
    --num-layers 28 --epochs 3 --learning-rate 3e-5 --lr-schedule --seed $S
done
```

Then evaluate each seed on `ood-v2`, with and without docs. `--docs` must be
passed as separate argv words — zsh does not word-split an unquoted variable,
which has silently broken this twice.

Score with `spike/reverify.py` (lenient policy, per pre-registration §1), never
with the raw eval output.

## The comparison

| | baseline (repair-v2) | explained-v1 |
| --- | --- | --- |
| adapter alone, seeds 42/43/44 | 54 / 58 / 48, **spread 10** | ? |
| adapter alone, mean | **53.3** | ? |

- **Primary: does the spread fall from 10?**
- **Secondary: does the mean move from 53.3 toward docs-alone's 76?**
- **Not a metric: adapter + docs.** Registered in advance. Do not promote it.

A mean that rises while the spread stays at 10 is a *weaker* result and must be
reported as one. If the spread does not fall, the hypothesis is wrong — say so
and stop, rather than rebuilding at a different row count until it moves.

## After the numbers exist

1. Write up in `REPAIR_STATUS.md`, commit.
2. **Send to Fable for an honest adversarial review**, including the raw result
   files and the pre-registration. Ask specifically whether the result is an
   artifact, whether the explanatory rows leaked, and whether the metric was
   honoured.
3. **Verify Fable's claims independently before acting on them.** Every round
   so far has held up, but the checking is what makes relaying them honest.
4. Correct whatever it finds, commit the correction, and continue.

## Standing rules for this session

- **Never** author SP5 patterns or write to `patterns/approvals.jsonl`. That
  ledger records human review; writing entries for self-authored patterns
  forges a review that never happened. The explanatory rows are spike-only and
  stay out of the approved corpus.
- Prefer fixing the instrument over collecting more numbers. Three sessions of
  conclusions have died to broken measurement; a fourth is likelier than a real
  effect.
- Any headline gets a paired test and a seed spread before it is written down.
- Record what was *not* run, so a gap never reads as a covered case.

## If time remains

In priority order, stopping when the session ends rather than rushing:

1. **Early-stop at the validation minimum.** Every adapter so far bottoms
   around iteration 80 of ~170 and then drifts up while train loss reaches
   0.000 — all comparisons to date are between overfit checkpoints. Retrain the
   best config from its `0000076_adapters.safetensors` checkpoint equivalent,
   or with `--epochs 2`, and compare.
2. **A second base model.** The deliverable is a *corpus*; "does it help any
   model" is the shippability question, not "does it help this quantization of
   Mellum". Qwen2.5-Coder-7B is already set up and every arm exists for it.
3. Nothing else. Do not start a new experiment thread near the end of the
   session.
