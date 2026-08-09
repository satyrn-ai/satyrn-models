# What SP5 needs to do for scale

Written for the corpus owners after a long run of training-side experiments.
The short version: **training works, and the corpus is now the binding
constraint.** Nothing on the training side is worth doing next.

## What training established

On Mellum2-12B-A2.5B-Instruct, against `benchmark/ood-v2` (100 independently
authored tasks), scored on exact match plus a mechanism check:

| arm | score |
| --- | --- |
| bare model | **5 / 100** (reaches for t-strings in 7 of 100) |
| + LoRA adapter, 6 seeds | **55.8** |
| + documentation in prompt | **76** |
| + adapter + documentation | ~78 |

Training a 12B model on this feature demonstrably works: 5 → 56 with **zero
regressions**, from 443 rows. The model goes from not knowing the feature
exists to solving over half of an independent benchmark.

## Why the corpus is now the constraint

Every corpus-*composition* change we tried returned null. Every training-side
change that worked, worked once and is done.

| intervention | outcome |
| --- | --- |
| training recipe (1 epoch → 3 + LR schedule) | **60 → 76, p = 0.0015** |
| renderer over-exposure fix | null |
| program-shape diversity | null |
| explanatory API content | null once placebo-controlled |

The decisive evidence is the placebo. Adding 90 rows of verified prose about
**dataclasses and pathlib** — nothing to do with t-strings — captured +5.3 of a
+7.0 gain. Only +2.2 was attributable to the content being about PEP 750, and
that did not reach significance across six seeds.

**That is a volume signal, not a quality signal.** Adding rows helps almost
regardless of what is in them, which is what a data-starved regime looks like.
We have been rearranging a shortage.

For scale: the Mellum 2 technical report's own SFT run is ~47B tokens. This
corpus is on the order of 100k. We are five orders of magnitude down and have
spent four experiments tuning composition.

## Where the pool actually runs out

`reports/pilot-candidates.jsonl`: 5035 rows, **51 patterns**, **54 seeds**,
**270 distinct program shapes**.

The row count is misleading. Structure is what the model learns from, and
5035 rows collapse onto 270 shapes — each shape appears ~19 times. A curriculum
of 443 rows already reaches 103 of those 270; the shape ceiling is close.

**Seeds and patterns contribute structural variety at almost the same rate:**

| | count | distinct shapes each contributes |
| --- | --- | --- |
| seeds | 54 | median 15 |
| patterns | 51 | median 14 |

Marginal value is ~5.0 new shapes per seed and ~5.3 per pattern. **Neither
dominates, so grow both** — but see the domain skew below, which makes seeds the
more urgent of the two.

## The three specific gaps

### 1. Domain coverage is badly lopsided, and it is a *seed* problem

Row counts look tolerable. Distinct seeds do not:

| domain | rows | **distinct seeds** |
| --- | --- | --- |
| text | 38.3% | **17** |
| data | 14.0% | **16** |
| html | 15.9% | **7** |
| sql | 15.9% | **7** |
| logging | 9.2% | **4** |
| regex | 6.7% | **3** |

`regex` and `logging` rest on 3 and 4 seeds. Any curriculum honouring the
domain marginals draws those few seeds repeatedly, which is duplication dressed
as coverage. **Priority: bring every domain to at least 12–15 seeds.** That is
roughly 30 new seeds concentrated in regex, logging, sql and html — and it is
the single highest-value item in this document.

SQL and HTML matter disproportionately: escaping and parameterisation are the
motivating use cases for t-strings existing at all, and each currently rests on
seven seeds.

> This table is a historical diagnostic snapshot and is left unmodified. The
> domain floors it calls for have since been partially addressed — see
> `docs/superpowers/specs/2026-08-09-sp5-seed-sourcing-design.md`.

### 2. Extraction is confined to two domains

Only **10 of 54 seeds** supply `extracted` rows, and they cover only `data` and
`text`. So the 20% extracted quota is filled from a narrow slice, and the model
never sees real-world t-string usage in the domains where the feature is most
motivated.

Extracted seeds in `sql`, `html` and `logging` would be worth more than
authored ones — they carry structure nobody on this project would think to
write.

### 3. Two properties are effectively unpopulated

| property | share |
| --- | --- |
| `construct` | **0.2%** (10 rows) |
| `negative` | 5.2% |
| `compose_templates` | 6.0% |

`construct` — assembling a `Template` from `Interpolation` objects by hand —
has ten rows in the entire pool. It is a legitimate and tested part of the API;
`ood-v2` includes such tasks and our scoring had to be widened to accept them.
Ten rows cannot teach it.

## What would change the outcome

In priority order:

1. **~30 new seeds, weighted to regex, logging, sql, html.** Brings every
   domain to a defensible base and roughly doubles the shape ceiling.
2. **Extracted seeds outside `data`/`text`.** Real usage in sql/html/logging.
3. **Populate `construct` and `compose_templates`** to a few percent each.
4. **New patterns only after 1–3.** Patterns multiply what seeds provide; more
   patterns over 54 seeds deepens duplication rather than relieving it.

A corpus at ~150 seeds and ~70 patterns would plausibly reach 800–1000 distinct
shapes against today's 270. That is the regime where composition questions
become worth asking again — and where the training-side experiments we ran
would actually have had room to show an effect.

## What training will do meanwhile

Nothing further on Mellum composition. The two open measurements both need a
bigger corpus to be worth running:

- **Transfer to a second base model.** Attempted on Qwen2.5-Coder-7B and
  abandoned: matching `--num-layers 28` gave Qwen a 7× smaller adapter
  (0.265% trainable against Mellum's 1.171%), so a null would not have
  separated "corpus is Mellum-specific" from "not enough capacity". Worth
  redoing at matched *capacity* once the corpus is larger. One real finding
  survived: the adapter makes Qwen run on — 41 of 100 completions over 1500
  characters, against 0 of 100 bare.
- **Early stopping.** Every adapter so far bottoms out on validation around
  iteration 80 of ~170 and then drifts up. All published comparisons are
  between overfit checkpoints.

## One caveat to carry into any external claim

`spike/pep750-docs-context-v3.md` — the 76-point comparator — contains
benchmark-convention advice ("If a task asks only for the static parts… do not
render"). Fair for internal comparison, since every arm sees it. **Not fair in
an external claim without disclosure.** The same text leaked into one
explanatory training row before being caught.
