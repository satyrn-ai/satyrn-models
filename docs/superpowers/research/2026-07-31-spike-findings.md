# Spike findings: what the throwaway build established

**Date:** 2026-07-31
**Source:** branch `worktree-overnight-tstrings-spike` (30 commits, treated as
throwaway). This document is the harvest of its learnings.

## How to use this document

This is **input to a Superpowers brainstorm**, not a design. It records what the
spike established as fact, what it cost, and which decisions earned their keep —
so the real build starts from evidence rather than from the spike's code.

Read it alongside the
[SP5 corpus-authoring brief](2026-07-31-corpus-authoring-brief.md), which covers
the corpus-generation half. This document covers everything else: measurement,
verification, and the failure modes that dominated the spike.

**Do not carry the spike's code forward.** Carry the judgment below. The code was
shaped by constraints discovered mid-flight and by an architecture that was
pivoted twice; it is worth reading for reference, not for reuse.

---

## 1. What was established as fact

### The base model has no latent t-string knowledge

Qwen2.5-Coder-7B scores **0/11** on a held-out benchmark, both zero-shot and
with PEP 750 documentation in context. Of the 10 with-docs tasks that *require*
a template, all 10 failed with the same reason —
`no t-string literal (ast.TemplateStr) found` — producing syntactically valid
Python every time while never reaching for t-string syntax, even with the API in
the prompt. (The 11th is a negative-control task where a t-string is the wrong
answer; it failed on an assertion, not the surface check.)

This makes it a **clean substrate**: results attributable to training, not to
pretraining contamination. (Chosen deliberately for that property; a base that
already half-knew t-strings would confound whether the machinery works.)

> ⚠️ **The with-docs arm is a deliberately weak representative of retrieval, and
> this was never resolved.** Gate 1 flagged it explicitly: an 8-line
> comment-style API summary, fed to a *base* (non-instruct) model, single greedy
> sample, no worked example. A serious docs-in-context contender would be the
> instruct variant with a real PEP 750 excerpt and at least one worked example,
> or few-shot prompting.
>
> Consequence for the rebuild: **`base + docs = 0%` supports "this base model
> does not know t-strings." It does not support "retrieval loses."** Any eventual
> "fine-tuning beats retrieval" verdict is scoped to *this specific weak arm*
> unless the arm is strengthened first. Gate 1 left that decision to the owner
> and it was never made — it is still open. See §6.

Secondary observation from retained completions: on bare comment prompts the
base model frequently generates *prose* (StackOverflow-question-style English)
rather than code, and greedy decoding sometimes loops a line to the token
budget. Neither is a harness artifact; both are consistent with the model
having no idea what to do.

### The verify → train → evaluate loop closes end to end

The most important positive result. On its **own training prompts**, a LoRA
fine-tune emits correct t-strings in **4 of 5 sampled prompts** (the fifth
correctly uses the `Interpolation(...)` constructor, which is what that example
teaches). The base model emitted **zero** t-strings across 22 baseline
generations.

This separates *"the pipeline is broken"* (ruled out) from *"the corpus is too
small"* (confirmed). Everything downstream of data generation is a known
quantity.

Precision notes: the corpus is 24 examples, of which **20 were training rows**
(4 were split off for validation), and the memorization probe sampled **5 of
those 20**. "Memorization" is therefore well-evidenced but not measured
exhaustively — the rebuild should run the check over all training rows and
retain completions, which the committed `memorization_check` module supports.

### n=24 produces zero generalization

| Condition | Held-out (11 tasks) |
|---|---|
| Base, zero-shot | 0% |
| Base + PEP 750 docs | 0% |
| Fine-tuned, n=24 | 0% |

Training loss fell 2.86 → 0.08 over 150 iterations. In isolation that looks like
success; combined with 0% held-out and ~100% training-prompt recall, it is
textbook memorization without transfer.

⚠️ **This anchor is composition + scale, not scale alone.** Only ~9 of the 24
examples contain a t-string literal; the other 15 teach the
`Interpolation()`/`convert()` constructor API. Future points on the data-scale
curve must match composition or they are not comparable to this one.

### Harvesting cannot reach scale under stdlib-only sourcing

Empirically established, not assumed. Admissible sources total CPython's
`Lib/test/test_string/test_templatelib.py` (193 lines, 13 test methods) plus PEP
750's examples — roughly 1–2 orders of magnitude below a useful corpus size.
This is what forces generation to be the primary source rather than a
gap-filler.

---

## 2. The central finding: a bug class that defeats ordinary testing

**Three distinct defects, one of which recurred after being "fixed."** All share
one shape: **wrong, but passes its own test.**

| # | Defect | Caught by |
|---|---|---|
| 1 | Dependency inliner resolved the wrong module's same-named symbol — code ran, its test passed, behaviour was wrong. **Recurred** after a fix round: the specific repro was closed while the underlying class survived in three other code paths | Adversarial review, twice |
| 2 | Hidden tests asserted two *candidate-produced* values against each other, encoding no expected value at all. Proven exploitable: a zero-work candidate passed | Manual inspection, then an adversarial probe built to confirm it |
| 3 | The anti-vacuity gate built to stop #2 was itself structurally blind — its degenerate candidate carried no t-string, so the oracle rejected it on a surface check *before the hidden test ran*. A hidden test of literally `assert True` passed every gate | Final review gate |

None were caught by the test suite. Every one required someone actively trying
to break it. Defect #3 appeared *inside the gate built to stop #2*, despite
active vigilance about exactly this class — and the real corpus turned out clean
only because a **stronger adversary had been run by hand than the committed code
enforced.** That gap between "verified once manually" and "enforced
structurally" is the recurring theme.

### The design rule this yields — stated narrowly

**Make the bad state unrepresentable where you can. Where only a gate is
possible, the gate itself needs an adversarial test.**

The stronger half is evidenced: deleting cross-module inlining outright (rather
than fixing its resolution logic) made defect #1 impossible to express, and
requiring expected values to live in the hidden test — never in the reference
solution the model produces — made #2 impossible.

⚠️ **Do not over-rotate against gates.** The fix for #3 is itself *a better
gate* (degenerates must carry a dummy t-string so they reach the hidden test;
their failure must originate there), not a structural impossibility — anti-vacuity
is inherently a gate, because it is a claim about a test's discriminating power.
And it is **untested in anger**: the spike ended immediately after that commit.
The evidence supports "gates are where this bug class re-hosts, so gates need
their own adversarial tests," not "gates are bad."

### Implication for the real build

Start from the threat model, not from a feature list. The spike's gates accreted
one per discovered defect; a proper design should begin from *"generated examples
can be confidently wrong in ways review does not catch"* and work backward, with
adversarial verification as a **structural, first-class requirement** rather than
a review activity — including adversarial tests aimed at the gates themselves.

Budget for it explicitly. Every incident above cost a review round; two cost an
architectural pivot.

---

## 3. Technical facts worth not rediscovering

- **`ast.Interpolation.format_spec` is itself an `ast.JoinedStr` node.** A naive
  "flag every `JoinedStr` as an f-string" check therefore rejects *every correct
  t-string using a format spec* (`t"{v:.2f}"`). Detection must exempt nodes
  reachable only through a `.format_spec` slot, while still descending into them
  so a genuine f-string nested in a spec expression is still caught.
- **`Template.__add__` collapses adjacent strings** when no interpolation
  separates them: `t"Hello " + t"World"` yields `.strings == ("Hello World",)`,
  not two segments.
- **`string.templatelib.convert(value, conversion)`** is the canonical `!r`/`!s`/`!a`
  helper and the heart of the renderer idiom worth teaching. It is absent from
  pre-3.14.0 CPython checkouts.
- **CPython's `test_templatelib.py`** uses `TStringBaseCase` helpers
  (`assertTStringEqual`, `assertInterpolationEqual`) from the private
  `test.test_string._support`. Expand them into plain asserts rather than
  importing a private test helper into training data. Its `fstring()` helper is
  itself excellent training content — the canonical template renderer.
- **mlx-lm's default 1000 iterations is catastrophic on a small corpus.** At
  n≈24, ~150 iterations at batch size 1 (≈7–8 epochs) is appropriate; the
  default would be hundreds of epochs of pure memorization.
- **Pin the source to the version that *verifies*, not the newest.** The
  interpreter executing examples and the source they were harvested from must
  match exactly, or the two silently drift.
- CPython source must be **official upstream** (`python/cpython`), pinned by tag,
  with the remote URL checked — a fork on a feature branch nearly poisoned the
  corpus with a pre-release API.

---

## 4. Errors made, and their root causes

Recorded because the root causes are more useful than the incidents.

### The tdom category error (cost: most of a build cycle)

**This was the spike author's own design error**, not something inherited. The
research doc ranked a third-party library (`tdom`, an HTML templating library
built on t-strings) as "the highest-value corpus available," and an entire
harvest architecture was built around that ranking. Two things were wrong:

1. **Category error.** The goal is teaching a *language feature* and the
   `string.templatelib` stdlib API. Training on a library teaches that library's
   API surface and binds the model's notion of t-strings to one niche
   dependency. Correct rule: **stdlib-only; no training example may import a
   third-party package.**
2. **Nobody checked whether the harvested examples contained the feature.** The
   two modules actually harvested contain **zero** t-string literals. Three
   review rounds hardened a dependency resolver to extract examples that did not
   contain the target feature at all.

**Root cause:** a source was ranked on plausible-sounding reasoning
("real library code consuming the feature") without a one-line empirical check
(`grep -c 't"' <source>`). The corrective is cheap and should be a standing
gate: *an example that does not contain the feature does not enter a corpus for
that feature, whatever its provenance.*

### An analytical claim that did not survive review

The initial literature analysis argued the project was on the easy side of the
problem, citing work showing fine-tuning teaches syntax readily while semantics
resist. Review established the inference was wrong: that work used an *invented*
language with **zero competing prior**, whereas f-strings are among the most
frequent patterns in pretraining. On the axis that matters — prior interference
— the cited case is the *easier* one.

**Root cause:** borrowing authority from a paper whose setup differed on the
dimension that mattered. Check the axis, not the headline.

### Task sizing

One task required two fix rounds, an architectural pivot, and was then deleted
entirely. That boundary was drawn around the wrong unit of work.

### Delegated long-running work was abandoned twice

On two occasions a delegated implementer launched a long foreground run (model
load plus generation), then backgrounded it and ended its turn expecting an
async completion notification that does not exist for subagents. The work itself
was fine; it was simply left unfinished and unreported, and had to be recovered
by checking the OS process directly.

**The rebuild will dispatch identical long runs** (training, evaluation,
gate sweeps that invoke the real oracle per example). Any delegation of those
must state explicitly: *this call blocks your turn; wait for it to return before
reporting.* Cheap to say, and it cost two recovery cycles to learn.

---

## 5. Carry forward / redo

**Carry (validated design judgment):**

- Oracle: pytest in an isolated subprocess with a timeout — never in-process
  `exec`, which has no timeout, no isolation, and no notion of a hidden test
- Three-check contract: hidden asserts + the feature is actually used + an
  old-form canary (f-string / `.format()` / `%`)
- Expected values derived by **executing real code**, never generated by a model
- Expected values live in the **hidden test**, never in the reference solution
- Self-verification before emission: every example's own reference solution must
  pass its own hidden test through the real oracle, or be dropped loudly
- Anti-vacuity: degenerate candidates must *reach* the hidden test, and their
  failure must originate there
- Contamination gate that **raises rather than warns**, dual-axis (prompt and
  normalized code, separate thresholds — a single shared threshold provably
  closes nothing)
- Mandatory provenance on every row; machine-enforced source pinning
- A memorization check (train-prompt regurgitation rate) as a standard
  post-training step — it is what distinguishes a broken pipeline from a small
  corpus

**Redo:**

- Design from the threat model in §2, rather than accreting gates per incident
- Validate source suitability empirically before building extraction for it
- Smaller task units around verification-heavy work

**Expired — do NOT carry:**

- *"The benchmark is frozen because baselines are attached to it."* Correct
  discipline mid-spike; obsolete now. The attached baselines are two 0% numbers
  that a rerun reproduces exactly (greedy decoding) in a few minutes of compute.
  Freezing an 11-task benchmark that Gate 1 called too thin, to protect
  baselines that cost minutes to re-measure, is a bad trade. **Redesigning the
  benchmark and re-running baselines should be on the table** — see §6.

---

## 6. Open questions for the brainstorm

1. **Prompt↔solution alignment is unchecked, by design.** No gate can currently
   detect an example whose solution is correct but answers a *different question
   than its prompt*. This poisons training data invisibly. Is it mechanically
   solvable, or does it need a sampling-based human check?
2. **Corpus composition targets.** The n=24 anchor is polluted by having only
   ~9 t-string-bearing examples. What is the intended balance between authoring
   t-strings, consuming templates, and constructor-API usage?
3. **Training format.** The corpus is deliberately format-neutral; the
   FIM-versus-chat decision was deferred and is now due. Note the spike used a
   naive `prompt + solution` concatenation with **no prompt-token loss masking** —
   acceptable for a smoke test, a real decision at scale.
4. **Contamination: thresholds don't transfer, and one blind spot is
   fundamental.** The 0.70 code-axis threshold was derived from an 11×24
   distribution and must be re-derived at scale. Two further points the spike
   established:
   - **Intra-corpus deduplication does not exist.** The gate compares
     benchmark × corpus only, which is *linear* in corpus size (the benchmark is
     fixed) — so that direction scales fine. Near-duplicate detection *within* a
     generated corpus is the genuinely missing piece, it is O(n²), and the
     corpus brief's correlation warning makes it necessary.
   - **Some real duplication is uncatchable by text similarity.** A known pair
     (`bench-sql-params` vs a quarantined example) is semantically duplicated
     but scores 0.267 on code and 0.566 on prompt — no threshold catches it
     without flooding false positives. The gate's authors trusted it less than
     a newcomer might; don't mistake "gate passes" for "no contamination."
5. **Does the base model choice still hold?** It was chosen partly to prove the
   machinery on a clean substrate. With the machinery proven, is a
   later-cutoff base now preferable, or does that reintroduce confounds?
6. **How strong should the retrieval arm be, and what may the §3.2 gate claim?**
   The spike's with-docs arm is weak by construction (see §1's warning). Decide
   before the rebuild adjudicates anything: strengthen it (instruct model, real
   PEP excerpt, worked example, few-shot) so a fine-tuning-vs-retrieval verdict
   is fair, or narrow what the gate is permitted to conclude. Gate 1 raised this
   and it was never decided.
7. **What benchmark size and composition can actually discriminate that gate?**
   At n=11, 0/11 carries a ~25% upper confidence bound (rule of three) — thin
   enough that a later "0% → 27%" improvement sits at the edge of meaningful.
   Benchmark redesign is cheap (baselines re-measure in minutes) and should be
   decided deliberately rather than inherited.

---

## 7. Where the detail lives

Branch `worktree-overnight-tstrings-spike` (not merged; treat as reference):

- `docs/superpowers/research/2026-07-30-sp1-baseline-ladder.md` — baselines with
  retained raw completions
- `docs/superpowers/research/2026-07-31-sp2-first-train-eval.md` — the three
  numbers plus the memorization diagnostic
- `docs/superpowers/research/2026-07-30-opus-gate-1.md`,
  `2026-07-31-gate-2.md` — the two independent review gates
- `docs/superpowers/research/2026-07-31-harvest-architecture-pivot.md` — the
  first pivot, itself later superseded
- `.superpowers/sdd/progress.md` — the full task-by-task ledger (git-ignored,
  local to that worktree)
