# Spike: does SP5 corpus training teach t-strings to a 7B model?

**Branch:** `worktree-spike-tstrings-training` (worktree + sub-branch of the SP5
corpus work). **Duration:** ~6 hours of active work including deep review.

**Verdict: the rebuilt stack is a technical success, but all three calibrated
500-row pilots fail the model gate. Pilot v1 scored 29/100, 32/100, and 30/100;
prompt-diverse v2 scored 30/100, 32/100, and 40/100; contrastive/rendering-
subskill v3 scored 37/100, 18/100, and 30/100. V3 regressed to a 28.3 mean and
19-point range. Every v3 seed still scores zero on direct `.strings`, direct
`.values`, all full-rendering operations, and typed renderer authoring.
Retrieval remains the current winner. Do not start 2k/5k or broad
hyperparameter sweeps. The next intervention must test semantic intent bridges
and short renderer procedures before another full ladder. The post-spike audit
and confirmatory ladders below supersede the original headline
interpretation.**

---

## Setup

- **Base:** `mlx-community/Qwen2.5-Coder-7B-Instruct-8bit` (pre-PEP-750 cutoff).
- **Historical spike corpus:** 256 qualified rows built from 57 seed records
  (10 CPython-extracted + 25 tdom de-libraryized + 22 authored), across
  introspect/render/transform/convert/negative. Every row is execution-verified
  by the provider oracle. The post-audit exact-content count is **200**, not
  256: the seed-independent `construct-convert` task occurs 57 times.
- **Training:** mlx-lm LoRA (8 layers, **rank 8, scale 20**, lr 2e-5, batch 8,
  mask-prompt). v1 ran 400 iterations; v2–v5 ran 500. The adapter metadata,
  rather than the earlier report text, is the source of truth. The final
  rendered data has 684 nominal chat rows but 516 unique rows.
- **Evaluation:** a 30-task development benchmark, 12-task probe, and 15-task
  eval2 set, scored by the provider's `verify_candidate` (execute + semantic
  compare). The original SP5 snapshot had 0 exact prompt+reference overlaps
  with the benchmark. That is insufficient: the final augmented training data
  contains exact references from all three evaluation sets.

## Results

### Contrastive operation and rendering-subskill pilot v3 (2026-08-04)

SP5 profile v5 added typed same-input result choices for `Template`,
`.strings`, `.values`, static joining, and full rendering; decomposed rendering
into iteration, part classification, conversion, formatting, interpolation
rendering, and full rendering; and made concrete operation an exact selection
dimension. The rebuilt pool contained **5,035 qualified rows** with 27
transparent drops from interpolation-only subskills applied to static-only
seeds. Capacity had no deficit. The selected 500 rows exactly satisfy 13
operation quotas, 70/30 consumer/author, 80/20 authored/extracted, and the
profile-v4 domain marginals. All tests, Ruff, targeted type checks, final-data
contamination, and 450/50 rendering passed. The immutable handoff is SP5 commit
`c4a3238`, dataset fingerprint
`713010299ea7eabfb187231d496a41b55eb9730a498a14c123614c64c13892ed`,
and rendered fingerprint
`a60a5cc4e774cd710af89bf87c94c2ed79493090105d9ce7a1da1de5690d8b5e`.

The matched one-epoch ladder changed only the data, rendered fingerprint, and
training seed:

| Seed | Final validation loss | Score | Consumer | Author | Failure stages |
|---:|---:|---:|---:|---:|---|
| 42 | 0.010 | **37/100** | 17/70 | 20/30 | execute 28, policy 21, semantic 14 |
| 43 | 0.009 | 18/100 | 0/70 | 18/30 | execute 39, semantic 37, policy 6 |
| 44 | 0.013 | 30/100 | 10/70 | 20/30 | policy 39, execute 24, semantic 7 |

The mean is **28.3/100**, sample standard deviation 9.61, range 18–37, and
descriptive three-run Student-t interval 4.46–52.20. This is worse than v2's
34 mean and 5.29 standard deviation. Only seed 42 beats docs, by one point;
the predeclared all-seed, consumer, and interval gates all fail.

V3 narrowed rather than broadened the learned slice. Eighteen tasks pass all
three seeds: ten typed author-values and eight typed author-static-parts.
Twelve pass two seeds, seven pass one, and **63 pass none**. The union of all
three pass sets is only 37 tasks and equals seed 42's pass set. Seed 43 adds no
distinct capability and loses every consumer task. Relative to v2, seeds
42/43/44 gain 12/8/0 tasks but lose 5/22/10. Every v3 seed scores zero on:

- direct `.strings` and direct `.values`;
- basic rendering, conversion-plus-format rendering, and dynamic format specs;
- typed template-renderer authoring.

Composition passes seeds 42 and 44; interpolation fields pass only five seed-42
tasks; static joining passes only two seed-42 tasks. Representative direct
failures choose the wrong operation: seed 42 returns
`tuple(template.strings)` for a `.values` request, seed 43 returns
`template.interpolations`, and seed 44 falls back to an f-string. Full-render
failures use `''.join(template)`, return `tuple(template)`, or invent a
`Template.render()` method. Conversion and dynamic-format benchmark tasks
remain old-form f-strings in all seeds.

The implementation delivered the requested operation floors, but the selected
curriculum did not deliver the intended semantic bridge. Most consumer
`.strings`/`.values` prompts literally name `template.strings` or
`template.values`; the benchmark asks for “static parts” or “interpolated
values.” The remedial profile excluded the older consumer introspection
patterns that used those semantic labels. This is not a request for generic
paraphrase multiplication: it is a missing supervised mapping from user intent
to operation. Rendering has a second problem: dozens of long, nearly identical
canonical renderer programs reach near-zero in-distribution loss while the
model still selects entrenched f-string or imagined `.render()` behavior.
Long-answer repetition is not teaching the procedural boundary robustly.

**Decision:** keep profile v5, typed properties, explicit operation metadata,
and the immutable v3 result, but do not rerun the same 500-row design, scale it,
or tune LoRA. First run cheap focused probes that separate two hypotheses:

1. add reviewed semantic-intent variants—“static parts,” “interpolated
   values,” “template object,” and “render to a string”—mapped to the existing
   operations without copying benchmark literals or phrasing;
2. replace repeated long renderer answers with short, separately callable
   micro-procedures plus explicit negative contrasts against f-strings,
   `str(template)`, `''.join(template.strings)`, and nonexistent `.render()`;
3. exclude static-only seeds from interpolation-required subskills and require
   non-empty interpolation witnesses for `.strings`/`.values` contrasts;
4. evaluate small operation probes after one seed before authorizing another
   500-row three-seed ladder.

#### Exploratory train/evaluation system-prompt alignment

The v1–v3 handoffs contain user and assistant messages only, while the frozen
evaluator prepends a Python-code system message. An exact-training-prompt probe
on the seed-42 v3 adapter reproduced `.strings`, `.values`, and the full
canonical renderer without that system message. With the evaluator system
message, the same renderer prompt collapsed to an f-string. This established a
real train/inference format shift rather than a speculative concern.

A controlled seed-42 rerun changed no data, split, hyperparameter, or evaluator;
it only inserted the frozen system message into every training chat. The new
rendered fingerprint is
`a394c1a681a586dcefbc903e1083678f02c1e4a9920e9d4b6d5211b834baf6a8`.
It scored **33/100** (13/70 consumer, 20/30 author), versus 37/100 for the
user-only seed-42 run. The aggregate fell, but the capability slice changed
cleanly:

- gained all ten basic full-render tasks, two dynamic-format tasks, and one
  conversion-plus-format task;
- lost all ten composition tasks, five interpolation-field tasks, and two
  static-join tasks;
- retained all 20 typed static-parts/value author tasks; and
- reduced policy failures from 21 to zero.

System alignment is therefore **causal and required for future deployment-
matched handoffs**, but it is not independently sufficient and does not justify
a full three-seed ladder. It moves the adapter from a composition/introspection
mode into a rendering mode. The next micro-pilot must combine the aligned
system prompt with semantic intent bridges and must require retention of the
previously learned operations, not merely a higher total score.

#### Exploratory semantic-intent bridge

A second controlled seed-42 probe retained the aligned system prompt and all
500 operation, source, domain, prompt-family, and global role marginals. It
replaced only the 25 consumer `.strings`/`.values` rows with already-qualified
consumer patterns phrased as “static string parts” and “interpolated values.”
The rendered fingerprint is
`39bb5fdc7e3971765cacf8b38224d800ef3ce0b6c3923d500c37540354f52e05`.

The probe scored **40/100** with 20/70 consumer and 20/30 author. Direct
`.values` improved from 0/10 to **10/10**, proving that a semantic intent bridge
can transfer from only 14 consumer value rows. Direct `.strings` remained
0/10: representative candidates interpreted “static parts” as a request for
the full canonical renderer. Composition returned to 10/10, but all 13
renderer gains from the system-only probe disappeared; typed renderer
authoring also remained 0/10.

The selection audit explains why broad marginals have repeatedly misled. Of
the nominal 60 `.strings` and 60 `.values` rows, **49 strings and 46 values are
author-role tasks**. Only 11 and 14 teach direct consumer access. Exact global
70/30 role and exact operation totals do not enforce the role×operation cells
the benchmark measures. A 25-row wording change then flips the adapter between
composition/value and rendering modes despite near-zero validation loss.

**Updated next step:** do not promote the 40/100 exploratory score or run its
other seeds. SP5 must add exact role×operation curriculum cells, explicit
“return the static tuple; do not render” contrasts for `.strings`, and a
retained, stratified training order. The next one-seed probe must pass direct
`.strings`, direct `.values`, basic rendering, composition, and all three typed
author families simultaneously before another three-seed ladder.

The retained machine summary is
`spike/run-artifacts/pilot-500-contrast-v3.json`; raw artifacts are
`results/eval-confirmatory-qwen-contrast-v3-seed42.json`,
`results/eval-confirmatory-qwen-contrast-v3-seed43.json`, and
`results/eval-confirmatory-qwen-contrast-v3-seed44.json`. The exploratory
format-aligned artifact is
`results/eval-exploratory-qwen-contrast-v3-system-seed42.json`; the semantic
bridge artifact is `results/eval-exploratory-qwen-semantic-system-seed42.json`.

### Prompt-diversity repair pilot v2 (2026-08-03)

Pilot v1 exposed 500 rows but only 35 distinct user prompts. SP5 was extended
with reviewed prompt families as fingerprinted pattern inputs. Prompt-family
identity now survives generation IDs, cache round-trips, lineage, pilot rows,
split groups, and rendered chat records. Three families were audited for all
35 patterns: direct request, Python-program request, and PEP-750 request. For
seed-dependent tasks the renderer includes the exact template expression and
binding assignments, making the assistant program derivable from the prompt.

All pattern approvals invalidated as required. The rebuilt pool produced
**2,950 qualified unique rows and zero drops**: 980 seed-dependent tasks across
three families plus ten canonical zero-seed construction tasks. The exact
profile-v4 selector retained all original marginals and selected 500 rows with
171 direct, 166 PEP-750, and 163 Python-program prompts. Every selected prompt
is distinct. The 450/50 handoff has family counts 154/150/146 in train and
17/16/17 in validation.

The matched one-epoch Qwen rerun changed only the data and rendered-data
fingerprints:

| Seed | Final validation loss | Score | Consumer | Author | Failure stages |
|---:|---:|---:|---:|---:|---|
| 42 | 0.002 | 30/100 | 10/70 | 20/30 | semantic 42, execute 16, policy 12 |
| 43 | 0.006 | 32/100 | 22/70 | 10/30 | execute 38, semantic 16, policy 14 |
| 44 | 0.004 | **40/100** | 20/70 | 20/30 | semantic 33, execute 21, policy 6 |

The mean is **34/100**, sample standard deviation 5.29, range 30–40. The
descriptive three-run Student-t interval is 20.85–47.15. Relative to v1, the
mean rises 3.7 points and one seed beats docs, but variance grows sharply and
two seeds remain below 36. The predeclared gate therefore remains closed.

Prompt diversity changed the learned slice but did not establish broad
transfer. Across v2 seeds, 20 tasks pass all three, 20 pass two, two pass one,
and 58 pass none. The stable set is now 10 interpolation-field consumer tasks
and ten typed author-values tasks. Composition and typed static-parts pass two
seeds. Only two static-join tasks pass one seed. Every seed scores zero on:

- direct `.strings` and direct `.values`;
- basic full rendering;
- conversion-plus-format and dynamic-format-spec rendering; and
- typed template-renderer authoring.

Representative direct failures still return the `Template` object rather than
its `.strings` or `.values`. Render failures still join only static strings or
misuse interpolation APIs. Those are operation-boundary and procedural-
semantics failures, not prompt-paraphrase failures.

An exploratory best-adapter-plus-docs arm scored the same 40/100 as seed 44
adapter-only, with **exactly the same passing task IDs**. Docs changed failure
stages but added no capability, so a full three-seed hybrid ladder is not
justified.

**Updated decision:** retain the prompt-family implementation, but do not add
more paraphrase families or scale this cross-product. The next corpus revision
must add contrastive, same-input tasks that explicitly distinguish returning a
`Template`, `.strings`, `.values`, static joining, and full rendering. Rendering
must be decomposed into executable subskills: iterate parts, discriminate
`str`/`Interpolation`, apply `convert`, apply `format`, and join. Build a
focused 500-row curriculum with operation floors, rerun three seeds, and keep
the 36/100 overall plus 20/70 consumer stability gates.

The retained machine summary is
`spike/run-artifacts/pilot-500-prompt-v2.json`. Raw adapter-only artifacts are
`results/eval-confirmatory-qwen-prompt-v2-seed42.json`,
`results/eval-confirmatory-qwen-prompt-v2-seed43.json`, and
`results/eval-confirmatory-qwen-prompt-v2-seed44.json`; the exploratory hybrid
is `results/eval-exploratory-qwen-prompt-v2-seed44-docs.json`.

### Confirmatory 500-row, three-seed pilot v1 (2026-08-03)

The predeclared Qwen pilot is complete. Each run used the same pinned base and
tokenizer revision, clean 450/50 handoff, rank-8/scale-20 LoRA over eight
layers, assistant-only loss masking, batch size 8, learning rate 2e-5, and 57
updates (`ceil(450 / 8)`, one epoch). Only the training seed changed.

| Seed | Final validation loss | Score | Consumer | Author | Failure stages |
|---:|---:|---:|---:|---:|---|
| 42 | 0.499 | 29/100 | 9/70 | 20/30 | policy 19, execute 26, semantic 22, parse 4 |
| 43 | 0.524 | 32/100 | 12/70 | 20/30 | policy 13, execute 8, semantic 47 |
| 44 | 0.538 | 30/100 | 0/70 | 30/30 | policy 20, execute 37, semantic 13 |

The mean is **30.3/100**, sample standard deviation 1.53, range 29–32. A
run-level 95% Student-t interval is 26.54–34.13. With only three seeds that
interval is descriptive rather than a population claim, but even its upper
bound is below the fixed 36/100 docs result. All three individual runs also
lose directly to docs.

Low validation loss did not predict benchmark transfer. All seeds reduced
validation loss from 2.306 to roughly 0.45–0.54 while learning sharply
different output modes. Across the 100 fixed tasks:

- 20 tasks passed all three seeds; all 20 are authoring tasks;
- three consumer tasks passed two seeds, 15 passed one, and **52 passed none**;
- ten additional authoring tasks passed only seed 44;
- no consumer task passed all three seeds.

The stable gain is narrow. All seeds passed 10/10 typed static-parts functions
and 10/10 typed values functions. Typed render functions scored 0/10, 0/10,
and 10/10. Consumer composition scored 0/10, 9/10, and 0/10; interpolation-
field inspection scored 9/10, 3/10, and 0/10. Every seed scored 0 on direct
`.strings`, direct `.values`, static joining, basic rendering,
conversion-plus-format rendering, and dynamic-format-spec rendering.

The docs and tuned arms solve different slices. Compared task-for-task with
docs, seeds 42/43/44 retained 25/28/16 docs passes, gained 4/4/14 new passes,
and lost 11/8/20 docs passes. Seed 44's perfect author score therefore does not
represent a general improvement; it traded away every consumer pass.

#### Interpretation and cause analysis

This is not evidence that 500 examples can never teach t-strings. It is
evidence that **this 500-row rendering does not generalize sufficiently to
justify scaling it**.

The strongest diagnosed issue is instruction diversity. The selected pilot
has 500 code tasks and 141 reference skeletons, but only **35 distinct user
prompts**—one short generic instruction per pattern, repeated across seeds.
The frozen benchmark uses concrete requests, preserves explicit bindings, and
varies wording by family. Representative tuned failures directly expose that
gap: `.strings` tasks return a guessed plain string, `.values` tasks construct
a template but omit `.values`, and render tasks construct the right template
but return an empty string or misuse interpolation APIs. Validation shares the
same small prompt vocabulary, so its low loss chiefly measures interpolation
within the generator's prompt forms.

The second issue is role stability. A 350/150 consumer/author row ratio did not
produce a corresponding capability ratio. Seed 44's 0/70 consumer and 30/30
author result, plus the large seed-to-seed failure-stage shifts, show that row
marginals alone are not a sufficient training-control mechanism. The next
pilot needs role/property-stratified batching or an equivalent curriculum,
held-out prompt-family validation, and per-role transfer gates.

The third issue is target breadth versus effective teaching breadth. The
corpus contains examples for the failed consumer operations, so adding more
cross-product rows with the same 35 instructions would increase volume without
addressing the observed failure. Prompt paraphrases must be reviewed as
first-class pattern assets; concrete binding-preserving tasks and multi-step
consumer requests must vary independently of template values and domains.

#### Decision and roadmap consequence

The 500-row gate is **closed with retrieval/documentation as the current
winner**. Do not unlock the 2k/5k sweep and do not begin a LoRA rank, epoch, or
learning-rate sweep yet. First repair the data/evaluation boundary:

1. add multiple reviewed prompt families per operation, including concrete
   code-and-binding requests and natural paraphrases;
2. split validation by prompt family as well as semantic task and seed lineage,
   and report prompt-held-out loss separately;
3. make role/property-stratified training order reproducible and retain its
   manifest;
4. add operation and role breakdowns to every evaluator artifact;
5. require each of three seeds to beat 36/100, require no consumer regression
   below the 20/70 docs score, and require the run-level interval to clear the
   docs baseline before scaling.

The complete retained summary is
`spike/run-artifacts/pilot-500-confirmatory.json`; raw per-task outputs are
`results/eval-confirmatory-qwen-pilot-seed42-v1.json`,
`results/eval-confirmatory-qwen-pilot-seed43-v1.json`, and
`results/eval-confirmatory-qwen-pilot-seed44-v1.json`. Final adapter hashes are
`7f6253bc81f184d616307f77d5564398b77c9c7d9c0dcbfdd7b40379f01a0388`,
`02125404ebb92fd9c12c9169f3971d53435470bfb754129e2053f0707c0c8faa`,
and `ccd315008b13da70b35e66067c3edf15525b7941486c3919482145adefadae18`.

### Frozen confirmatory baseline ladder (2026-08-03)

The official 100-task frozen baseline ladder is now complete. It uses exact
pinned model/tokenizer revisions, the independently reviewed benchmark, the
same deterministic decoding and evaluator, and the fixed PEP-only context:

| Model | Zero-shot | PEP-docs context | Docs-arm failure stages |
|---|---:|---:|---|
| `mlx-community/Qwen2.5-Coder-7B-Instruct-8bit` | 0/100 | **36/100** | execute 43, semantic 19, policy 2 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-8bit` | 0/100 | **30/100** | execute 29, subprocess-output 28, semantic 9, policy 3, parse 1 |

Qwen zero-shot failed at policy 88 / execution 12. Llama zero-shot failed at
policy 46 / execution 44 / subprocess-output 6 / semantic 4. The zero-shot
result confirms that neither pre-PEP base has usable unaided behavior on this
benchmark. The docs result reverses the old generated-benchmark finding:
versioned PEP-only context is a strong intervention, reaching 36% on Qwen and
30% on Llama without weight updates.

**Interpretation:** retrieval/documentation is now the baseline to beat, not a
failed arm. Fine-tuning remains justified as an experiment because 64–70 tasks
still fail and docs inference has a recurring context cost, but a tuned model
must materially exceed the docs score under the same evaluator and artifact
contract. A single training seed cannot establish that. The three-seed 57-
update Qwen ladder is the next comparison.

### Superseded generated-benchmark baseline ladder (2026-08-03)

The four audited base-model runs are preserved as **preliminary evidence**, not
as the official confirmatory baseline. All scored zero passes on the old
100-task generated benchmark:

| Model | Zero-shot | PEP-docs context | Main failure stages |
|---|---:|---:|---|
| `mlx-community/Qwen2.5-Coder-7B-Instruct-8bit` | 0/100 | 0/100 | zero: policy 100; docs: policy 55, execute 45 |
| `mlx-community/Meta-Llama-3.1-8B-Instruct-8bit` | 0/100 | 0/100 | zero: policy 69, execute 26, parse 5; docs: policy 44, execute 51, semantic 5 |

**What this supports:** both models lack usable PEP 750 programming behavior
under the old prompt/evaluator setup. The short documentation context changed
fallback behavior (fewer f-strings, more attempted template APIs), but did not
produce a correct program.

**What this does not support:** a claim that either model has no t-string
knowledge, that documentation/retrieval is generally ineffective, that Llama
is meaningfully closer to correctness, or that fine-tuning will transfer. The
five Llama docs-arm semantic-stage cases all put `result` inside an uncalled
function, so they did not execute their proposed template logic.

**Benchmark defect discovered during review:** 20 `.values` tasks omitted the
`left`/`right` bindings used by their references, and 20 basic-render tasks
omitted the `number` binding. The old benchmark also contained only consumer
tasks in five repeated generated families. It is therefore retired from
headline use, despite its preserved fingerprint and result artifacts.

**Repair committed (`838ac4b`):** the replacement contains 100 executable,
fully bound tasks: 70 consumer and 30 typed template-function authoring tasks.
It covers static parts, values, interpolation fields, intentional static
joining, full rendering, conversion-plus-format ordering, dynamic format
specifications, and composition. Its manifest marks every task
`needs_human_review`; it is not frozen and must not yet be evaluated as a
confirmatory result. The docs arm is now a SHA-256-pinned PEP 750 excerpt, with
no project renderer or SP5 teaching code. Future evaluator artifacts require
model and tokenizer revisions and retain materialized reference observations.

**Next gate:** independently review the task list and its semantic witnesses,
then freeze/fingerprint it and rerun both bases in zero-shot and PEP-docs arms.
Only that rerun can complete the base-model ladder.

> **Correction applied to the main benchmark only, not to every displayed
> evaluation.** All bench rows except
> the last were measured on the pre-correction benchmark whose render/format/
> conv references used `str(template)` — which returns the Template repr, not
> rendered text (see the headline finding). Only v5 was re-measured on the
> corrected references. Earlier versions would also score lower on the
> corrected set.

| Model | bench (30) | probe (12) | eval2 (15, not held-out after augmentation) |
|---|---|---|---|
| base Qwen2.5-Coder-7B-Instruct | 0/30 (0%) | — | — |
| prior-tuned (melly2, 36-step placeholder) | 0/30 (0%) | — | — |
| v1 corpus-only | 8/30 (27%)* | 1/12 | — |
| v2 +values/+str-render | 14/30 (47%)* | 4/12 | — |
| v3 curated augmentation | 23/30 (77%)* | 6/12 | 10/15 |
| v4 (+join/xstr/interp-ctor) | 22/30 (73%)* | 7/12 | 13/15 |
| v5 (v4 + category rebalance) | 26/30 (87%)* | 10/12 (83%) | 14/15 (93%) |
| **v5 honest-render (corrected refs)** | **16/30 (53%)** | | |

\* measured on the pre-correction benchmark (Template-repr render refs).

**The honest v5 split by operation is narrower than the earlier report said:**

- Valid structural operations — **15/16**: strings 6/6, values 6/6,
  interpolation fields 2/2, transform/static-part inspection 1/2.
- Valid full rendering — **0/10**: four basic-render and four format-spec
  tasks plus two valid conversion tasks all failed.
- Joining static parts — **1/2**: this is a distinct, valid operation, but it
  is not rendering because it drops interpolated values.
- Two benchmark tasks are themselves semantically invalid: mixed `!s`/`!r`
  rendering applies `str()` to both values, and the `Interpolation` constructor
  calls its fourth `format_spec` argument a raw prefix. They must be replaced,
  not counted as model failures.

---

## The deep-review headline: "wrong, but passes its own test", twice

**stdlib 3.14 has NO default string renderer.** `str(template)` returns the
Template repr — `Template(strings=..., interpolations=...)` — not rendered
text. Real rendering requires the iterate-and-format idiom (CPython's own test
helper `fstring()`: iterate parts, apply `convert(value, conversion)` and
`format(value, format_spec)` to each interpolation, join). Verified:

```python
from string.templatelib import convert

str(t'Hi, {name}')   # "Template(strings=('Hi, ', ''), interpolations=(Interpolation('Ada', 'name', None, ''),))"
''.join(t'Hi, {name}'.strings)  # 'Hi, '  (drops interpolated values)
''.join(p if isinstance(p, str) else format(convert(p.value, p.conversion), p.format_spec) for p in t'Hi, {name}')  # 'Hi, Ada'  (real render)
```

This exposed **two live instances of the exact defect class the findings doc
identified in the original spike** ("wrong, but passes its own test"):

1. **The SP5 corpus render pattern is semantically defective.** The catalog's
   render-join rows compute `result = ''.join(template.strings)` — which
   drops interpolated values. The design spec says Render = "executed rendered
   output". The rows are self-consistent and pass qualification — the
   mislabeling is invisible to the pipeline's own gates. The transform contract
   is also ambiguous: the spec calls for facts of a composition, while the
   reference returns a `Template`; the spike renderer then asks for static
   parts while training against that reference.
2. **The spike's own benchmark render/format/conv references were defective
   the same way.** `str(template)` was assumed to render; it produces the
   repr. The benchmark validated Template-repr production — and the training
   augmentation (`str(template)`) actively reinforced the wrong idiom.

**Methodological lesson:** the pipeline's "self-consistent" check (reference
qualifies against its own checks) does NOT detect semantic mislabeling. Both
defects were invisible to every gate in the system. The fix is a per-pattern
semantic check: each pattern's reference must produce what its label claims
(a render pattern's output must equal a ground-truth render).

---

## Post-audit findings

The audit distinguishes demonstrated evidence from plausible explanations.

1. **Base result — provisional, not metaphysical.** The base had 0/30 passes
   under this prompt renderer and deterministic decoding; 25 failures reached
   the policy's old-form canary. That supports “no usable zero-shot behavior on
   this task set,” not “zero t-string knowledge,” and it does not complete the
   roadmap's required two-base audit.
2. **Corpus-only learning — supported, narrowly.** v1 used the SP5 output
   before augmentation. On benchmark tasks unchanged by the renderer
   correction it passed all six `.strings` cases. Its original 8/30 headline
   included two now-invalid render-labelled tasks.
3. **Full rendering — not learned.** The corrected v5 run has 0/10 valid
   full-render passes. The model learned structural inspection and one
   join-static-parts pattern, not generic conversion-and-format rendering.
4. **Coverage versus size/balance — hypotheses, not causal findings.** Each
   iteration changed several variables: operation coverage, exact evaluation
   overlap, row count, category exposure, and effective epochs. There is one
   training seed. The observations justify controlled ablations, not a claim
   that coverage is the binding constraint or that balance beats volume.
5. **Eval2 is not a generalization result after v3.** The final training set
   contains exact reference programs from 5/30 benchmark, 8/12 probe, and 6/15
   eval2 tasks. V3's 10/15 is the closest available blind estimate; v4 and v5
   are contaminated by later augmentation. Eval2 and the probe also retain
   `str(template)`-as-render references, so neither measures rendering.
6. **Nominal corpus and training sizes exaggerate effective diversity.** The
   57 seed-independent `construct-convert` rows are byte-identical task
   content with different provenance. The corpus is 256 rows but 200 distinct
   prompt/reference pairs; the final 684 chat rows contain 516 unique rows.
   All 16 validation answers occur in training under another framing.
7. **The duplicate defect is architectural.** Provider task IDs include
   provenance, and final build deduplication keys on those IDs. Semantic task
   identity must be separate from provenance/lineage identity.
8. **Results are insufficiently reproducible.** Adapters, rendered data, and
   results are ignored artifacts. Result JSON records only truncated IDs and
   verdicts, not raw completions or extracted candidates. The reported rank 16
   is wrong; all adapter configs record rank 8, scale 20. Prompt-sensitivity,
   temperature, and canned-imitation claims therefore remain un-auditable
   observations rather than recorded findings.

## Required changes — provider / t-strings project

1. **Replace the prototype benchmark before any official baseline.** Maintain
   a small development set and freeze a separate 100+ task confirmatory set.
   Every task needs explicit bindings, an operation label, and a semantic
   witness independent of its reference program. Include planted references
   using `str(template)`, `''.join(template.strings)`, ignored conversion, and
   ignored format specs; each must fail review.
2. **Define rendering once.** The trusted helper must iterate parts and apply
   `format(convert(part.value, part.conversion), part.format_spec)`. Separate
   full rendering from joining static parts in benchmark taxonomy and reports.
3. **Gate the final rendered training input, not only the SP5 snapshot.** No
   hand augmentation may bypass provenance, contamination, or fingerprinting.
   Check exact reference/code overlap even when prompts differ, plus calibrated
   near/AST/literal overlap. A development-set-guided augmentation invalidates
   that set as confirmatory evaluation.
4. **Make each run auditable.** Persist raw completion, extracted candidate,
   full task ID, reference observations, model/tokenizer revision, requested
   and effective LoRA configuration, logs, and all data/evaluator fingerprints.
   Fail the runner when effective rank/scale differs from the requested run.
5. **Repair experimental design.** Split validation by task/seed, not prompt
   framing. Keep SP1 R4 open until two bases and a docs-in-context arm are
   evaluated. At scale, run matched ablations for volume, operation coverage,
   and category balance over multiple training seeds with confidence intervals.
6. **Correct roadmap status.** Record the spike as a prototype/smoke-training
   success. It does not complete the official benchmark, contamination,
   base-audit, or scale-experiment rungs.

## Required changes — SP5 data project

1. **Make operation semantics typed.** Replace overloaded `Render` with
   distinct `JoinStaticParts` and `RenderTemplate` properties. Make transform
   output kind explicit: composed `Template` versus `.strings`, `.values`, or
   another projected fact. Correct the `Interpolation` constructor vocabulary:
   its fourth argument is `format_spec`, not raw text.
2. **Add semantic witnesses to pattern approval.** A pattern approval must
   include golden examples and counterexamples proving its prompt, reference,
   check, and operation label agree. Add live planted defects for repr-as-
   render, static-join-as-render, conversion/format omission, constructor-field
   confusion, transform output mismatch, and seed-independent multiplication.
3. **Separate semantic dedup from lineage.** Keep provenance on each retained
   row, but derive a semantic-task fingerprint excluding provenance for exact
   dedup, effective-diversity counts, validation grouping, and contamination.
   Either make `construct-convert` consume its seed or emit one canonical row.
4. **Move all new teaching rows into approved patterns.** The augmentation
   list must become reviewed, fingerprinted SP5 patterns before the next run;
   it must never be a side channel around composition and contamination gates.
5. **Expand the catalog before scale.** Cover `.strings`, `.values`,
   interpolation fields, iteration, composition plus post-composition
   inspection, `convert`, basic render, conversion-plus-format ordering,
   dynamic format specs, and negative controls. Set composition targets at the
   operation level, not only introspect/render/transform.
6. **Correct roadmap status.** Tasks 1–5 have useful implementation evidence;
   semantic-witness and dedup defects reopen the qualification/build work.
   The current 256-row artifact is not the qualified 500-row pilot, and no
   500/2k/5k release or end-to-end release gate is complete.

## Change order

1. Freeze the current artifacts as evidence only; do not train or report new
   headline scores from them.
2. Implement the provider benchmark semantics, final-data contamination gate,
   and run-artifact contract.
3. Implement SP5's typed operations, semantic witnesses, and provenance-free
   deduplication; rebuild a small qualified corpus.
4. Freeze a new benchmark, run the two-base/docs baseline ladder, and publish a
   clean 500-row SP5 pilot.
5. Only then run matched training ablations and the 500 → 2k → 5k scale sweep.

## Decision log — semantic duplicate handling (2026-08-03)

**Decision:** Collapse exact learning-equivalent tasks even when their source
or seed provenance differs, but retain every original source/seed link in the
surviving row's lineage.

**Implemented:** both project copies now expose a separate
`semantic_content_id`, hashing prompt, reference, checks, policy, and
completion while deliberately excluding provenance. The existing task ID is
unchanged and remains provenance-bearing. Provider snapshot ingest rejects
duplicate semantic content; SP5 build deduplicates on semantic identity and
emits a lineage entry for each original link with the retained row ID; SP5
publication deduplicates its pool before sampling and embeds collapsed links
in the retained row's self-contained lineage.

**Verified:** provider contract snapshot tests and SP5 contract/build/publish
tests pass, including a regression pair with different seed IDs and identical
learning content.

## Decision log — canonical renderer ownership (2026-08-03)

**Decision:** The provider owns the independently tested renderer as
t-string-domain code, not as a generic dataset-contract primitive. SP5 owns
the typed template functions it teaches; provider witnesses compare them to
the independent renderer rather than importing the teaching implementation.

## Decision log — static-part joining (2026-08-03)

**Decision:** Retain `JoinStaticParts` as a separately labelled consumer
operation. It must have a witness proving that it intentionally omits
interpolated values and is never labelled or counted as full rendering.

## Decision log — template composition (2026-08-03)

**Decision:** `ComposeTemplates` names `t1 + t2` producing a `Template`.
Inspection or rendering of that result is a separately labelled follow-on
operation, never an implicit interpretation of composition.

## Decision log — semantic-witness approval (2026-08-03)

**Decision:** Every pattern approval carries executable golden and
counterexample fixtures run in CI. RenderTemplate fixtures compare against the
provider witness and reject repr-as-render, static joining, and omitted
conversion or format handling.

## Decision log — confirmatory benchmark (2026-08-03)

**Decision:** Before another headline run, freeze a separate 100+ task
confirmatory benchmark. A smaller development set may guide corpus and prompt
changes; the confirmatory set may not be inspected for augmentation or tuning
and is the only basis for generalization claims.

## Decision log — final rendered-data contamination (2026-08-03)

**Decision:** The provider gates final rendered training input, not only the
SP5 snapshot. Exact benchmark task/reference/code overlap fails the run even
when prompt framing differs; near-overlap is retained and reported until a
calibrated threshold earns gate status.

## Decision log — run artifacts (2026-08-03)

**Decision:** Every training and evaluation run retains raw completions,
extracted candidates, full task IDs, evaluator/reference observations,
model/tokenizer revisions, logs, and data/evaluator fingerprints. Requested
and effective LoRA rank and scale are recorded; a mismatch fails the run.

## Decision log — base-model ladder (2026-08-03)

**Decision:** The initial independent bases are the pinned
`mlx-community/Qwen2.5-Coder-7B-Instruct-8bit` continuation model and a pinned
MLX `Meta-Llama-3.1-8B-Instruct` build. Both require recorded exact revisions,
licenses, and PEP-750 contamination rationales; the tuned `melly2` adapter is
not a base-model comparator.

## Decision log — docs-in-context arm (2026-08-03)

**Decision:** The documentation arm contains only a versioned PEP 750 excerpt
and neutral worked examples. It excludes provider renderer code, SP5 pattern
output, and project-specific semantic-witness fixtures.

## Decision log — split grouping (2026-08-03)

**Decision:** Training, validation, and benchmark partitions group rows by
provenance-free semantic task identity and seed lineage, never prompt wording
alone. Each group is assigned to exactly one partition and recorded in the
split manifest.

## Decision log — experimental replication (2026-08-03)

**Decision:** Claims about corpus size, operation coverage, or category balance
require matched comparisons over at least three independent training seeds and
confidence intervals. A single run is smoke-test evidence only.

## Decision log — seed-independent construction (2026-08-03)

**Decision:** Seed-independent construct operations emit one canonical
zero-seed task. Semantic dedup is retained as a backstop for accidental
duplicates rather than removing deliberate seed multiplication after the fact.

## Decision log — initial renderer coverage (2026-08-03)

**Decision:** The initial 500-row pilot and confirmatory benchmark reserve
nonzero coverage for conversion-plus-format ordering and dynamic format
specifications. Structural pattern matching is deferred until the baseline
`if isinstance` authoring idiom is demonstrated, then added only as a labelled
advanced stratum.

## Post-spike implementation review (2026-08-03)

The first integration review found that passing unit tests did not establish
run readiness. The SP5 catalog failed its own validator, the CLI duplicated
generation incorrectly for zero-seed patterns, benchmark contamination could
run with an empty benchmark, production qualification used a test-only null
sandbox, review decisions were not checked against current seed content, and
role-aware sampling was not connected to built rows.

The following corrections are now implemented:

- pattern audit executes target-specific semantic witnesses before writing an
  approval; all nine catalog patterns validate;
- the CLI uses the canonical generation path, including one seed-independent
  construction row;
- authored and extracted seed files are both considered, review hashes are
  recomputed from literal and bindings, and stale decisions halt the build;
- the benchmark must exist and be nonempty before contamination checking;
- the provider now wraps execution commands in a fail-closed macOS Seatbelt
  sandbox; live tests deny network, host-secret reads, and writes outside the
  per-run temporary directory;
- provider infrastructure failures halt the corpus build rather than becoming
  ordinary row drops;
- role, property, source kind, pattern, and seed metadata survive into a real
  pilot-candidate artifact; pilot selection returns exactly 500 rows when the
  pool contains 500 unique candidates and writes calibration reports;
- the dormant `Interpolation` constructor now uses `expression`, `conversion`,
  and `format_spec` in their finalized positions.

### First release-gated corpus build (2026-08-03)

The active input review and confirmatory-benchmark gates are now complete:

- all 32 active seeds are accepted: 22 authored and ten exact, pinned-source
  CPython extractions;
- the 25 source-less HTML records remain quarantined as `authored_candidate`
  material and are not loadable as active seeds;
- all nine generation patterns were re-audited after executable semantic
  validation;
- the replacement confirmatory benchmark is frozen in the provider at 100
  unique tasks with a 70/30 consumer/author split and fingerprint
  `1ba96f45b18e03b328b53668d503ac0a754557bb3c21c180dfc7a652d6243d0c`;
- all 100 benchmark tasks qualify through the real macOS Seatbelt sandbox and
  `tstring-v1` policy; comparison with the 242 pre-dedup SP5 candidates found
  zero exact, semantic, or structural-skeleton overlap.

The first end-to-end SP5 build against that frozen benchmark produced 241
qualified unique rows and one semantic-duplicate drop. Adding first-class
domain metadata and preventing cross-domain composition corrected that result
to **240 qualified unique rows and one semantic-duplicate drop**. There were no
local, policy, execution, or infrastructure drops. This is important: the
current blocker is generation capacity and composition, not candidate
correctness.

The corrected qualified pool is 144 consumer / 96 author and 75 extracted /
165 authored. Its operation mix is 96 introspection, 64 full rendering, 32
static-part joins, 15 same-domain template compositions, one construction task,
and 32 negative controls. It has 71 distinct reference skeletons but only nine
distinct prompts. Domain now survives seed loading, generation, lineage, pilot
candidates, build reports, and publication manifests; domain changes also
invalidate generated artifacts. The observed domain capacity is data 46, HTML
22, logging 15, regex 15, SQL 15, and text 127.

The original profile's 25% construction target required 125 rows despite the
accepted rule that seed-independent construction emits one canonical row per
distinct operation. Profile v2 corrects this before calibration or publication:
construction is 2% (ten distinct tasks), introspection and full rendering are
29% each, composition is 20%, and static joining and negative controls remain
10% each.

The pilot now performs a marginal-capacity gate before sampling and writes all
deficits to `reports/pilot-capacity.md`. Against profile v2 it refuses the pool
with 16 explicit shortages, including 260 total rows, 125 extracted rows, 206
consumer rows, 54 author rows, 110 SQL rows, 103 HTML rows, 85 composition rows,
81 render rows, and nine canonical construction tasks. Its terminal result is:

```text
Pilot capacity gate failed with 16 insufficient strata; see reports/pilot-capacity.md.
```

### Capacity expansion and calibrated pilot (2026-08-03)

The capacity blocker is now closed without promoting any quarantined records:

- twelve accepted authored seeds were added only in deficient domains: four
  HTML, five SQL, two logging, and one regex; active inputs are now 44 seeds
  (34 authored, ten exact CPython extractions);
- the catalog expanded from nine to 35 approved patterns covering values,
  interpolation objects and metadata, typed authoring functions, separator-
  aware static joins, four post-composition outcomes, full rendering, negative
  controls, and ten distinct canonical `convert`/`Interpolation` construction
  tasks;
- structural pattern matching remains deferred as decided; new authoring rows
  use typed introductory functions rather than making SPM a prerequisite;
- generation now groups composition by source kind and domain and emits every
  seed-independent pattern once across the complete seed pool, removing the
  prior duplicate-per-seed-file behavior.

The expanded release-gated build produced **990 qualified unique rows, zero
drops, 175 reference skeletons, and 35 prompts**. All rows passed local gates,
the real Seatbelt sandbox, `tstring-v1`, semantic deduplication, and frozen-
benchmark contamination checking.

Exact feasibility analysis caused two further pre-pilot profile corrections.
Profile v3 reduced the extracted target from 40% to 20% because exact CPython
seeds occupy only text/data domains. Exact flow then showed that v3's combined
50% HTML/SQL target left room for only 85 extracted rows after mandatory
composition and construction. Profile v4 therefore uses HTML 20%, SQL 20%,
logging 15%, regex 10%, text 20%, and data 15%. This preserves the 20% exact-
source anchor and better represents a language/API corpus rather than an
HTML/SQL application corpus.

The old nested fallback sampler selected 500 rows while silently missing the
profile. It has been replaced for the pilot by an exact capacity-and-flow
selector. The committed profile-v4 pilot contains exactly:

- 500 unique rows;
- 100 extracted / 400 authored;
- 350 consumer / 150 typed template-function author;
- 145 introspection / 145 full rendering / 50 static join / 100 composition /
  10 construction / 50 negative-control rows;
- 100 HTML / 100 SQL / 75 logging / 50 regex / 100 text / 75 data rows;
- 141 distinct reference skeletons and all 35 prompts.

The corpus is now **ready for a clean training handoff, but not yet for a model
run**. The remaining blocker is provider-side training rendering and retained
run orchestration: wire the leakage-safe semantic-task/seed-lineage split into
the rendered 500-row handoff, rerun final-data contamination on that exact
rendering, retain the complete run bundle, then execute the two-base baseline
and three-training-seed ladder.

### Training handoff and adapter-reload smoke (2026-08-03)

The provider training boundary is now implemented and exercised. It renders
assistant-only chat records, groups the split by semantic identity and seed
lineage, and rejects exact assistant-code overlap with the frozen benchmark
even when prompts differ. The committed handoff contains 450 train and 50
validation rows in 33 indivisible groups. Its selected-dataset fingerprint is
`553db985ae12f6f74497b9d84e7cbbfbd362379f2943c4e6c5c521fe82bdab94` and
rendered-data fingerprint is
`f00148c8159b576d366ed3713944f8e04a80d8101c2bc008237db5505e7f5373`.

An MLX two-update plumbing smoke loaded the pinned Qwen base, consumed the
actual `train.jsonl` / `valid.jsonl` handoff with `--mask-prompt`, trained 5.767M
parameters in eight layers, saved and reloaded a rank-8/scale-20 adapter, and
scored one frozen-benchmark completion through the evaluator. Validation loss
moved 2.305 → 2.197; the one completion failed policy by reverting to an
f-string (0/1). This tiny run establishes data loading, prompt masking,
validation, adapter saving/reloading, and scoring only. It is **not evidence of
learning or generalization**. The retained machine summary is
`spike/run-artifacts/pilot-500-smoke.json`; the local adapter SHA-256 is
`e1bef7d9e4a80b10f391eb90b43bc118c27c94756b74413ad456272db6ba9966`.

The full baseline ladder, pilot v1, and prompt-diversity repair v2 are now
complete; see the confirmatory sections above. Their gate results supersede
this smoke-era next-step statement. The next evidence step is a focused
contrastive 500-row curriculum for direct API boundaries and decomposed
rendering semantics, not the 2k/5k scale sweep.

## Artifacts

- `spike/REPORT.md` (this file), `spike/results/summary.md` (progression table)
- Active seeds: ten accepted source-resolved records in
  `seeds/extracted.jsonl` and 34 accepted records in `seeds/authored.jsonl`.
  Twenty-five unresolved HTML examples remain quarantined as authored
  candidates.
- Reviewed confirmatory benchmark: provider-owned `benchmark/tasks.jsonl`,
  `benchmark/manifest.json`, `benchmark/fingerprint.txt`, and
  `benchmark/review.json`.
- Current release-gated build: 990 qualified unique rows in the SP5 worktree;
  committed calibrated selection: `reports/pilot.jsonl` (500 rows, profile v4).
- Corpus: `corpus/tstrings.jsonl` (256 qualified rows)
- Benchmarks: `benchmark/tasks.jsonl`, `benchmark/probe.jsonl`, `benchmark/eval2.jsonl`
- Adapters: `adapters/tstring-v1..v5`; served model: `tspike-v5-8bit` (oMLX)
- Reproduction: `spike/build_seeds.py` → `build_corpus.py` → `build_train_data.py`
  → `train_lora.py` → `run_eval.py`
