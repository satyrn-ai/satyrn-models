# SP-DATASET: Measure-Harvest-Synthesize Dataset Workflow

Status: Approved for implementation by the user on 2026-07-30 (approach A plus
the machinery list, chosen over synthesis-first and retrieval-only).

Research of record: [`DATASET_METHODOLOGY.md`](../../../DATASET_METHODOLOGY.md)
— literature review, independent critical review, and two defects verified
against this repo. **Required pre-reading for every rung's brainstorm.**

## 1. Problem

satyrn-model is meant to teach a small local model Python 3.14/3.15 syntax that
postdates its pretraining. The current repo does not do that, and cannot
currently tell whether it does, for two verified reasons:

1. **Train/eval contamination.** Seven of ten prompts in `eval.py` are
   byte-identical to training descriptions in `make_data.py`; two more differ
   only cosmetically. At 24 examples and 3 epochs, the reported pass rate is a
   memorization score.
2. **The oracle cannot see the failure it exists to catch.** `validate_snippet`
   defines success as "did not raise." A completion answering a t-string task
   with an **f-string** passes, as does `pass`. Falling back to the pretrained
   form is the single most likely failure mode, and the harness is blind to it.

A third defect was environmental and is now **resolved**. The CPython source was
a *fork* (`t-strings/cpython`) on an in-progress docs branch dated 2025-06-17,
roughly four months pre-3.14.0, and it lacked `string.templatelib.convert()`
entirely — the canonical `!r`/`!s`/`!a` helper, and exactly the renderer idiom
this project exists to teach. Harvesting from it would have poisoned a dataset
whose entire purpose is currency. It has been replaced by a shallow clone of
official upstream `python/cpython` at tag `v3.14.5`
(`~/projects/pauleveritt/cpython-3.14.5`), matching the verifying interpreter.

The deeper problem is that no measurement loop is closed. Dataset size is not
the bottleneck; the absence of a number is. The user has confirmed the existing
scripts were placeholders and may be discarded.

## 2. Scope

**In scope.** A t-strings vertical slice, built end-to-end, with machinery
designed so additional 3.14/3.15 features plug in later:

- a held-out benchmark with hidden-test oracles, provably disjoint from every
  training corpus;
- a pytest-based verification harness with subprocess isolation and timeouts;
- a baseline ladder run through the existing local oMLX endpoint;
- a harvested corpus drawn from the freshly pinned CPython test suite, PEP 750,
  and the What's New docs — stdlib-only, no third-party package sources;
- one training run measured against those baselines;
- three project-local Claude skills encoding the conventions above.

**Out of scope for this spec.** Broad 3.14/3.15 feature coverage (deferred to
SP4, gated on this slice producing a measured win); synthesis machinery
(SP3, gated on harvest proving insufficient); the FIM-versus-chat deployment
decision (deliberately deferred — see §3.6).

**Explicitly discarded.** `main.py`, `make_data.py`, and `eval.py` in their
current form. They are placeholders and carry both defects above. Nothing in
this spec preserves their structure.

## 3. Decisions

### 3.1 Sequence is measure → harvest → synthesize, and the order is load-bearing

Each stage is gated on the previous stage's evidence. Measurement precedes data
work because the literature's own numbers argue against fine-tuning as the
default tool: documentation-in-context reaches ~66% executable on post-cutoff
API tasks, while the only weight-update result cited is negative. Harvesting
real code precedes synthesis because OSS-Instruct's central finding is that
seeding from real code beats ungrounded generation, and because harvesting is
nearly free here.

### 3.2 The baseline ladder is a decision gate, not a formality

SP1 produces three numbers on the held-out benchmark: base model zero-shot,
base model plus PEP 750 docs in context, and (later) the fine-tune.

> **Gate:** the fine-tune must beat base-plus-docs. If it does not, the correct
> answer for this project is a docs/retrieval layer, and that verdict is a
> legitimate outcome that re-scopes or kills the training track.

This is stated up front so the result cannot be rationalized after the fact.
It also means approach C (retrieval-only) is tested as a byproduct rather than
assumed to lose.

**Amended 2026-07-31 — the gate is SUSPENDED for this spike's own run.**

The gate above assumes a corpus built at the intended scale. This spike will
instead train on a knowingly-undersized corpus (stdlib-only sourcing leaves
CPython's 13 `test_templatelib.py` methods plus PEP 750's examples — see
[SP5's brief](../research/2026-07-31-corpus-authoring-brief.md)), because its
purpose changed: **settle the machinery and establish a low anchor on the
data-scale curve**, not decide fine-tuning's fate.

Applying the gate unmodified would manufacture an unsupportable verdict. If a
fine-tune on ~30 examples fails to beat base-plus-docs, the honest reading is
**"this corpus size is insufficient"** — *not* "retrieval wins." The literature
is explicit that nobody has published a volume for this task, which is exactly
why the low anchor is worth having.

So for this spike, Task 12 reports:

- the three numbers, and
- **the corpus size that produced them**, as a labelled data point on the
  scale curve,

and explicitly records that the §3.2 gate was **not** adjudicated. The gate
resumes, unchanged, once SP5 delivers a corpus at intended scale — at which
point this spike's anchor becomes the curve's left-hand end rather than a
verdict.

### 3.3 The oracle is pytest in a subprocess, never in-process `exec`

Verification runs each candidate as a pytest case in an isolated subprocess with
a timeout. This replaces `exec(compile(code, label, "exec"), {})`, which has no
timeout (a generated `while True` hangs the run), no isolation, and no notion of
a hidden test.

Every task carries three checks:

1. **Hidden asserts** the model never sees, expressing the task's actual
   contract.
2. **A feature-use check** — the solution must actually construct a `Template`.
3. **An old-form canary** — the task fails if the solution used an f-string or
   `.format()` where a template was required.

Checks 2 and 3 exist specifically because "did not raise" cannot distinguish a
correct answer from a pretrained-prior fallback.

### 3.4 Every example records its provenance and source version

Each corpus row carries the source file, the upstream commit or tag it came
from, and the interpreter version that verified it.

**Pin to the version that verifies, not to the newest.** CPython is pinned at
`v3.14.5` because that matches the installed interpreter which executes every
example — deliberately not upstream's newer `v3.14.6`, so harvest source and
validator cannot drift apart. `main` is used only for 3.15 material, recorded as
such. Sources must come from official upstream (`python/cpython`), never a fork.

This is a direct response to the stale-checkout near-miss. A dataset whose
purpose is currency is uniquely damaged by an unlabelled stale snapshot, and
provenance makes the failure detectable instead of silent. The near-miss also
produced a second lesson worth encoding: the *first* diagnosis of that staleness
was wrong on the facts (see the correction recorded in the research doc), which
is why SP2 R1 makes the pin machine-enforced rather than trusting a written
claim about what a tree contains.

### 3.5 Harvest converts real code into tasks; it does not paraphrase it

**Amended 2026-07-31** — see
[the harvest architecture pivot](../research/2026-07-31-harvest-architecture-pivot.md).
The principle below is unchanged; the *harvest unit* it originally named was
wrong and is corrected here. **Further amended 2026-07-31, same day:** the
harvest-unit correction below was right, but its original instantiation
against `tdom`'s test files was ruled out separately — see the stdlib-only
decision at the end of this subsection.

**Harvest call sites, not callees.** The unit of harvest is a real **test
function** exercising the feature: its intent becomes the prompt, its
t-string-bearing body the reference solution, its own assertions the hidden
oracle. Call sites are naturally standalone (a t-string literal plus one
import); callee-side library internals are where dependency closures live.
This now applies to CPython's own test suite
(`Lib/test/test_string/test_templatelib.py`), the sole admissible harvest
source.

The original reading — harvest unit = library-internal function, oracle temp
dir must be import-free — forced a miniature Python module bundler whose bug
class survived two fix rounds, to unlock a ceiling of ~21 examples of which
**the four actually shipped contained zero t-strings**. Neither premise was
required by the research or the user. Both are dropped.

Consequences:

- Function-level harvest is retained only for **trivial closures** (same-file
  or stdlib). Cross-module inlining is deleted, not fixed — making the
  wrong-symbol bug class unrepresentable rather than merely gated.

**Two mandatory invariants on any harvester, unaffected by any of the above:**

1. **Self-verification before emission.** Every Example's `reference_solution`
   must pass its own `hidden_test` through the real oracle, or be dropped
   loudly with a reason. This turns any future harvester bug from silent
   corpus poisoning into visible yield loss. Necessary but not sufficient — a
   wrong-but-passing example survives any gate, which is why the architecture
   changed rather than merely acquiring this check.
2. **On-target filter.** An Example whose prompt, reference solution, and
   hidden test collectively contain no `TemplateStr` and no `Template`-consuming
   code does not enter a t-strings corpus, whatever its provenance.

**Stdlib-only, decided 2026-07-31 by the project owner.** No training example
may import `tdom` or any other third-party package. The project teaches the
PEP 750 language feature and the `string.templatelib` stdlib API, not any one
library's abstractions built on top of it. `tdom` is ruled out as a corpus
source entirely — see
[`DATASET_METHODOLOGY.md`](../../../DATASET_METHODOLOGY.md) section 1 for the
full history, including the two independent failures this produced before
being caught in review. Admissible harvest sources are CPython's own pinned
test suite and PEP 750/What's New material; synthesis (SP3) supplements both,
also stdlib-only.

### 3.6 The corpus is stored format-neutral

Rows are stored as structured records — task, reference solution, hidden tests,
provenance — and rendered to a training format at training time. The
FIM-versus-chat deployment decision is deferred rather than baked in, because it
is genuinely undecided and because format-neutral storage costs little and
permits training both and comparing.

### 3.7 Training uses mlx-lm directly

Unsloth's MLX backend is new, and its rank/alpha handling and prompt-token loss
masking are unverified. `mlx-lm` is the lower-level, better-understood path on
hardware that is already running MLX via oMLX. Rank is a swept parameter, not a
guessed constant; note that the placeholder config paired `r=16` with
`alpha=16`, so any rank change must adjust alpha deliberately.

### 3.8 Conventions ship as project-local Claude skills

Three skills in `.claude/skills/`, written when the convention they encode is
first established, not speculatively:

- `harvest-corpus` — extraction rules, the stdlib-only rule, mandatory version
  pinning and provenance;
- `verify-example` — the three-check oracle contract of §3.3;
- `eval-run` — running the ladder, reading it, and the contamination check.

## 4. Completion criteria

This spec is satisfied when all of the following hold:

- A held-out benchmark exists whose tasks are provably disjoint from every
  training corpus, enforced by an automated contamination check that fails loudly
  rather than reporting a score.
- The oracle runs candidates as isolated, timed-out pytest cases and applies all
  three checks; a deliberately planted f-string solution to a template task is
  demonstrated to **fail**.
- Three baseline numbers exist for the benchmark: base zero-shot, base plus docs,
  and at least one fine-tune, all produced by the same harness.
- A base-model audit has compared at least two candidate bases zero-shot, and the
  chosen base is recorded with its reasoning.
- The harvested corpus draws from the official-upstream CPython checkout
  pinned at `v3.14.5` and other stdlib-only sources (PEP 750, What's New
  docs), with per-row provenance, and the harvester *enforces* the pin by
  failing when the tree's tag and the verifying interpreter disagree. No
  example imports `tdom` or any other third-party package.
- One training run has completed and been scored against the baselines. For a
  run at intended corpus scale, the §3.2 gate has been evaluated and its
  verdict recorded — including if the verdict is that retrieval wins. **For
  this spike's own run**, per §3.2's 2026-07-31 amendment, the gate is
  pre-registered as suspended rather than adjudicated, and the criterion is
  instead that the run records a labelled data-scale anchor (corpus size
  alongside the three numbers) so it can serve as the left-hand end of a
  future scale curve once the gate resumes at intended scale.
- The three project-local skills exist and encode the conventions actually used.

**Non-criteria.** Beating the baseline is *not* a completion criterion. Producing
a trustworthy number is. A well-measured negative result closes this spec
successfully and re-scopes the roadmap.
