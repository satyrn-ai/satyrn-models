# PEP 750 t-string corpus, trained adapter, and evaluation machinery

For project collaborators. **Shipped deliberately with its flaws documented,
because the flaws are the most useful thing in here** — they say where the
corpus needs to go, and they were expensive to find. This bundle includes
the actual trained adapters (`adapters/`), not just prose about them — every
number below is reproducible by loading a real file, not just cited.

Read [SP5_SCALE_BRIEF.md](SP5_SCALE_BRIEF.md) next; it is the actionable part.

---

## Known wrong, or unproven — read this before the numbers

1. **The corpus does not beat documentation-in-prompt.** Adapter alone reaches
   55.8/100 on the independent benchmark; 708 words of PEP 750 in the prompt
   reaches 76. The adapter has **never been shown to add anything on top of
   docs** (p = 0.185 over three seeds, and the one time it looked significant
   that was a harness bug — see below).
2. **Every published comparison is between overfit checkpoints.** Validation
   loss bottoms around iteration 80 of ~170 and then drifts up while training
   loss reaches 0.000. Early stopping was never run.
3. **The documentation comparator contains benchmark-convention coaching.**
   `spike/pep750-docs-context-v3.md` says things like *"If a task asks only for
   the static parts… do not render"*. Fair for internal comparison since every
   arm sees it; **not fair in any external claim without disclosure.**
4. **Single quantization, single harness.** Everything is MLX 8-bit via
   `mlx-lm` pinned at git `254d153f`. `mellum` support is git-main-only; the
   PyPI release raises `Model type mellum not supported`. Unpinning silently
   breaks cross-session comparability — it did, once.
5. **Structural ceiling.** The 5035-row candidate pool collapses onto **270
   distinct program shapes**. Row counts overstate what is there.

Transfer to a second base model was attempted (Qwen2.5-Coder-7B) and
abandoned as capacity-mismatched rather than informative; its adapter
weights were not kept, and it is not part of what this bundle claims. See
`PREREGISTRATION.md` §4 if you need the record of why.

## What is established

On Mellum2-12B-A2.5B-Instruct against `ood-v2`, exact match plus a mechanism
check, scored by `spike/reverify.py`. Every arm below is a real file in
`adapters/` and `results/`, not just a number:

| arm | score |
| --- | --- |
| bare model | **5 / 100** — reaches for t-strings in 7 of 100 |
| + adapter, per seed (`adapters/m2i-runA-{repair-v2,seed43,seed44,seed45,seed46,seed47}`) | 54, 58, 48, 56, 61, 58 — **mean 55.8** |
| + documentation in prompt | **76** |
| + adapter + documentation (3 of the 6 seeds only: `repair-v2`, `seed43`, `seed44`) | 80, 76, 80 — **mean ~78.7** |

**Training a 12B model on a language feature it has never seen works**: 5 → 56
with **zero regressions**, from 443 rows. That is the result worth having,
and `adapters/m2i-runA-*` is the proof — load any of the six and re-score
against `benchmark/ood-v2/tasks.jsonl` with `spike/reverify.py` to confirm.
Each directory ships only the final `adapters.safetensors` + config, not the
intermediate training checkpoints also produced during the run.

The one significant *improvement* found was training-side, not corpus-side:
three epochs with warmup and cosine decay beat one epoch at a constant rate,
60 → 76, **p = 0.0015**, surviving correction across six comparisons.

## What is in here

| path | what it is |
| --- | --- |
| `adapters/m2i-runA-*/` | **The trained result.** Six LoRA adapters (one per seed) for Mellum2-12B-A2.5B-Instruct, the recipe behind the "established" numbers above. Gitignored (multi-GB safetensors don't belong in git history) but present on disk. |
| `results/eval-v2-runA*.json`, `eval-m2i-ood-runA*.json` | The eval-run evidence backing each cell of the table above — tracked despite `results/` being gitignored otherwise, because this is the specific proof, not routine output. |
| `corpus-sft/` | The corpus in the Mellum 2 report's SFT schema (§5.1.1): `messages`, optional `tools`, optional `reasoning`. 443 train / 49 valid. Belongs in their *single-turn coding* category. |
| `benchmark/ood-v2/` | 100 independently authored evaluation tasks, fingerprint `3a94d381b74c`. |
| `OOD_AUTHORING_SPEC.md` | The spec that produced them, including a self-check the author must pass. |
| `SP5_SCALE_BRIEF.md` | Where the corpus needs to grow, with pool numbers. |
| `PREREGISTRATION.md` | Decisions fixed before the analyses they govern. |
| `spike/` | Scoring and benchmark-building. |

### About `ood-v2`

Authored by an agent with **no access to this repository**, to a spec requiring
every task be solvable from its prompt alone. Verified before use: vocabulary
Jaccard 0.071 against the in-distribution benchmark, zero tell-tale phrases
from our prompt conventions, zero reference collisions against training
answers, 100 distinct answer variables, 47 `str` and 53 non-`str` answer types.

It replaced a 25-task predecessor where **23 of 25 tasks required string
literals their prompts never stated** — one asked to render a diagnostic "with
the supplied credentials" and supplied none, while the hidden reference
invented `riley` and `swordfish`. Exact match was grading literal-guessing. The
spec's self-check rejects 24 of those 25 tasks.

## The methodological history, because it is the main lesson

Four successive scoring instruments gave four different verdicts on the same
model completions:

| instrument | verdict |
| --- | --- |
| exact match on `ood-v1` | everything collapses out of distribution |
| "is the answer a `str`" | mis-specified the 6 of 25 tasks answering `tuple`/`dict` |
| type-match against reference | **the bare model wins** — while using a t-string in zero tasks |
| type + mechanism together | only adapter+docs solves anything |

Then on `ood-v2`, a stdout-parsing bug in the oracle produced a p = 0.011
headline that did not survive: candidates calling `print()` were filed as
infrastructure failures, and this hit **7 candidates, all in the untrained
control arm and none in any of six adapter arms** — printing a result is a
habit the fine-tuned models were trained out of. Corrected, p = 0.185.

And a corpus experiment produced, in sequence, a false null, an over-corrected
positive, and a final null — with the instrument sound throughout. The
resolution came from a **content-matched placebo**: 90 rows of verified prose
about dataclasses and pathlib captured +5.3 of a +7.0 apparent gain, leaving
+2.2 for the content actually being about PEP 750.

**The generalisable lesson: a control holding everything constant except the
variable of interest settled in one run what three rounds of statistics could
not.** If you take one thing from this bundle, take that and the placebo
pattern — not the scores.
