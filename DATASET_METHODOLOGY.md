# Dataset methodology: teaching a ~9B model Python 3.14/3.15 syntax

Working document. Combines a literature review with a critical review pass, plus
two defects verified directly against this repo.

Status: **the repo has two blocking defects that make current results
uninterpretable.** Fix those before generating any more data or running any more
training.

---

## The three things that matter

If only three things happen to this project, these, in order:

1. **Rebuild evaluation.** It is currently measuring memorization, not learning
   (see Defect 1). Nothing else can be verified until this is fixed, and the
   baselines it produces decide the strategic question at the bottom of this doc.
2. **Invert the data pipeline.** Stop hand-writing examples that get validated;
   start generating candidates at volume and letting the interpreter reject them.
   Seed from the pinned CPython at `~/projects/pauleveritt/cpython-3.14.5` and
   PEP 750 rather than from imagination — see "Ground truth worth mining".
   **Stdlib-only:** no example may import a third-party package.
3. **Re-audit the base model.** Qwen2.5-Coder-7B predates PEP 750's *acceptance*.
   A newer base may already half-know this material, which turns knowledge
   injection into reinforcement — a much easier problem. One afternoon of work,
   possibly the largest single effect available.

Explicitly **not** in the top three: LoRA rank sweeps, a continued-pretraining
stage, adopting distilabel/Curator, tokenizer work.

---

## Two blocking defects (verified in this repo)

### Defect 1 — train/eval contamination

Seven of the ten prompts in `eval.py` were byte-identical to training
descriptions in `make_data.py` (both files deleted in SP0 R1; quoted here as
the historical record of the defect):

```
build a parameterized SQL query from a template
render HTML with automatic escaping of interpolated values
write a custom renderer that uppercases interpolations
match interpolations by value type with structural pattern matching
use a raw template string to keep backslashes literal
concatenate two templates with +
return a reusable template from a function
```

Two more differ only cosmetically (`use the name= debug syntax` vs
`use the {name=} debug syntax`; `inspect the structure of a template...` vs
`inspect the structure of an empty template...`). Roughly one prompt out of ten
is genuinely held out.

With 24 examples at 3 epochs and lr 2e-4, any pass rate this eval reports is a
memorization score. It cannot distinguish a model that learned t-strings from one
that memorized twenty-four strings.

### Defect 2 — the validator cannot detect the failure it exists to catch

`make_data.py::validate_snippet` (since deleted) was:

```python
exec(compile(code, label, "exec"), {})
```

Success is defined as "did not raise." That means a completion answering
*"greet a user by name"* with an **f-string** passes validation. So does a
completion that defines nothing. So does a bare `pass`.

This matters because falling back to the pretrained form is the single most
likely failure mode (see "What the evidence says", below). The eval is
structurally blind to it.

Minimum fix: per-task **hidden asserts** that the model never sees, plus a
structural check that a `Template` was actually constructed, plus **old-form
canaries** that fail the example if the completion used an f-string or
`.format()` where the task called for a template.

---

## What the evidence actually says

Five papers were checked. Numbers below are verified; the interpretive moves are
labeled where they are inference rather than evidence.

### The prior is the enemy, and it is stronger here than in the literature

[When LLMs Lag Behind](https://arxiv.org/abs/2604.09515) tested models on
post-cutoff API changes: **42.55%** of generated code was executable with no
documentation, rising to **66.36%** with structured API docs in the prompt.
Self-reflection prompting added a further **+11.33%**. Of non-adoption failures,
42.1% were *complete omission* — the model ignored the new API and used what it
already knew; of execution failures, 26.6% were wrong parameters.

[CodeUpdateArena](https://arxiv.org/abs/2407.06249) (54 functions, 7 packages,
670 synthesis examples) found that prepending update documentation to open-source
code LLMs does **not** get them to incorporate the change, and that knowledge
editing had substantial room for improvement.

⚠️ Neither paper tested fine-tuning. Deriving *data-design* rules from them
("the dataset must suppress the old form") is plausible inference, not
demonstrated result. Treat it as a hypothesis the new eval should test.

### The "syntax is the easy half" argument does not survive review

[Syntax Without Semantics](https://arxiv.org/abs/2605.15607) fine-tuned Qwen3
4B/8B/32B on PyLang, an invented language absent from pretraining: 352 problems,
Python outperforming PyLang by up to ~19%, identical algorithm chosen 80% of the
time, internal representations converging (CKA > 0.97) with divergence only at
the output stage, and no intervention closing the gap — preference tuning
actually *widened* it at 8B (18.8% → 22.1%).

The original analysis read this as good news: "you're not teaching a new
language, just new surface forms, so you get the hard half for free." **That
inference does not hold**, for two reasons:

- **PyLang had zero competing prior.** Nothing in pretraining fought the new
  syntax. Here, f-strings are among the most frequent patterns in the entire
  pretraining corpus. On the axis that actually matters — prior interference —
  PyLang is the *easier* case, not the harder one.
- **t-strings are not pure surface syntax.** `t"..."` returns a `Template`, not a
  `str`, and correct use requires the processing-function idiom (a renderer
  consuming `.strings` / `.interpolations`). That is usage semantics, which is
  precisely what the paper found does not transfer.

The paper makes no claim about new syntax within a known language. Expect the
PyLang failure mode — right algorithm, wrong expression — rather than assuming
immunity to it.

### Volume: no published recipe fits this task

The "~12 examples per API change" figure is `670 / 54` from CodeUpdateArena —
that's a *benchmark's* density, not a validated training volume, and that paper's
fine-tuning results were largely negative. Magicoder's 75K
([OSS-Instruct](https://arxiv.org/abs/2312.02120)) was general instruction tuning,
not single-feature injection.

Honest position: nobody has published a number for this. Sweep **500 → 2k → 5k**
against a fixed held-out eval and let the curve decide. What is certain is that
24 is far too few.

---

## Data design principles

**Write problems whose solution requires the feature.** The current 24 examples
are mostly assert-style API introspection (`assert template.strings == (...)`).
That teaches a model to write assertions *about* templates, not to reach for one
when solving a problem. Follow CodeUpdateArena's construction: tasks "prone to
use the update," with the assertion moved out of the example body and into a
hidden test.

**Include contrastive old→new pairs and negative coverage.** Same task, old
solution and modern solution, modern as target. Also include tasks where a
t-string is the *wrong* choice, or the model will jam templates into everything.

**Seed from real code.** OSS-Instruct's central finding is that seeding
generation from randomly sampled real snippets mitigates synthetic-data bias and
maximizes diversity. Ungrounded self-instruct collapses toward the generator's
own distribution — which is already visible here: roughly 15 of the current 24
examples are variations on `name = "World"; t"Hello {name}"`.

**Vary the prompt format.** Every training example and every eval prompt begins
with `# Python 3.14 t-strings:`. That is a trigger phrase no real user will type,
and generalization away from it is entirely untested. Mix comment, docstring,
chat, and no-version-mention framings. Related: training targets the *base* model
in completion format while any realistic deployment is chat-shaped.

**Scale the oracle, not the handwriting.** Execution-verified rejection sampling
is the code domain's strongest signal. The interpreter check here is the best
asset in the repo and it's currently filtering 24 hand-written items. Invert it.

---

## Ground truth worth mining

Ranked by value per unit of effort, using assets already on this machine.

### 1. ~~`tdom`~~ — RULED OUT, and the ranking below was wrong

⛔ **Corrected 2026-07-31 by the project owner. No training example may import
`tdom`, or any other third-party package. All sources are stdlib-only.**

An earlier revision of this document ranked `tdom` as "the highest-value corpus
available" and built a whole harvest architecture around it. That was a
category error, and it cost most of a build cycle.

**Why it was wrong:** the goal is to teach a *language feature* — PEP 750
t-string syntax and the `string.templatelib` stdlib API (`Template`,
`Interpolation`, `.strings`, `.interpolations`, `.values`, `convert()`).
Training on tdom would have taught the model **tdom's** API surface
(`TemplateParser`, `TFragment`, `TElement`, `html()`) and bound its notion of
t-strings to one niche third-party library. The reasoning below — "real library
code that consumes the feature" — is true and still irrelevant: consuming the
feature *through a library's abstractions* is not the skill being taught.

**Two independent failures this produced**, both caught only by review:

1. The two modules actually harvested (`escaping.py`, `callables.py`) contain
   **zero t-string literals**. A dependency-closure resolver was hardened over
   two fix rounds to extract examples that did not contain the target feature
   at all.
2. Pivoting to tdom's *test* files (which do hold 341 + 62 t-strings) produced
   329 examples whose hidden tests were **vacuous** — they asserted
   `_result_0 == _result_1` where both values came from the candidate's own
   code, so a candidate returning `{k: 1 for k in [...]}` with a dummy
   t-string passed. Proven exploitable against the real oracle before anything
   was committed.

The second failure was itself downstream of the first: those junk assertions
existed only because tdom's tests compare against large structural literals
(`TFragment(children=(...))`). Stdlib t-string tests assert on small
self-contained values and need no such transformation.

**Nothing tdom-derived ever entered the corpus** — the defects were caught
before any training data was committed. The harvesters and the oracle's
third-party-package machinery have been deleted.

**Standing rule:** a source is only admissible if its examples teach t-strings
using the standard library alone.

### 2. CPython's own test suite — now pinned at v3.14.5

**Resolved 2026-07-30.** The source is now a shallow clone of *official upstream*
`python/cpython` pinned at tag **`v3.14.5`**, at
`~/projects/pauleveritt/cpython-3.14.5` (157 MB).

It replaced a checkout that was wrong in two ways. That tree was a **fork**
(`github.com/t-strings/cpython`) sitting on an in-progress branch
(`docs/pep750-first-pass`, HEAD `fcd74e64c74`, **2025-06-17**) — roughly four
months before 3.14.0 final. It has been removed; that branch remains on the fork's
remote.

**The measured gap between that tree and v3.14.5:**

| | Jun-2025 fork tree | v3.14.5 |
|---|---|---|
| `string.templatelib.convert()` | **absent** | present |
| `Lib/string/templatelib.py` | 26 lines | 33 lines |
| `test_templatelib.py` | 160 lines | 193 lines |
| Test methods | — | `+test_convert`, `+test_interpolation_creation` |
| `Objects/templateobject.c` | — | 94 changed lines |

The missing `convert()` is the material one, and it is squarely on-target:
`convert(obj, conversion)` is the canonical way a custom renderer applies
`!r` / `!s` / `!a`, which is exactly the renderer idiom this project exists to
teach. A model trained from that tree would never see it.

**Correction, recorded deliberately.** An earlier revision of this document
claimed the stale tree lacked `Template.values`. **That was wrong.** `values` is
a C-level getset in `Objects/templateobject.c` and was present in *both* trees;
the claim came from grepping the thin Python shim, where `values` is defined in
neither. The conclusion (stale tree, do not mine it) held, but the evidence
offered for it did not — and a document arguing for provenance discipline is the
worst possible place to keep an unverified claim.

The standing rule this produces: **pin every source to a known version and record
which version each example came from.** Pin to the version that will *verify* the
examples — here `v3.14.5`, matching the installed interpreter, not upstream's
newer `v3.14.6` — so harvest source and validator cannot drift apart.

### 3. PEP 750 and the What's New documents

Feature inventory plus intent prose — useful for generating instruction framing
and for the raw-text rows mixed into training. Lower value than the two corpora
above because it is *about* the feature rather than *using* it, and because
in-context documentation is the baseline we are trying to beat (see the
strategic question below); it should not also be the training signal without
care.

### 4. Real migration diffs

Libraries adopting 3.14 give natural old→new contrastive pairs, in principle.
In practice, stdlib migration diffs for a brand-new feature are scarce this
soon after release, and third-party history (e.g. `tdom`'s) is inadmissible as
a corpus source under the stdlib-only rule (see section 1 above). Expect
contrastive old→new pairs to come primarily from synthesis (SP3), not from
mined migration diffs.

### On 3.15

Safe to train on now. Per [PEP 790](https://peps.python.org/pep-0790/), 3.15 hit
feature freeze at beta 1 on 7 May 2026, final release 1 October 2026 — the
feature set is frozen. Still derive the list from actual docs and changelog
rather than asking a model; any LLM account of 3.15 will be part-confabulation.
The same version-pinning rule applies with more force here, since 3.15 material
is still moving between betas.

---

## Training configuration notes

**Skip the separate CPT stage.** "CPT injects knowledge, SFT aligns behavior" is
a framing from full-parameter, billions-of-tokens pipelines. The entire raw
corpus here (PEPs, What's New, `Lib/test/`, templatelib docs) is a few megabytes,
and both "stages" would be LoRA runs on the same Mac. Just mix raw-text documents
into the same run as extra `{"text": ...}` rows alongside task examples and
replay data. Same effect, no pipeline complexity.

**Rank: sweep, don't guess.** Higher rank does help in the knowledge-acquisition
regime, but at 24 examples rank is nowhere near the binding constraint — data is.
At low-thousands scale, r=32–64 with alpha ≈ 2r is a reasonable thing to sweep.
Note the current config pairs r=16 with alpha=16; raising r without adjusting
alpha silently changes the effective scale.

**Replay: cheap insurance, not yet urgent.**
[Scaling laws for forgetting](https://arxiv.org/abs/2401.05605) confirm LoRA
still forgets, with a strong inverse-linear relationship between fine-tuning
performance and forgetting, not avoidable by early stopping. But forgetting
scales with parameters and *update steps*, and the current run is ~36 steps.
It becomes real at the recommended data scale. Mix 10–30% generic verified
Python then.

**Worth one hour, not more:** confirm `unsloth_zoo.mlx.trainer` honors r > 16 and
scales `lora_alpha` correctly (the MLX backend is new), and check whether
`MLXTrainingConfig` masks prompt/header tokens from the loss — it likely trains
on the full sequence, spending gradient budget on learning the header.

**Tokenizer is a non-issue.** Qwen uses byte-level BPE; `t"` needs no vocabulary
change and will tokenize via existing merges the same way `rb"` does. Worth a
five-minute check, not a workstream.

---

## The strategic question this project has not yet answered

The cited evidence currently argues *against* fine-tuning more than for it:
docs-in-context reaches 66% executable (plus ~11 points from self-reflection),
while the only weight-update evidence cited is negative. The decision criterion
was never stated, so state it:

> **The fine-tuned model must beat base-model-plus-docs-in-context on the
> held-out eval. If it doesn't, the right answer is a docs/retrieval layer.**

That is why baselines are part of priority 1: base zero-shot *and* base + PEP 750
docs in context. Without both numbers, no gain can be attributed to fine-tuning.

Fine-tuning is still defensible here for reasons worth claiming explicitly: a
small local model has no context budget to spend on docs; there's no per-request
retrieval latency; docs-in-context scales poorly across *dozens* of 3.14/3.15
features at once; and fine-tuning attacks the parametric-vs-context conflict that
appears to cap the docs approach at 66%. The strongest configuration is probably
**hybrid** — fine-tune *and* supply docs — which neither the analysis nor the repo
currently contemplates.

It is also fine for this to be partly a learning exercise. But then that should
be said, rather than implying the evidence establishes fine-tuning as superior.

---

## Sources

- [Syntax Without Semantics: Teaching LLMs to Code in an Unseen Language](https://arxiv.org/abs/2605.15607)
- [When LLMs Lag Behind: Knowledge Conflicts from Evolving APIs](https://arxiv.org/abs/2604.09515)
- [CodeUpdateArena: Benchmarking Knowledge Editing on API Updates](https://arxiv.org/abs/2407.06249)
- [Magicoder: Empowering Code Generation with OSS-Instruct](https://arxiv.org/abs/2312.02120)
- [Scaling Laws for Forgetting When Fine-Tuning LLMs](https://arxiv.org/abs/2401.05605)
- [API-guided Dataset Synthesis to Finetune Large Code Models](https://arxiv.org/pdf/2408.08343)
- [PEP 790 – Python 3.15 Release Schedule](https://peps.python.org/pep-0790/)
- Tooling: [distilabel](https://github.com/argilla-io/distilabel) ·
  [Bespoke Curator](https://github.com/bespokelabsai/curator)
