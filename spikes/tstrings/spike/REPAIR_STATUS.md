# Repair status

Tracks the six-step sequence in [STRATIFIED_BATCHING_REVIEW.md](STRATIFIED_BATCHING_REVIEW.md).
All six steps have been executed. Steps 1, 2, 3 and 5 are done; step 4 is half
done and half blocked on human pattern review; step 5 is structurally done but
not empirically compared. Step 6 ran one seed and the promotion gate FAILED
(4 of 7 capabilities), so there is no three-seed ladder and no promotable
adapter.

**The conclusion then moved twice.** Read the sections in order; the earlier
ones record what was believed at the time and are corrected later rather than
rewritten.

1. *Control experiments* (after the sequence): documentation in the prompt beat
   every adapter. ~290 words of API-surface prose scored 77.4% against the
   adapter's 45.2%, and a second informed curriculum iteration moved the
   adapter by one task at p = 1.0. The recommendation at that point was to stop
   the fine-tuning arm.
2. *Overnight sweep*: *that was wrong, and the reason was undertraining.* Every
   run to that point used 56 updates over 0.076% of the parameters. Given all
   28 layers, the same pipeline reaches **70/84** against a documentation bar
   of 76 +/- 2. Independent review then showed the accompanying statistics were
   inflated — the benchmark's near-clone twins are 42/42 concordant, so
   effective n is 42, not 84, and only the capacity result survives correction.
3. *Out-of-distribution check*: on 25 tasks written by an author with no access
   to this repository, **every arm collapses to the floor** — documentation
   0/25, best adapter 0/25, bare base model 1/25. Neither approach transfers.
   This invalidates the premise of the docs-versus-training comparison rather
   than settling it.

4. *Mellum2, the actual target, measured.* Qwen2.5-Coder-7B is proxy work —
   nobody will ship it. Mellum2 is the model the work is meant to improve.
   Released Instruct terminates cleanly (1.00 clean-stop rate against the
   preview snapshot's ~0.5), `mlx_lm.lora` trains its MoE without modification,
   and it scores 0/84 bare, 59/84 with documentation. Crucially, **it also
   scores 1/25 on the independent tasks** — so the out-of-distribution floor
   was never a Qwen weakness. Across six model/condition combinations only
   **2 of 25** tasks were solved by anything.

The live recommendation is neither "ship docs" nor "ship an adapter". The
adapters failed because they memorized a distribution generated from 54 seeds;
`ood-v1` is too hard to rank anything; and Mellum2 has a clean, reproducible
knowledge gap — it confabulates a `t_string` type with `.value` and
`.format_args`. That gap, in a model whose team will accept training data, is
the actual opportunity. See "Remaining".

## Scope decision

Roles stay tied to capability, as in the superseded benchmark: the consumer
capabilities remain consumer tasks and the three typed families remain author
tasks. Only framing was decoupled, and the missing capability cells were added.
Crossing every capability with both roles was considered and rejected as more
benchmark than the repair needs.

## Step 1 — fresh benchmark: done

`spike/build_benchmark_v2.py` writes `benchmark/repair-v1/`.

- 14 capabilities x 3 framings x 2 fresh constants = 84 tasks, 66 consumer and
  18 author.
- Framing is an explicit axis. The superseded builder used
  `FRAMINGS[index % 3]` while emitting tasks in a fixed per-iteration order, so
  operation position was congruent modulo three. **Nine of its eleven
  operations** were pinned to one wording; `render_dynamic_format_spec` and
  `render_conversion_format` were not, because their loops emit one task per
  index. An earlier draft of this file claimed the lock was universal — it was
  not. Capability and framing are now independent by construction: all 42
  capability x framing cells hold exactly two tasks.
- Capabilities cover each of the four interpolation fields, `.strings`,
  `.values`, static joining, basic/dynamic/conversion rendering, composition,
  and all three typed template-function families — the coverage the review
  found missing.
- Every reference is distinct. That is weaker than it sounds: within a
  capability the six tasks are the same program with a different embedded
  token, so `repair-v1` removes the framing confound but **not** the brief's
  near-identical-variant criticism. n=6 per capability is a coarse gate, not
  evidence of reliable breadth, and 84 changed tasks make any numeric
  comparison against the old 36/100 meaningless. Both baselines were therefore
  re-run on `repair-v1` before step 6 — see that section.
- Every reference program is proven executable through `materialize_reference`.
- Contamination checked against the superseded confirmatory benchmark, the
  450-row training split, and the full corpus: zero reference overlap in all
  three. `spike/build_train_data.py` now covers `repair-v1` and raises on a
  missing benchmark file rather than skipping it — `benchmark/` is gitignored,
  so absence is the fresh-checkout default and skipping was fail-open. The
  check is still exact-string only; re-tokenized near-clones would pass it.
- Fingerprint:
  `3a0bb0103cc7906b2821ea086ff9eedac692a230548f7c58aab7e892d7055f4d`

`benchmark/` is gitignored, so the artifact is reproduced by running the
builder; the fingerprint above is the tracked record of it.

**Still required:** the manifest marks every task `needs_human_review`. The
task list is not frozen until an independent reviewer approves it.

The superseded `benchmark/development/` and `benchmark/confirmatory/` builders
are untouched and remain valid historical evidence.

## Step 2 — trainer: done

`spike/train_lora_stratified.py`.

- `_batch_indices` looped `while sum(...) >= batch_size`, so 450 rows at batch
  size 8 produced 56 batches covering 448 rows. Because buckets were reshuffled
  per epoch, a *different* pair of rows was withheld from every epoch. It now
  partitions every row and pads only the final short batch back to
  `batch_size` from rows already drawn in that epoch: 57 batches, all 450 rows
  covered, 6 recorded repeats.
- Length is expressed in whole epochs. `--epochs` replaces `--iters`, and iters
  is derived as `ceil(rows / batch_size) * epochs`. The reviewed run's 57
  updates were the first batch of a second epoch; 57 is now exactly one epoch.
- `batch-manifest.json` records the row ID, operation, and epoch of every row
  in every batch, not just per-batch operation names.
- `--save-every` defaults to 19, so a one-epoch run leaves intermediate
  checkpoints for generated evaluation. It was 200 against 57 iters, which
  wrote none.

`spike/run_eval.py` now also breaks results down by `capability` and `framing`
when the manifest carries them, which is what makes the framing effect
separable from the capability effect. Older manifests without those keys are
summarized as before.

## Verification

- `tests/test_spike_repair.py`: 16 tests covering framing/capability crossing,
  constant freshness, reference executability, full row coverage per epoch and
  across three consecutive epochs, and — for step 5 — row coverage and
  determinism under all three orderings, the never-repeat-a-stratum guarantee,
  strata spanned versus shuffling, single-role batches confined to the epoch
  tail, and refusal of an unknown ordering.
- `tests/test_spike_curriculum.py`: 12 tests covering exact cell fill, per-cell
  prompt-family balance, shared contrast seed sets, seed-diversity floors,
  refusal of unapproved patterns, fail-closed on an unfillable cell, and —
  against the real pool — the corrected role x capability counts, the absence
  of unsampled patterns, and the enforceable marginals staying on profile.
- The contrast-sharing test was rewritten after review showed the original
  passed with the sharing mechanism removed. Its fixture now gives group
  members overlapping-but-unequal seed universes; with equal universes,
  sharing and per-pattern prefix-taking produce identical output and *no*
  assertion can distinguish them. Re-verified by sabotaging
  `Allocator.contrast_seeds` and confirming the test fails.
- Both the benchmark and the curriculum rebuild byte-identically across runs,
  and all three batch orderings are deterministic given a seed.
- Full suite: 189 passed, 6 skipped. Ruff clean on every touched file.
- The runtime wiring is no longer untested: step 6 trained an adapter through
  the `iterate_batches` monkeypatch and `batch-manifest.json` confirms the
  interleaved ordering held under real training.
- One integration defect surfaced only when the eval was first run against
  `repair-v1`: `--limit` truncates the task list but not the manifest, so the
  strict ID check in `summarize_by_benchmark_metadata` raised. The manifest is
  now narrowed to scored tasks when a limit is set, and left strict otherwise.

## Step 3 — curriculum cells: done

`spike/build_curriculum.py` writes `handoff/curriculum-repair-v1/`.

The root cause is narrower than "the curriculum is skewed". The SP5 selector
enforces marginals over property, operation, source kind, role, and domain —
all of them *global*. Nothing constrained the role x capability cell, so the
12% `strings` quota was satisfied almost entirely from
`contrast-author-strings`. **Twenty approved patterns were sampled zero times.**
Fifteen have 132 rows each and cover most of what the adapter failed; the other
five are `construct-*` patterns with one row apiece, and construct was not a
failure mode. The fifteen:

- `intro-interpolations`, `intro-expressions`, `intro-conversions`,
  `intro-format-specs` — every interpolation-field capability, absent entirely.
- `author-static-parts`, `author-values`, `author-render-template`,
  `author-render-explicit-function` — the typed authoring families. The adapter
  was trained on `contrast-author-*` select-the-result prompts instead, which
  is why it emits the canonical renderer only occasionally.
- `render-template`, `render-template-explicit-function` — plain rendering,
  which is why basic rendering fell back to `"".join(template)`.
- `contrast-strings`, `contrast-values` — the consumer half of the contrast.

Note what this does *not* explain: the largest failure buckets, 17 import and
13 attribute errors, occurred on tasks whose sibling patterns were trained
heavily. Zero-sampling accounts for the interpolation-field and plain-rendering
failures, not the API hallucinations. See
[API_CONTRAST_PATTERNS.md](API_CONTRAST_PATTERNS.md).

The new selector names the cells rather than inferring them. Each cell draws a
fixed count from named patterns and is filled as `k` seeds x 3 prompt families,
so capability and framing stay independent in training as they now are in the
benchmark.

Result: 504 rows, 354 consumer / 150 author, prompt families 172 / 166 / 166.
The 6-row `construct` cell is the only family-imbalanced one, because those
rows exist in a single family each; it is a mandatory stratum in
`composition.toml`.

### Marginals and content diversity

The first cut of this selector fixed the capability cells and quietly broke
almost everything else, because `coverage()` reported only the dimensions the
*old* selector got wrong. Two defects, both found in review:

- **Seed collapse.** Every pattern's seeds were ordered identically and each
  cell took `seeds[:wanted]`, so all cells drew the same leading seeds: 504
  rows on **12 distinct seeds, five of them supplying 89%** of the curriculum.
  That reproduced, worse, the near-identical-variant problem the brief raised
  about the benchmark. Selection is now greedy on most-owed stratum first with
  least-used seed as tie-break: **48 distinct seeds, top five 22.6%**, against
  the old curriculum's 49 and 22.6%.
- **Broken marginals.** Domain ran to 9.5% sql and 9.5% text against 20%
  targets. Now every enforceable marginal is within ~2pp:

| marginal | result | target |
| --- | --- | --- |
| role | 70.2 / 29.8 | 70 / 30 |
| source kind | 80.4 authored / 19.6 extracted | 80 / 20 |
| domain | sql 17.9, html 19.6, text 21.4, logging 15.5, data 15.5, regex 10.1 | 20 / 20 / 20 / 15 / 15 / 10 |

`property` and `operation` remain **deliberately** off profile v5, and
`coverage()` now says so explicitly rather than omitting them. Profile v5 puts
45% of rows in `render_subskill` and 43% in `select_result`; that is the
curriculum that scored 36/100 while sampling zero interpolation-field and zero
typed-authoring rows. SP5 should ratify a profile v6 rather than treat this as
conformant.

| cell | old 500 | new 504 |
| --- | --- | --- |
| consumer / author `strings` | 11 / 49 | 36 / 30 |
| consumer / author `values` | 14 / 46 | 36 / 30 |
| consumer / author `render_template` | 18 / 42 | 54 / 51 |
| consumer / author `interpolations` | 0 / 0 | 72 / 27 |

Rendered to a chat handoff through SP5's own `render_training_handoff`:
454 train / 50 validation rows, fingerprint `f330cf7c1b8aa797…`, contamination
checked against `benchmark/repair-v1`. 454 rows is 57 batches at batch size 8,
which the repaired trainer covers as exactly one epoch.

Every selected row comes from the approved candidate pool, and every pattern is
checked against `patterns/approvals.jsonl`. Nothing is hand-authored — see the
retired-augmentation note in `build_train_data.py`.

## Step 4 — paired contrasts: half done

**Done.** The capability contrasts — return the tuple, join only the static
strings, fully render — are selected on a shared seed set per contrast group,
so the same template appears under each instruction and the contrast is carried
by the wording rather than by a different example. In the rendered training
split, single seeds appear under as many as nine distinct contrast
instructions.

**Blocked.** Negative examples for the hallucinated APIs cannot be built from
the approved pool: no pattern names a wrong API, and the only negatives teach
f-string output. Authoring the patterns *and* writing their approval records
would forge a human review, so the proposal is written up for the SP5 owner in
[API_CONTRAST_PATTERNS.md](API_CONTRAST_PATTERNS.md) instead. Until those are
reviewed and the pool is regenerated, an adapter trained on this curriculum
should still be expected to produce `ImportError` on `.strings` tasks even
when it routes intent correctly — that was 17 of the failures.

## Step 5 — deterministic interleaving: structurally done, empirically not

`spike/train_lora_stratified.py` now offers three orderings behind
`--batching`, all of which cover every row exactly once per epoch:

- `interleaved` (default) — builds each batch to span distinct role x
  capability x prompt-family strata while holding the global role share.
- `shuffled` — an ordinary permutation, the comparison baseline.
- `operation` — the superseded eight-distinct-operations ordering, retained so
  the reviewed run stays reproducible.

`spike/compare_batching.py` reports the structural comparison over the real
handoff. Averaged across seeds 42/43/44 on 454 rows spanning 70 strata:

| ordering | mean strata per batch | min | single-role batches |
| --- | --- | --- | --- |
| interleaved | **8.000** | **8** | 3.0 |
| operation | 7.807 | 5 | 3.0 |
| shuffled | 7.584 | 6 | 3.7 |

The mean of exactly 8.000 is the design guarantee: a batch never repeats a
stratum while an unused one remains. The single-role figure deserves care —
interleaving does not reliably produce *fewer* such batches than shuffling,
because with one role at 30% of rows shuffling can get lucky. What it
guarantees is *where* they occur: interleaving confines them to the epoch tail
(batches 53-55 of 57) once a role is exhausted, while shuffling scatters them
through training (15, 27, 28, 46, 50). That is the property the tests pin.

Getting here took three attempts, each caught by measuring rather than by
reasoning. Plain round-robin over strata produced **35** single-role batches —
worse than shuffling — because stratum keys lead with the role, so sorting
emitted every author stratum before every consumer one. Fixing the pass order
left a tail collapse (19 single-role batches on a role-correlated fixture)
because small strata drain first. Even fractional spreading fixed the tail but
clumped equal-span strata (15 on the real handoff). Only direct
largest-remaining-first construction with a role-share term satisfies both.

**Not done:** the empirical half. Whether interleaving trains a *better*
adapter than shuffling needs paired runs scored on `benchmark/repair-v1`, and
no training run has been executed. The structural result establishes only that
the ordering does what it claims — it is not evidence that it helps.

## Step 6 — one seed run: done, gate not passed

One adapter trained on `handoff/curriculum-repair-v1`, seed 42, interleaved
batching, one epoch (57 updates), scored on `benchmark/repair-v1`.

### Baselines re-established first

The old 36/100 is not a reference point for an 84-task benchmark with different
tasks, so both baselines were re-run on `repair-v1`:

| run | score |
| --- | --- |
| base model, no context | 0/84 (0.0%) |
| base model + PEP-750 documentation context | 33/84 (39.3%) |
| adapter, interleaved, seed 42 | **38/84 (45.2%)** |

The bare model scores zero: 78 of 84 failures are policy failures, meaning it
does not emit a t-string at all. Documentation context is what makes the task
possible; the adapter is measured against that, not against zero.

**The adapter does not beat documentation context on this evidence.** 38 against
33 is a five-task margin on 84 tasks from a single seed. It is consistent with
a real improvement and equally consistent with noise, and no seed replication
was run because the gate below failed.

### Promotion gate: failed

The gate requires one adapter to pass direct `.strings`, direct `.values`,
composition, basic rendering, and all three typed authoring families at once.

| gate capability | result |
| --- | --- |
| `strings` | 1/6 — fail |
| `values` | 2/6 — fail |
| `compose` | 6/6 — pass |
| `render_basic` | 0/6 — fail |
| `author_strings` | 6/6 — pass |
| `author_values` | 6/6 — pass |
| `author_render` | 0/6 — fail |

Four of seven fail, so there is no promotion to a three-seed ladder.

### What the repair demonstrably fixed

Every capability below had **zero** training rows before step 3:

- `author_strings` and `author_values`: 6/6 each.
- `compose`: 6/6, `interpolation_value`: 6/6, `interpolation_format_spec`: 5/6.
- Framing is flat — 12 / 14 / 12 across the three wordings. Capability scores
  no longer partly measure wording, which was the step-1 objective.

### What is still broken, with evidence

All four rendering capabilities sit at 0-2/6, and consumer `.strings` and
`.values` remain near zero *despite now having more rows than their author
counterparts* (36 against 30). The remaining failure is therefore not a
coverage problem. Sampled candidates:

- `strings` → `tuple(part.static for part in template)`. A *new* hallucinated
  attribute, `.static`, joining the `StaticPart` family. AttributeError.
- `author_render` → `return template.render()`. The exact hallucinated API from
  the reviewed run, unchanged.
- `render_basic` → `result = render_template(template)` with no definition.
  NameError. This looks like a **side effect of the step-3 curriculum**: the
  new author rows taught the name `render_template`, and consumer rendering
  tasks now call it as though it were part of the library.
- `values` → emitted a full typed renderer instead of `.values`. The paired
  contrast did not take for this capability.
- `interpolation_expression` → returned `.value` where `.expression` was asked
  for. Field confusion, not API invention.

Three of those five are API-surface errors, which is what
[API_CONTRAST_PATTERNS.md](API_CONTRAST_PATTERNS.md) predicted would survive
this curriculum, and it is the largest remaining bucket (21 attribute/name
errors at `candidate_execute`, plus 18 semantic mismatches).

The `render_template` NameError is new and was not predicted. It should be
treated as a regression introduced by adding author-render rows without a
consumer-side contrast telling the model that a consumer task must define or
inline the renderer.

### Infrastructure verified in a real run

- The `iterate_batches` monkeypatch works; it had never executed before.
- `batch-manifest.json` confirms `interleaved`, 57 batches, 454/454 rows
  covered, 2 padding repeats, mean and minimum 8.0 distinct strata per batch —
  the structural claim from step 5 holding under real training.
- Intermediate checkpoints written at iterations 19, 38 and 57.
- Final train loss 0.036, validation loss 0.044. Per the review brief, that
  validation figure remains teacher-forced on close variants of training rows
  and is **not** a generalization signal — the 45.2% is.

## Post-sequence: two control experiments

An independent review of the step-6 result argued that the named blocker was
being reached for too quickly, and that the information the schema extension
would encode into training rows could be delivered as prompt context instead.
Two evaluations tested that. Both used the same frozen `repair-v1` tasks.

`spike/pep750-docs-context-v2.md` is `pep750-docs-context.md` plus roughly 290
words: the `Template.strings` and `convert` API, an explicit list of the real
public surface, a table of the five hallucinated APIs against their real
replacements, a reference renderer, and three sentences saying when *not* to
render. The original context is untouched and remains the baseline artifact.

| arm | score | |
| --- | --- | --- |
| base model | 0/84 | 0.0% |
| docs v1 (371 words) | 33/84 | 39.3% |
| adapter (seed 42) | 38/84 | 45.2% |
| adapter + docs v1 | 38/84 | 45.2% |
| **docs v2 (661 words)** | **65/84** | **77.4%** |

Paired McNemar on the per-task results:

| comparison | discordant | p |
| --- | --- | --- |
| adapter vs docs v1 | +12 / -7 | 0.359 |
| docs v2 vs adapter | +31 / -4 | <0.0001 |
| docs v2 vs docs v1 | +33 / -1 | <0.0001 |

### What this establishes

- **The adapter never beat documentation context.** 38 against 33 is p = 0.36.
  The earlier "+5 tasks" is not a result.
- **Roughly 290 words of API documentation beat the whole fine-tuning pipeline
  by 27 tasks.** Docs v2 also exceeds the adapter-union-docs oracle of 45/84,
  which was the theoretical ceiling of combining the two.
- Adding docs v1 to adapter c1 moved the score not at all — 38 to 38 — while
  changing 24 individual verdicts. **An earlier draft of this file read that as
  fine-tuning destroying the model's ability to use context. That was wrong**;
  see "The completed matrix" below. Docs v1 was simply too thin to help either
  arm.
- **Docs v2 passes 5 of the 7 promotion-gate capabilities with no training at
  all**, including all three typed authoring families and `render_basic`,
  where the adapter scored 0/6. The adapter passes 3 of 7. The two docs v2
  misses are near: `values` 4/6, `compose` 5/6.
- **The adapter is also 4.6x slower at inference**: 12.5s mean per task against
  2.7s for docs v2, because it emits long renderers where a property access
  was asked for.

### What docs v2 does not fix

Its 19 failures are `render_dynamic_spec` 6, `render_conversion` 6,
`join_static` 4, `values` 2, `compose` 1. Sampled candidates show these are
mostly *definition-order* errors — calling `render(template)` on the line
before defining `render` — not missing knowledge. That is a prompt instruction,
not a curriculum or schema problem.

### The fair second iteration: run, and it changed nothing

The caveat below was addressed rather than argued: the curriculum was given the
same second pass the documentation got.

Two defects were found by inspecting the v1 training rows rather than guessing.
**Eight patterns emit the byte-identical `def render_template(...)` body**, and
at v1 weights that block appeared in **102 of 454 training rows — 22.5% of the
curriculum**. The whole 454-row split contained only **144 distinct answer
bodies**, because each is taught under three prompt families. Over-exposure,
not absence, is the obvious cause of both the `values`-to-renderer collapse and
the `render_template` NameError.

`handoff/curriculum-repair-v2` therefore halves the render cells (block
concentration 22.5% → 11.5%), triples the negatives to attack the f-string
policy regressions, and reallocates to the failing consumer capabilities —
`strings` and `values` 36 → 48 each, `interpolation_expression` 18 → 24,
`join_static` 36 → 42. 492 rows, all marginals within 2pp, 48 distinct seeds.

| arm | score | |
| --- | --- | --- |
| adapter, curriculum v1 | 38/84 | 45.2% |
| adapter, curriculum v2 | 39/84 | 46.4% |

| comparison | discordant | p |
| --- | --- | --- |
| v2 vs v1 curriculum | +7 / -6 | **1.0000** |
| v2 curriculum vs docs v1 | +11 / -5 | 0.210 |
| docs v2 vs v2 curriculum | +27 / -1 | <0.0001 |

**One task of movement, p = 1.0.** Thirteen individual verdicts changed and the
total did not. The failure distribution moved without improving:

| stage | v1 curriculum | v2 curriculum |
| --- | --- | --- |
| candidate_execute (API inventions) | 21 | **10** |
| policy (f-string) | 7 | **18** |
| semantic mismatch | 18 | 17 |

The render-block thinning did what it was designed to do — API-invention
failures halved — and the score did not move, because policy failures more than
doubled to absorb the difference. Note especially that the negatives were
*tripled* specifically to suppress f-string output and f-string failures went
**up**, which refutes the hypothesis that motivated that change.

Per-capability it is churn, not progress: `interpolation_value` 6/6 → 3/6,
`values` 2/6 → 0/6, `strings` 1/6 → 2/6, `interpolation_expression` 0/6 → 2/6.
The promotion gate still passes 3 of 7, the same three as before.

This is the whack-a-mole dynamic made explicit: two curriculum iterations, each
correcting a real and measured defect, moved the score by one task while
redistributing errors across stages. Documentation context beats the second
iteration by 26 tasks at p < 0.0001.

### The completed matrix, and a correction

The comparisons above left one cell empty: the *best* adapter combined with the
*best* context. Filling it materially weakens the conclusion drawn from the
others.

| arm | score | |
| --- | --- | --- |
| base | 0/84 | 0.0% |
| docs v1 | 33/84 | 39.3% |
| adapter c1 | 38/84 | 45.2% |
| adapter c1 + docs v1 | 38/84 | 45.2% |
| adapter c2 | 39/84 | 46.4% |
| adapter c2 + docs v2 | 56/84 | 66.7% |
| **docs v2** | **65/84** | **77.4%** |

| comparison | discordant | p |
| --- | --- | --- |
| adapter c2 + docs v2 vs adapter c2 | +25 / -8 | **0.0046** |
| docs v2 vs adapter c2 + docs v2 | +14 / -5 | **0.064** |

**Two corrections to what is written above.**

First, the claim that fine-tuning "destroyed the model's ability to use
in-context documentation" was wrong. It was inferred from adapter c1 + docs v1
scoring 38 against 38 alone. With documentation that actually carries the API
surface, the adapter gains 17 tasks (39 → 56, p = 0.005). The earlier null
meant docs v1 was too thin to help *anything*, not that the adapter blocks
context. A null result was over-read as a mechanism.

Second, "documentation wins decisively" is too strong. Against the strongest
fine-tuning configuration the margin is 9 tasks at p = 0.064 — ahead, but not
significant at the conventional threshold. The defensible statement is that
the simplest arm is at least as good as anything involving training, while
costing no training run, no curriculum, and no schema extension.

What does survive intact: **no configuration involving the adapter beats
documentation alone**, and the adapter costs two curriculum iterations, a
blocked schema request, and 4.6x slower inference to not get there.

Two details worth keeping. The combined arm's 28 failures are **entirely
`candidate_execute`** — every f-string policy failure (18) and every semantic
mismatch (17) disappeared, which no other arm achieves. And the adapter
actively damages capabilities documentation gets right: `author_values`
6/6 → 2/6 and `compose` 5/6 → 2/6 relative to docs v2 alone.

### Fairness caveat (now discharged)

Docs v2 was written with knowledge of the adapter's observed failure modes, so
a like-for-like contest required giving the curriculum the same second pass.
That was done, and it moved the score by one task at p = 1.0. The asymmetry
argument no longer holds: both arms have now had exactly one informed
iteration, and documentation won by 26 tasks.

## Overnight sweep: the earlier conclusion was an undertraining artifact

Every result up to this point held rank 8, 8 of 28 layers, one epoch (56
updates), ~492 rows, 8-bit base and seed 42 fixed. Only curriculum composition
and batch ordering had ever varied. `spike/overnight.py` varied the rest.

| arm | config | score |
| --- | --- | --- |
| docs-v3 / v3a / v3b | no training | 76 / 74 / 78 — **bar = 76 +/- 2** |
| vol1 seeds 42/43/44 | 492 rows, 1 epoch, 8 layers | 39 / 36 / 39 — **38 +/- 3** |
| vol2 / vol4 / vol8 | 978 / 1950 / 3462 rows | 34 / 40 / 47 |
| vol1-epochs8 | 492 rows, 8 epochs | 60 |
| holdout-family | vol4 minus one prompt family | 54 |
| cap-rank32 | scale 8, rank 32 | 59 |
| **cap-layers28** | **scale 8, all 28 layers** | **70** |
| bf16-lora / bf16-full / bf16-full-deep | unquantized base | 52 / 47 / 62 |

**What this establishes at full strength:** training moves from the high-30s to
the 60-70 band once given capacity or update count. The earlier "training
cannot beat documentation" conclusion was an artifact of training for 56
updates on 0.076% of the parameters. That conclusion was wrong.

**What it does not establish.** Independent review found the reported statistics
inflated. The benchmark's two near-clone variants per capability x framing cell
are **42/42 concordant** for docs-v3, cap-layers28 and vol1-epochs8, and 41/42
for vol8 — the twins carry no independent information, so effective n is 42,
not 84. Recomputed on the 42 cells:

| comparison | task-level (reported) | cluster-level (correct) |
| --- | --- | --- |
| cap-layers28 vs docs-v3 | p=0.24 | **p=0.51** |
| cap-layers28 vs vol8 | p=0.0003 | **p=0.012** — survives |
| vol1-epochs8 vs vol8 | p=0.035 | **p=0.14** — does not |
| vol8 vs vol1 | p=0.28 | p=0.52 |
| bf16-full-deep vs cap-layers28 | p=0.185 | p=0.42 |

Only the capacity result survives. `p=0.51` means **underpowered, not
equivalent** — this benchmark can resolve roughly 17-24 point differences and
nothing smaller, so "the adapter matched the docs bar" was a category error.

Three further corrections:

- **The noise floor cannot be borrowed.** It was measured only at the flat
  492-row/56-update configuration. `holdout-family` trained on 1172 rows that
  are a **strict subset** of vol4's 1755, with fewer updates, and beat it
  **+14/-0** (p=0.016). Less data, fewer steps, fourteen tasks better. Either
  mid-regime run variance is ~14 points or those rows are harmful; no data
  defect was found, so variance is the parsimonious reading. `cap-layers28`'s
  70 is one seed and its true value is roughly 60-75.
- **The full-fine-tune comparison is confounded, by a fix made here.** After
  the previous review flagged a hardcoded 2e-5 as too hot for full tuning, the
  trainer was changed to default full runs to 1e-5. So `bf16-full-deep` ran
  200 updates at 1e-5 against `cap-layers28`'s 390 at 2e-5 — half the steps at
  half the rate — and still reached 62. "Full fine-tuning is worse than LoRA"
  is not supported.
- **The held-out-framing result has a mundane explanation.** Across all twelve
  adapter arms, `python-program` is simply the easiest framing (17.2 mean
  passes against 15.6 and 16.0). Its 20/28 as the held-out family is at
  expectation. The conclusion — no gross framing overfit — stands; the evidence
  offered for it did not.

## The out-of-distribution result: every arm collapses

Both the benchmark and the curricula are generated by the same task-template
machinery — same operation taxonomy, same `Copy these input bindings` preamble,
same three framings, same `result` contract — and every adapter memorizes its
training split (validation loss ~0.005). A score on `repair-v1` therefore
measures transfer *within one synthetic distribution*.

An agent with no access to this repository authored 25 tasks from PEP 750
alone: no sight of the benchmark, the curricula, the prompt conventions, or any
observed failure mode. Independence was verified before use.

| independence check | result |
| --- | --- |
| nine tell-tale phrases from our prompts | 0 / 25 on every one |
| prompt-vocabulary Jaccard vs `repair-v1` | **0.111** (237 words never used by ours) |
| reference collisions vs 809 training answers | **0** |
| fenced code block in prompt | 0/25 (ours: 84/84) |
| distinct answer variables | 25/25 (ours: 1, always `result`) |
| references executing under the sandbox | 25/25 |

`spike/build_ood_benchmark.py` wraps them as `benchmark/ood-v1`.

| arm | `repair-v1` (n=84) | `ood-v1` (n=25) |
| --- | --- | --- |
| base | 0/84 | 1/25 |
| **docs-v3** | **76/84 (90.5%)** | **0/25** |
| **cap-layers28** | **70/84 (83.3%)** | **0/25** |
| vol8 | 47/84 (56.0%) | 0/25 |

**No arm beats the bare base model.** Doubling `--max-tokens` to 512 produced
an identical 0/25 with an identical failure profile, so this is not truncation.
The failures are the same family chased all session — 8 NameError, 6
AttributeError, 2 TypeError — and one candidate called `template.substitute()`,
the *old* `string.Template` API, with the correct documentation in its context.

One evaluator defect was found and fixed on the way: the system prompt
hardcoded ``define the variable `result` `` while these tasks name their answer
per task, so the first attempt scored zero for a reason unrelated to ability.
`_system()` now takes the name from the task's own check and renders
byte-identically for `repair-v1`, so every earlier score remains comparable.

### What this does and does not show

**Shows:** the circularity risk is real and larger than suspected. Both arms'
`repair-v1` scores are substantially specific to that generator's task shape.
Documentation was never the out-of-distribution control it was treated as — it
was tuned against `repair-v1` failures across three iterations, fitted to the
same distribution by prose rather than by gradients.

**Does not show:** any ranking between arms. A benchmark on which everything
scores 0-1 has no discriminative power. This is a floor effect, not a finding
that documentation and training are equally useless in general.

The session's arc, stated honestly: on the synthetic benchmark documentation
beats training, and training closes most of the gap when given capacity. On 25
independently authored realistic tasks **neither approach works at all** — which
invalidates the premise of that comparison rather than settling it.

## Mellum2: the actual target, measured

Mellum2 is the model this work is ultimately meant to improve — the team behind
it will accept training data, which was never true of Qwen2.5-Coder-7B. Every
Qwen result above is therefore proxy work on a model nobody will ship.

### The preview snapshot was not Mellum2

First measurements used a local q8 conversion of a GRPO **preview** checkpoint
at step 200. It scored 0/25 on `ood-v1`, but the number was meaningless:
**48% of generations opened `<think>` and never closed it**, and 44%
degenerated into repetition with control tokens emitted as literal text. Half
the trials failed before the model could be right or wrong.

Released weights behave completely differently:

| generation health (10 gens, temp 0) | preview GRPO | released Thinking | released Instruct |
| --- | --- | --- | --- |
| clean-stop rate | ~0.5 | 0.80 | **1.00** |
| unterminated `<think>` | 48% | 0 | 0 |
| repetition loops | 44% | 1/10 | **0** |
| mean output | — | 2310 chars | 634 chars |

**Released Instruct is the variant to build on.** Details and the withdrawn
issues are in [MELLUM_ISSUES.md](MELLUM_ISSUES.md).

### The LoRA path exists

`mlx_lm.lora` trains Mellum2's MoE without modification: 0.335% trainable
(40.65M of 12.15B), two updates, loss 1.094, no routing errors. This was the
gating risk for the deliverable and it is resolved. Note `mellum` is supported
in **mlx-lm git main only**, not the 0.31.3 PyPI release.

### Scores

| arm | `ood-v1` (25) | `repair-v1` (84) |
| --- | --- | --- |
| Mellum2-Instruct, bare | 0/25 | 0/84 |
| Mellum2-Instruct + docs-v3 | 1/25 | **59/84 (70.2%)** |
| Qwen2.5-Coder-7B, bare | 1/25 | 0/84 |
| Qwen2.5-Coder-7B + docs-v3 | 0/25 | **76/84 (90.5%)** |

Two things follow, and the second is the important one.

**Mellum2 is *worse* than Qwen on the synthetic benchmark** — 59 against 76
with identical documentation, despite being newer and larger. Neither model
knows PEP 750 bare (both 0/84). Mellum2 confabulates a `t_string` type with
`.value` and `.format_args`; the Thinking variant invents `prefix`,
`f-strings`, `values`. Both are wrong in different ways, and neither carries
the preview's tagged-template draft.

**The out-of-distribution floor is a property of the benchmark, not of Qwen.**
Across six model/condition combinations — two base models, bare and with
documentation, plus the preview snapshot and two Qwen adapters — **only 2 of
the 25 tasks were solved by anything at all**. That answers the question left
open above: the collapse was not the 7B being weak. `ood-v1` is valid,
independently authored and executable, but it is too hard to discriminate
between arms and cannot rank anything.

### Training works on the target model

A LoRA over all 28 layers, one epoch, the same 443-row `curriculum-repair-v2`
used throughout, trained on released Instruct:

| Mellum2-Instruct | `repair-v1` | `ood-v1` |
| --- | --- | --- |
| bare | 0/84 | 0/25 |
| **+ LoRA, 28 layers** | **45/84 (53.6%)** | 0/25 |
| + docs-v3 | 59/84 (70.2%) | 1/25 |

**+45/-0 against bare, p < 0.00001.** Forty-five tasks gained, none lost, from
a true zero baseline. This is the first unambiguous demonstration in the whole
effort that the corpus can install knowledge in the model it is meant for — on
Qwen every adapter was competing against a documentation arm that already
worked, which made the signal hard to see.

Against documentation the adapter is behind but not decisively: **+30/-16,
p = 0.054**. Note these are not exclusive; the deployable question of adapter
*plus* documentation is untested on Mellum2.

Capability profile is sharply split. Solved outright: both typed authoring
families, composition, three of four interpolation fields (6/6 each). Failed
outright: every rendering capability, `values`, and most of `strings` (0/6).
The adapter learned introspection and authoring and did not learn rendering —
the same shape seen on Qwen, which points at the curriculum rather than the
model.

`ood-v1` remains 0/25, consistent with every other arm. Installing benchmark
capability and transferring to independently authored code are different
problems, and only the first is solved.

### Documentation and training compose: 78/84

The deployable configuration — adapter *and* documentation, which the whole
session had treated as alternatives — was the last cell in the matrix.

| Mellum2-Instruct | `repair-v1` | `ood-v1` |
| --- | --- | --- |
| bare | 0/84 (0.0%) | 0/25 |
| + LoRA, 28 layers | 45/84 (53.6%) | 0/25 |
| + docs-v3 | 59/84 (70.2%) | 1/25 |
| **+ LoRA + docs-v3** | **78/84 (92.9%)** | 0/25 |

| comparison | discordant | p |
| --- | --- | --- |
| LoRA+docs vs docs alone | +25 / -6 | **0.0009** |
| LoRA+docs vs LoRA alone | +33 / -0 | **<0.0001** |

**Thirteen of fourteen capabilities at 6/6.** The sole remaining failure is
`author_render` (0/6), and all six failures are `candidate_execute` — no policy
violations, no semantic mismatches. Every capability the adapter alone could
not do (rendering, `values`, `strings`) is solved once documentation is also
present, and every capability documentation alone could not do is solved by the
adapter.

**This overturns the framing the session ran on.** "Documentation versus
training" was the wrong question for this model: the two are complementary, and
the combination beats either alone with high significance. Note the same
combination on Qwen was flat — 38 against 38, gaining 12 and losing 12 — so
composition is a property of the target model, not a general result.

**The caveat that matters.** `repair-v1` shares a generator with the training
data, so 92.9% is an in-distribution number and the circularity described above
applies in full. On the independently authored `ood-v1` the combination scores
**0/25**, no better than anything else. Installing benchmark capability and
transferring to real code remain different problems, and only the first is
solved. The 92.9% should be read as "the pipeline can saturate its own
benchmark", not as a capability claim.

### Harness defect found, not yet fixed

The execution sandbox returns its verdict as JSON on stdout, so **candidate
code that prints corrupts the protocol channel** and fails as `subprocess`
regardless of correctness. Seen twice in ~175 out-of-distribution evaluations,
both on candidates that were otherwise plausible. It does not affect any
conclusion here — the tasks were unsolved by every arm anyway — but it fails
correct code and should be fixed by separating candidate stdout from the
protocol stream.

## Remaining

The six-step repair sequence, an overnight parameter sweep and an
out-of-distribution check are complete. The out-of-distribution collapse has
**two independent causes stacked on top of each other**, and an earlier draft of
this section conflated them into one:

- **docs-v3 scores 0/25** because the base model cannot apply correct API
  documentation supplied in its own context — it emitted `template.substitute()`,
  the *old* `string.Template` method, with the real API verbatim in the prompt.
  That is a base-model capability limit.
- **The adapters score 0/25** because they memorized a template distribution
  generated from **54 seeds**, and that does not transfer to arbitrary realistic
  code. That is a corpus limit, and a different base model does nothing for it.

### Correction: do not pick a base model that already knows PEP 750

The previous draft ranked "try a base model with a later training cutoff"
first. For the training arm that is self-defeating. The experiment asks whether
fine-tuning can install a genuinely novel API. A base that already knows
t-strings has nothing left to install, and any adapter score on it measures
pre-existing knowledge rather than learning — it would also contaminate
`ood-v1` as a measure of whether training worked.

On that reading `Qwen2.5-Coder-7B` is the *correct* substrate for the training
question, not the wrong one: it scores 0/84 bare, so anything it gains is
attributable.

A stronger model is legitimately useful for exactly one thing, below.

### Ranked

1. **Task-validity probe on `ood-v1`.** Score a strong model with docs-v3 on
   the 25 tasks, purely to establish a solvability ceiling. Right now two
   readings are indistinguishable: the tasks are sound and the 7B is too weak,
   or the tasks are too hard or underspecified to support any conclusion. It
   does not matter whether the probe model already knows PEP 750 — the question
   is "are these tasks answerable", not "did training work". **The probe model
   is probed and discarded; it is never trained and never becomes the base.**
2. **The corpus, not the base.** The adapter collapse is a transfer failure
   from 54 template-generated seeds. No rank, layer count, epoch schedule or
   quantization addresses that; the overnight sweep moved `repair-v1` scores
   from 38 to 70 and moved `ood-v1` not at all. Broadening the corpus toward
   realistic, non-template t-string code belongs to SP5 and is the binding
   constraint on the training arm.
3. **An out-of-distribution set with a difficulty gradient.** `ood-v1` cannot
   rank anything while every arm sits at the floor. A usable set needs tasks
   the base model can already pass. Contingent on the step-1 probe: if the
   probe scores well, `ood-v1` is fine and only the arms are weak.
4. **Freeze `repair-v1` only if still wanted.** Its 84 tasks remain
   `needs_human_review`, so no number here is citable — but scores on it are
   substantially specific to its own generator, which lowers the value.

### What is now moot

- **The API-contrast schema extension** (`API_CONTRAST_PATTERNS.md`) — scoped to
  fix hallucinated APIs on `repair-v1`, which the same arms hallucinate on
  `ood-v1` while scoring zero regardless.
- **Seed replication of `cap-layers28`** and **the combined adapter-plus-docs
  arm** — both only sharpen a ranking that does not survive contact with
  independently authored tasks.
- **The `interleaved` versus `shuffled` batching comparison** from step 5.
- **Adopting a newer base model for training.** See the correction above.

### Local model availability, checked

`mlx-lm` 0.31.3 is the newest release on PyPI, so there is no upgrade path for
unsupported architectures.

| candidate | local | loads under `mlx_lm`? |
| --- | --- | --- |
| Mellum2-12B GRPO preview (MLX q8) | yes, 12GB | **no** — `model_type: mellum` is not among the 118 supported architectures |
| Gemma 4 12B (MLX 8-bit) | yes, 12GB | **no** — `model_type: gemma4_unified` (multimodal); mlx-lm supports `gemma4`/`gemma4_text` only |
| Qwen3.5-9B | no | architecture `qwen3_5` **is** supported |

### Measured costs, for planning

| operation | cost |
| --- | --- |
| curriculum build (any scale) | seconds |
| LoRA train, 492 rows, 1 epoch | ~6 min |
| LoRA train, 3462 rows, 28 layers | ~47 min |
| full fine-tune, 28 layers, 200 iters | ~24 min |
| evaluation, 84 tasks, adapter | ~18 min |
| evaluation, 84 tasks, docs only | ~4 min |
| evaluation, 25 OOD tasks | ~3 min |

Compute was never the constraint. Measurement power was, and still is.

## Run A / Run B: the low-body curriculum, with a control (2026-08-06)

Two LoRA adapters on Mellum2-12B-A2.5B-Instruct, 28 layers, **identical
recipe** — 3 epochs, peak LR 3e-5 with linear warmup and cosine decay to 3e-6,
batch 8, seed 42 — differing only in curriculum:

| run | curriculum | rows | updates | renderer-body share |
| --- | --- | --- | --- | --- |
| **A** (control) | `curriculum-repair-v2` | 443 | 168 | 11.5% |
| **B** | `curriculum-lowbody-v1` | 486 | 183 | **6.2%** |

Scored with `spike/rescore_ood.py` on `ood-v1`, never exact match.

| arm | rendered | unrend | raised | **undef-render** | miss-import | unbound-in |
| --- | --- | --- | --- | --- | --- | --- |
| bare | 13 | 0 | 6 | 0 | 0 | 3 |
| + LoRA (old recipe) | 11 | 0 | 10 | 1 | 0 | 4 |
| + docs | 7 | 1 | 12 | 0 | 0 | 8 |
| + LoRA + docs (old recipe) | 6 | 1 | 14 | **3** | 3 | 4 |
| **A** | 12 | 0 | 9 | **0** | 0 | 3 |
| **A + docs** | 10 | 0 | 7 | **0** | 0 | 4 |
| **B** | 7 | 1 | 11 | **0** | 0 | 5 |
| **B + docs** | 12 | 0 | 8 | **0** | 3 | 4 |

### The hypothesis is not supported

`undefined_renderer` went to **zero on every new arm, including the control**.
Run A carries the *unchanged* curriculum at 11.5% renderer-body share and still
scores 0. **B − A = 0** on the metric the curriculum was built to move, so
halving the body share bought nothing measurable.

Whatever removed the defect is shared by both runs — the recipe, the toolchain,
or noise — and is not the curriculum.

Without the control this would have been written up as "lowering renderer
exposure eliminated a trained-in defect, 6 → 0". That claim would have been
wrong, and the control exists only because the pre-registration review demanded
one.

### A correction to the metric, found while reading the results

The first cut of `rescore_ood.py` scored `render`, `render_template`,
`Interpolation`, `Template` and `convert` as one bucket. They are two failures.
Calling a renderer that was never defined is the over-exposure symptom; using a
`string.templatelib` name without importing it is a forgotten import in a
program whose renderer is otherwise correct. B + docs looked like 3
`undefined_renderer` until the buckets were split — all three define `render`
correctly and omit `convert` from the import line. The baseline's 6 was
likewise 3 + 3, not 6.

### What this does not establish

- **The toolchain changed underneath the comparison.** Run A's first launch
  died with `Model type mellum not supported`: the venv held mlx-lm 0.31.3 from
  PyPI, which has no `mellum`, and the package is not pinned in
  `pyproject.toml`. The earlier Mellum work ran on an ad-hoc git install since
  clobbered. A and B ran on git `254d153f`. A and B are mutually comparable;
  neither is cleanly comparable to the recorded baseline.
- **Single seed, n = 25.** Differences of two or three tasks are not
  distinguishable from noise at documented 10–19 point variance. Multi-seed was
  deferred by choice.
- **Warmup clamped to 42 (A) and 45 (B)**, a quarter of each run, so this is
  not the Mellum 2 report's 100-step ramp.
- **Both runs fit the training split**: A's validation loss bottoms at 0.024
  around iteration 80 and drifts up while train loss reaches 0.000. Three
  epochs is past the useful point.
- Exact match: A scored 1/25, everything else 0/25. Still not a capability
  measure — the prompts do not supply the literals the references require.

### Correction: the structural metric was wrong, and the corrected one reverses the verdict (2026-08-06)

An adversarial review found, and independent re-measurement confirmed, that the
metric above mis-specified **6 of 25** tasks. Their references answer with a
`tuple` or a `dict`, not a `str`, so scoring "did it produce a string" filed
correct structured answers as failures — Run A's SQL answer
`('SELECT * FROM tickets WHERE tenant = $1 AND status = $2', (17, 'open'))`
among them. The `rendered` column had a ceiling of 19, and the printed table
omitted three outcome categories, silently dropping about a quarter of every
arm's tasks.

`rescore_ood.py` now executes each reference to learn its answer type, scores
candidates against **that**, gives the probe a `__name__` so main-guarded
programs run, and prints every category.

**Type-match against the reference's own type, all eight arms:**

| arm | type match | exact |
| --- | --- | --- |
| **bare** | **17 / 25** | 0 |
| + LoRA (old recipe) | 12 | 0 |
| + docs | 10 | 1 |
| + LoRA + docs (old recipe) | 9 | 0 |
| A | 13 | 1 |
| A + docs | 14 | 0 |
| B | 8 | 0 |
| B + docs | 16 | 0 |

**The bare model is the best arm.** Every intervention — LoRA, docs, and both
together — scores worse out of distribution than doing nothing. B swings 8 → 16
on the presence of docs alone, which is the size of the instability we are
trying to measure effects inside of.

The interventions do change behaviour: the bare model never defines a renderer
(**0/25**), trained arms emit one **9/25**, docs arms **16–21/25**. So the
training lands. It just does not produce more correct answers on tasks it did
not come from.

Renderer emission is **9/25 in both A and B, identically** — a more sensitive
readout than the `NameError` count, and the strongest legitimate evidence that
halving renderer-body share changed nothing about the model's habits.

### Consequences

- **The Run A/B conclusion above is vacuous, not merely null.** The
  pre-registered baseline of 6 was itself an artifact of the un-split scorer;
  corrected it is 3. An experiment powered to detect the removal of ~3 events
  in 25, single seed, across a simultaneous recipe *and* toolchain change,
  cannot produce a decisive answer either way. Nothing was shown to be removed.
- **`ood-v1` needs rebuilding, not re-metricking.** Essentially every task
  requires reference literals its prompt never states. A structural metric
  cannot score the 6 non-`str` tasks by equality, cannot tell rendered sense
  from rendered nonsense, and is blind to eager-evaluation errors — a candidate
  evaluating `t"...{name}..."` before binding `name` believes templates defer
  evaluation, which is precisely the gap this corpus exists to close, and it
  lands in `raised` unattributed. The task *ideas* are good; the checks and
  prompts are not.
- **On present evidence the corpus is not shippable.** There is no measurement
  showing that training on it beats putting documentation in the prompt, and
  none showing either beats the untouched model out of distribution. The
  in-distribution wins are same-generator-family artifacts.

### What would reopen the question

1. Rebuild the OOD benchmark: fully specified prompts, property-based checks
   (answer type, required substrings, interpolation values) instead of exact
   equality, n ≈ 100.
2. Establish the noise floor before claiming any effect again: three training
   seeds of one config, early-stopped at the validation minimum rather than run
   to three epochs.
3. A second-model transfer arm. The deliverable is a *corpus*, so the
   shippability question is "does it help any model out of distribution", not
   "does it help this MLX quantization of Mellum".

Until (1) exists, no training run can produce a believable number.

### Property-based scoring: the first metric that requires mechanism *and* correctness (2026-08-06)

The type-match verdict above was itself misleading, in the same family as the
two errors before it. It ranked the **bare model first at 17/25** — while that
model used a t-string in **zero** of 25 tasks. It was solving everything the old
way, with f-strings and concatenation. A metric that ignores mechanism rewards
ignoring the feature the corpus exists to teach.

`spike/score_ood_properties.py` scores only properties checkable without the
reference's private literals, and requires them together:

- `policy` — the program builds a `Template`, detected via `ast.TemplateStr`
  rather than a regex, so a `t"..."` in a comment cannot count
- `typed` — the answer's type equals the reference's own answer type
- `literals` — every literal the *prompt* does state appears in the answer
- **`solved` = all three**

| arm | **solved** | policy | typed | literals | exact |
| --- | --- | --- | --- | --- | --- |
| bare | **0** | 0 | 17 | 13 | 0 |
| + LoRA (old recipe) | **0** | 0 | 12 | 12 | 0 |
| + docs | **3** | 15 | 10 | 11 | 1 |
| + LoRA + docs (old recipe) | **5** | 24 | 9 | 12 | 0 |
| A | **2** | 6 | 13 | 11 | 1 |
| A + docs | **10** | 23 | 14 | 11 | 0 |
| B | **2** | 5 | 8 | 11 | 0 |
| **B + docs** | **11** | 24 | 16 | 12 | 0 |

The ordering is monotone and, for the first time, in the direction the work
predicts:

- **Neither ingredient alone solves anything.** Bare 0, LoRA alone 0, docs
  alone 3. The adapter supplies mechanism without correctness (policy 5–6,
  solved 2); documentation supplies some of both but little.
- **Only the combination works**, and the new recipe roughly doubles the old
  one: 5 → 10 (A) and 11 (B). Same corpus for A as the old run, so that gap is
  recipe, toolchain, or noise — not curriculum.
- **B − A = +1**, which is noise at n = 25. The low-body curriculum is still
  unsupported; it is simply no longer the thing being tested.

This does not overturn the caveats — single seed, n = 25, unrepaired prompts,
`solved` still cannot tell rendered sense from rendered nonsense. But the
claim "everything collapses out of distribution" was an artifact of three
successive broken instruments, and it does not survive a metric that asks the
actual question.

#### Correction: the policy check was literal-only (2026-08-06)

Validating the authoring spec's self-check against `ood-v1` caught a bug in
`score_ood_properties.py` as well. Both required an `ast.TemplateStr`, but task
`10e6fd992011` deliberately asks for a `Template` assembled by hand from
`Interpolation` objects — a legitimate shape with no t-string literal in it.
Any correct answer scored a policy failure. Both checks now accept a
`string.templatelib` import as well.

Corrected table:

| arm | **solved** | policy | typed | literals |
| --- | --- | --- | --- | --- |
| bare | **0** | 0 | 17 | 13 |
| + LoRA (old recipe) | **1** | 8 | 12 | 12 |
| + docs | **4** | 19 | 10 | 11 |
| + LoRA + docs (old recipe) | **5** | 25 | 9 | 12 |
| A | **4** | 14 | 13 | 11 |
| A + docs | **10** | 25 | 14 | 11 |
| B | **2** | 15 | 8 | 11 |
| **B + docs** | **11** | 25 | 16 | 12 |

The ordering is unchanged and the conclusions stand: neither ingredient alone
solves anything, only the combination does, the new recipe roughly doubles the
old, and B − A = +1 is noise. The bare model remains at 0 — it never touches
`string.templatelib` by any route.

Note the shape of it: the docs arms reach **policy 25/25** — every program uses
the feature — while `typed` sits at 9–16. Mechanism is essentially solved and
correctness is not. That is where effort should go.

## ood-v2: the first believable measurement (2026-08-06)

100 tasks authored to `spike/OOD_AUTHORING_SPEC.md` by an agent with no repo
access, verified independently before use (Jaccard 0.071 against `repair-v1`,
zero tell-tale phrases, zero reference collisions, 100 distinct answer
variables, 53 non-`str` answer types, all 100 references materialising).
Fingerprint `3a94d381b74c`.

**Because the prompts state their literals, exact match is a fair metric
again** — the property scaffolding existed only to work around `ood-v1`'s
underspecification. `solved` is now exact match AND the mechanism check that
stops a model scoring by avoiding t-strings.

| arm | **solved** | policy | typed |
| --- | --- | --- | --- |
| bare | **5** | 7 | 70 |
| + docs | **61** | 100 | 89 |
| + LoRA (old recipe) | **36** | 96 | 66 |
| + LoRA + docs (old recipe) | **61** | 100 | 74 |
| A | **51** | 98 | 74 |
| **A + docs** | **76** | 100 | 94 |
| B | **53** | 97 | 70 |
| B + docs | **75** | 100 | 85 |

Paired McNemar over the 100 tasks:

| comparison | gained | lost | p |
| --- | --- | --- | --- |
| docs alone vs bare | 56 | 0 | <0.0001 |
| adapter alone vs bare | 46 | 0 | <0.0001 |
| **adapter added on top of docs** | **23** | **8** | **0.011** |
| new recipe vs old (both + docs) | 20 | 5 | 0.004 |
| B vs A (+ docs) | 7 | 8 | 1.00 |
| B vs A (no docs) | 11 | 9 | 0.82 |

### What this settles

- **The corpus adds value over documentation-in-prompt.** 61 → 76 with 23 tasks
  gained against 8 lost, p = 0.011. That question has been open since the
  documentation arms first matched the trained ones, and every previous attempt
  to answer it ran through a broken instrument.
- **Training alone is substantial**: 5 → 51, with 46 tasks gained and **zero
  lost**. The bare model is not merely unpolished here; at policy 7/100 it
  almost never reaches for the feature at all.
- **The recipe change was real**: old 61 → new 76 on the same curriculum,
  p = 0.004. Three epochs with warmup and cosine decay beats one epoch at a
  constant rate.
- **B − A is null at n = 100** (p = 1.00 and 0.82). The low-body curriculum is
  confirmed to do nothing, now with the power to say so.

### A defect found in the scorer while reading these results

The `literals` gate was built for `ood-v1` and is wrong here. It extracts
backticked spans from the prompt — which on this benchmark are the template
*source* (`Weather in {city} today`) and API names (`.strings`) — and demands
they appear in the rendered answer, where by design they do not. It failed
tasks that pass exact match, and held `solved` to 0–3 of 100 on every arm. It
is retired to a diagnostic column.

### Standing caveats

Single seed. Same mlx-lm pin (`254d153f`) across all eight arms, so these are
mutually comparable — unlike anything measured before the pin. `typed` is
higher than `solved` everywhere, so a good deal of near-miss remains: the
models produce the right shape more often than the right content.

### RETRACTED: the p = 0.011 headline was a harness artifact (2026-08-06)

Review found, and re-verification confirms, that `verify_candidate` parsed the
*whole* of the collector's stdout as JSON (`oracle/verify.py:96`). The candidate
runs inside the collector's process, so anything it prints lands on that stream
ahead of the verdict — and any candidate ending in a demonstrative `print()`
was filed as an infrastructure failure and scored wrong.

**It hit 7 candidates on `ood-v2`, all in the untrained control arm and none in
any of the six adapter arms.** Printing a result is an untrained habit; the
fine-tuned models had been trained out of it. So the bug deflated precisely the
baseline every adapter was compared against. This is the "sandbox stdout
defect" that had sat on the open-issues list since early in the project.

The oracle now scans backwards for the last JSON object carrying a `status`
key. `spike/reverify.py` re-runs it over stored candidates, so a scoring fix
costs seconds per arm instead of a re-generation.

| arm | reported | **corrected** |
| --- | --- | --- |
| bare | 5 | **5** |
| + docs | 61 | **68** |
| + LoRA (old recipe) | 36 | **37** |
| + LoRA + docs (old recipe) | 61 | **60** |
| A | 51 | **50** |
| A + docs | 76 | **76** |
| B | 53 | **53** |
| B + docs | 75 | **76** |

| comparison | gained | lost | p | Bonferroni x6 |
| --- | --- | --- | --- | --- |
| docs alone vs bare | 63 | 0 | <0.0001 | <0.001 |
| adapter alone vs bare | 45 | 0 | <0.0001 | <0.001 |
| **adapter A on top of docs** | 18 | 10 | **0.185** | 1.00 |
| adapter B on top of docs | 18 | 10 | 0.185 | 1.00 |
| **new recipe vs old (+docs)** | 20 | 4 | **0.0015** | **0.009** |
| B vs A (+docs) | 7 | 7 | 1.00 | 1.00 |

**"The corpus adds value over documentation-in-prompt" is withdrawn.** It was
manufactured by a bug that only bit the control. It would not have survived
Bonferroni correction across six tests even at its reported value.

### What actually survives

- **Documentation dominates.** 68/100 alone, 63 tasks gained against **zero**
  lost. It beats every adapter-alone arm (37–53) by a wide margin.
- **The adapter works, as a substitute rather than an addition.** 5 → 50 with
  45 gained and zero lost. The bare model is at policy 7/100 — it does not know
  the feature exists. Weights buy that without spending context.
- **The recipe change is the strongest genuinely novel result**: 60 → 76 on the
  same curriculum, p = 0.0015, surviving Bonferroni. Three epochs with warmup
  and cosine decay beats one epoch at a constant rate.
- **B − A remains null.**

### The honest pitch

Not "our corpus beats documentation". It is: *the corpus installs the feature
in the weights, at no context cost, reaching roughly three-quarters of what a
708-word prompt achieves — and the two have not yet been shown to compose.*
That claim is defensible and reproducible; the previous one was neither.

### Also noted

Re-verification flipped four tasks that the bug does not explain (`47a37ea7`
three times, `b8bef4af` once), so execution is not perfectly deterministic at
about the ±1 level. Small against these margins, but it means single-run
differences of one or two tasks are not real.

## Seeds and the pre-registered policy (2026-08-06)

Both decisions were fixed in `spike/PREREGISTRATION.md` (commit `9f6956c`)
before either analysis ran.

### The lenient policy, applied to all twelve arms

`TStringPolicy` rejected any f-string, `.format()` or `%`-formatting whenever
the reference used a t-string — which **rejected 4 of the 100 gold reference
solutions**. A gate that fails the correct answer is not measuring correctness,
so evaluation now passes `strict_old_form=False`: a candidate fails only when
it builds no `Template` where the reference builds one. Under that rule 0/100
gold references are rejected. The shipped default is left unchanged, because
the policy is a cross-boundary contract run by the provider's CI; the option is
annotated for SP5 to decide.

**The pre-registered expectation held**: every arm rose, and the docs-only arm
rose most (68 → 76, the largest single gain), because mixed-usage rejects
concentrate there. As committed, that rise is *not* reported as evidence
against the adapter.

### Seed variance, same curriculum and recipe, seeds 42/43/44

| | seed 42 | seed 43 | seed 44 | spread |
| --- | --- | --- | --- | --- |
| adapter alone | 54 | 58 | 48 | **10** |
| adapter + docs | 80 | 76 | 80 | **4** |

Baseline `base-docs` = **76**.

| adapter + docs vs base-docs | gained | lost | net | p |
| --- | --- | --- | --- | --- |
| seed 42 | 17 | 13 | +4 | 0.585 |
| seed 43 | 15 | 15 | 0 | 1.000 |
| seed 44 | 17 | 13 | +4 | 0.585 |

### Verdict under the pre-registered rule

`s = 4`, so `s < 8`: seed noise does not by itself cover the originally
observed difference. But the rule's second branch applies exactly as written —
**the effect is not established.** Across three seeds the adapter adds a mean
of **+2.7 tasks** on top of documentation, no seed reaches significance, and
the best single seed is +4 with 13 tasks lost against 17 gained.

Per the pre-registration, this does not license claiming the adapter beats
documentation, and no further single-seed comparison will be reported as
evidence either way.

**Note the asymmetry, which is the useful finding.** Adapter-alone varies by
**10 tasks** across seeds while adapter-plus-docs varies by **4**. Documentation
in the prompt does not merely raise the score, it *stabilises* it: whatever the
adapter learned about the API is fragile to seed, and the docs supply the same
knowledge reliably. That is a better explanation of why docs keep winning than
anything about corpus composition, and it points at the corpus containing no
explanatory content at all — only task/solution pairs.

### Where this leaves the numbers

| arm | solved /100 |
| --- | --- |
| bare | 5 |
| + LoRA (old recipe) | 36 |
| adapter alone (mean of 3 seeds) | 53.3 |
| + LoRA + docs (old recipe) | 62 |
| **docs alone** | **76** |
| **adapter + docs (mean of 3 seeds)** | **78.7** |

## Explanatory content: the registered hypothesis is not supported (2026-08-08)

`curriculum-explained-v1` — `repair-v2` plus 90 verified explanatory rows
(16.9%) — trained at seeds 42/43/44 on the identical recipe, evaluated on
`ood-v2`, scored with the lenient policy.

### Primary metric, as registered in `PREREGISTRATION.md` §3

| adapter alone | seeds 42/43/44 | spread | mean |
| --- | --- | --- | --- |
| `repair-v2` (baseline) | 54 / 58 / 48 | **10** | 53.3 |
| `explained-v1` | 56 / 61 / 64 | **8** | 60.3 |

The spread fell from 10 to 8. **That is not a result.** A spread computed from
three points is an extremely noisy statistic, and a move of 2 on it is well
inside what three draws can produce by chance. The registered prediction was a
fall "toward 4"; this is not that.

### The mean rose, and the reason is one seed

| explained vs baseline, matched seed | gained | lost | net | p |
| --- | --- | --- | --- | --- |
| seed 42 | 13 | 11 | +2 | 0.839 |
| seed 43 | 12 | 9 | +3 | 0.664 |
| **seed 44** | **22** | **6** | **+16** | **0.004** |

Two of three seeds show nothing. The entire +7 mean comes from seed 44, which
was **the worst baseline seed at 48** and rises to 64. "Explanatory content
helps" and "baseline seed 44 was an unlucky draw" predict exactly this pattern
and cannot be told apart from it. Pooling the three (p = 0.019) is not
legitimate — the comparisons share one task set and are dominated by a single
seed.

### The confound I built in

`explained-v1` has 533 rows against the baseline's 443, so at fixed epochs it
trains for **201 updates against 168** — 20% more. Any mean gain has training
length as a competing explanation, and this was a design error on my part
rather than a discovered one.

### Verdict

Per the pre-registration: *"A mean that rises without the spread falling is a
weaker result, and will be reported as one."* That is this case. The hypothesis
that explanatory content stabilises what the adapter learns is **not
supported**. The corpus change is not established as doing anything a longer
training run would not.

The registered response to a null is to say so rather than rebuild at a
different row count, and that stands. One control is still owed, because it
tests the confound rather than the hypothesis: **`repair-v2` trained to 201
updates**. If it also gains ~7, training length explains the whole thing.

### Recorded as not run

`adapter + docs` was pre-registered as not a metric and is not used here. For
completeness only, and not as evidence: 72 / 80 / 76 against the baseline's
80 / 76 / 80.

### What did clear

Prose leakage was a live risk — 90 rows from 18 distinct texts, each repeated
5×, is the over-exposure shape that caused trained-in failures earlier. It did
not materialise: **0 of 100 candidates fail to parse as Python** on seed 42.
The explanatory rows do not make the model answer prose when asked for code.

### CORRECTION: the null verdict above was an over-correction (2026-08-08)

Review challenged the null and I verified the challenge. **My "explanation helps
and unlucky seed 44 are indistinguishable" claim was false** — the per-task data
distinguishes them, and it favours a real effect.

Regression to the mean predicts seed 44's gains land on tasks the *other*
baseline seeds already solve. They do not:

| seed-44 gains (22 total) | count |
| --- | --- |
| on tasks another baseline seed solved | 11 |
| **on tasks no baseline seed solved** | **11** |

Base-44's 52 failures split 22 solvable-by-another-base-seed and 30
solved-by-none; gains hit 50% of the first group and **37% of the second**,
where regression to the mean predicts approximately zero.

Across the frontier: **3 tasks go 0/3 baseline → 3/3 explained**
(`616c2179`, `7913a6bf`, `833a49d4`) against **1** going the other way.

And the mechanism is visible in the error taxonomy, pooled over three seeds:

| | baseline | explained |
| --- | --- | --- |
| **AttributeError** (hallucinated API) | 49 | **26** |
| NameError | 22 | **35** |
| — of which missing `templatelib` import | 10 | **14** |

Hallucinated-API errors roughly halve, which is exactly what explanatory rows
target. (Absolute counts differ somewhat from the reviewer's — 49→26 against
their 43→23, and 10→14 against their 6→18 — because we classify differently.
The direction and rough magnitude agree; the import regression is real but
smaller than they reported.)

**Corrected verdict: not "hypothesis unsupported" but "underpowered, direction
consistent, mechanism visible, confound outstanding."**

### Three defects of my own that the review found

1. **The registered primary metric was undetectable by design.** A range over
   three draws is close to worthless as a variance estimate — the 95% CI on σ
   from 3 points spans roughly [0.5σ̂, 6σ̂]. Distinguishing spread 10 from
   spread 4 needs on the order of 10 seeds per arm. Worse, **the observation
   that motivated the whole experiment** — "docs stabilise, spread 4 vs 10" —
   is the same 3-draw statistic and was never established either. Registering a
   refutation rule the instrument cannot support is not discipline; it produces
   confident nulls.
2. **Row 13 violates the pre-registration's own exclusion.** It reads *"If a
   task asks only for the static parts… do not render"* — benchmark-convention
   coaching, which §3 explicitly excluded. It came near-verbatim from
   `pep750-docs-context-v3.md`, which means the 76-point docs comparator also
   contains harness-shaped advice. Fair as an internal comparison, since both
   arms carry it; **not fair in an external claim without disclosure.**
3. **6 of 18 explanatory answers name `Template`/`Interpolation`/`convert`
   without showing an import**, which is the likely cause of the missing-import
   regression. Telling does not beat demonstrating.

Also: `--repeat` defaults to 4 while the shipped artifact used 5, and the
runbook does not pass it. The invocation is now recorded.

### The planned control was the wrong control

`repair-v2` at 201 updates introduces a *third* configuration rather than
isolating one: the cosine schedule length derives from `iters`, so it would
carry a different per-step LR profile than either existing arm, plus a
fractional epoch. And the confound is smaller than "20% more updates" suggests
— the explanatory rows are 16.9% of rows but only **8.5% of characters**.

Replaced by a **content-matched placebo**: `repair-v2` plus 90 verified Q/A
rows on an unrelated Python topic, same system prompt, same 18×5 structure,
same stratum, same 533 rows. That holds updates, schedule, duplication and
prose-register constant, leaving only whether the prose is *about PEP 750* —
and it also kills the "any Q/A prose regularises" alternative, which the
matched-update control could not have addressed.

## The content-matched placebo (2026-08-08)

`curriculum-placebo-v1` — structurally identical to `explained-v1` (533 rows,
90 injected at 18 distinct texts × 5, same system prompt, same stratum, 201
updates) with the prose about dataclasses, pathlib and itertools instead of
PEP 750. Three seeds, same recipe.

| arm | seeds 42/43/44 | mean | spread |
| --- | --- | --- | --- |
| baseline `repair-v2` (443 rows, 168 updates) | 54 / 58 / 48 | 53.3 | 10 |
| **placebo** (533 rows, 201 updates, unrelated prose) | 62 / 54 / 60 | **58.7** | 8 |
| **explained** (533 rows, 201 updates, PEP 750 prose) | 56 / 61 / 64 | **60.3** | 8 |

Decomposing the +7.0 I previously attributed to explanatory content:

| | |
| --- | --- |
| placebo − baseline (extra updates and/or prose register) | **+5.3** |
| **explained − placebo (PEP 750 knowledge, isolated)** | **+1.7** |
| explained − baseline (what was reported before) | +7.0 |

Paired, matched seed, explained vs placebo: −6 (p = 0.286), +7 (p = 0.189),
+4 (p = 0.523). No seed reaches significance and the sign is not even
consistent.

**Three quarters of the gain is not about t-strings.** Adding 90 rows of
verified true prose on *unrelated* Python topics captures most of it. The
spread also falls to 8 in both injected arms, so the stabilisation is not
specific to PEP 750 content either.

### What this settles, and what it costs

The corrected verdict from the previous round — "underpowered, direction
consistent, mechanism visible" — survives only in weakened form. The mechanism
evidence stands: `AttributeError` still halves, and 3 tasks still go 0/3 → 3/3.
But the *size* attributable to teaching the API is +1.7 on 100 tasks across
three seeds, which is indistinguishable from nothing at this power.

The likeliest reading is that most of what helped was **more optimizer steps
and a second register of prose**, not the API knowledge — the model benefits
from being trained on some question-answering at all, regardless of subject.

This is the control that should have been in the original design. It was
proposed by review, not by me; my own planned control (matched updates) would
have confirmed the update confound while leaving the prose-register
explanation untested, and I would have reported a knowledge effect that mostly
is not one.

### Still running

Seeds 45–47 on baseline and explained, taking both arms from 3 seeds to 6.
That halves the standard error on the difference and is the only thing that can
say whether +1.7 is real or zero. The placebo remains at 3 seeds.

## Six seeds: the final reading (2026-08-08)

Seeds 45–47 added to both arms, taking each from 3 to 6.

| arm | seeds 42–47 | mean | **sd** |
| --- | --- | --- | --- |
| baseline `repair-v2` | 54, 58, 48, 56, 61, 58 | 55.83 | **4.49** |
| `explained-v1` | 56, 61, 64, 57, 69, 58 | 60.83 | **4.96** |
| `placebo-v1` (3 seeds) | 62, 54, 60 | 58.67 | — |

### The primary hypothesis is refuted, now with power to say so

The registered hypothesis was that explanatory content *stabilises* what the
adapter learns. Measured properly — standard deviation over six seeds rather
than a range over three — **the explained arm is not more stable (4.96 against
4.49); it is marginally less.**

The 10 → 8 "fall" reported earlier was noise on a statistic that could not
support the question, exactly as review said. So was the observation that
motivated the experiment.

### The secondary effect does not reach significance, and most of it is not the content

Paired by seed: deltas **+2, +3, +16, +1, +8, 0**, mean **+5.00**, se 2.48,
**t = 2.02, df = 5, p = 0.100**. Doubling the seeds did not rescue it. The
distribution is also lopsided — one seed at +16 and two at ~0.

And the placebo splits that +5:

| | |
| --- | --- |
| placebo − baseline (more updates and/or any prose at all) | **+5.3** |
| **explained − placebo (PEP 750 knowledge, isolated)** | **+2.2** |

### Verdict

**Explanatory content is not established as doing anything.** The stabilisation
hypothesis is refuted; the level effect is p = 0.10 across six seeds and is
mostly reproduced by prose on unrelated topics.

What survives is narrower and worth keeping: adding *any* second register of
question-answering to a corpus of pure task/solution pairs is worth roughly
+5 tasks in 100, and the API-hallucination error class halves. Neither of those
is a claim about t-strings.

### Cost of the round

Three verdicts on one experiment: a false null, an over-corrected positive, and
this. The instrument was sound throughout — the movement was all inference. The
lesson that generalises is the one review supplied: **a control that holds
everything constant except the variable of interest settles in one run what
three rounds of statistics could not.** The placebo should have been in the
original design, and the pre-registration should have demanded it rather than
registering an unanswerable spread metric.

### Recorded as not run

- Placebo at seeds 45–47 (kept at 3; the explained-minus-placebo gap is well
  inside noise either way).
- Early stopping at the validation minimum — a different regime, deliberately
  not folded in.
- Qwen replication — the shipping question, untouched by this round.

## Qwen transfer test: ABANDONED, partial results on disk (2026-08-08)

Stopped by decision partway through. **The transfer question is unanswered.**
Three result files exist and must not be read as a completed test:

| file | what it is |
| --- | --- |
| `eval-v2-qwen-base.json` | bare Qwen, complete |
| `eval-v2-qwen-base-docs.json` | bare Qwen + docs, complete |
| `eval-v2-qwen-seed42.json` | adapter, **one seed only** |

The pre-registered rule (§4) requires the adapter to beat bare at **all three**
seeds. Seeds 43 and 44 were never trained. Deliberately not scoring the single
seed: a one-seed reading is exactly what the rule exists to prevent, and the
last round showed how one favourable seed can carry a story two others do not
support.

### Why it was stopped: the test could only half-answer

Both models have 28 layers and all 28 were adapted, so the flag matched — but
the resulting capacity did not:

| | trainable |
| --- | --- |
| Mellum2-12B (MoE) | **1.171%** — 142M of 12.1B |
| Qwen2.5-Coder-7B (dense) | **0.265%** — 20M of 7.6B |

The MoE exposes far more LoRA target modules per layer, so "all layers" gives
Qwen a 7× smaller adapter. A positive result would still have been decisive —
beating bare *despite* less capacity is strong. A null would have been
uninterpretable: corpus fitted to Mellum, insufficient capacity, and generation
degradation are not separable. Spending the time for an outcome that is only
informative in one direction was not worth it against the SP5 scale work.

This asymmetry should have been checked before launching, not after being asked
whether the run would help.

### One real finding that survives

The adapter makes Qwen **run on**, and it is not subtle:

| arm | mean/task | completions > 1500 chars |
| --- | --- | --- |
| bare | 2.6 s | **0 / 100** |
| bare + docs | 2.9 s | **0 / 100** |
| **+ adapter** | **21.7 s** | **41 / 100** |

Bare Qwen never produces a long completion; with the adapter, 41% do, at 8×
the latency. Mellum showed nothing comparable. Whatever transferred, it
included a length pathology — which is itself a transfer signal, and a reason
to be cautious about handing this corpus to a model it was not tuned against.

### Also not run

The three `+docs` adapter arms were cut mid-run. They were pre-registered as
not a metric, and at ~36 minutes each they were over half the runtime.
