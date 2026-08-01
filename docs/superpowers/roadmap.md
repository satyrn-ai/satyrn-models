# satyrn-model Roadmap

The specs in `docs/superpowers/specs/` and plans in `docs/superpowers/plans/`
are the source of truth for *what* each task does. This file is the cross-task
index: sequence, status, and links.

**Next task:** SP0 R1 — repo reset. Nothing else may start first: SP0 R1
discards the placeholder scripts whose two verified defects
([contamination](#verified-findings), [blind oracle](#verified-findings))
would otherwise contaminate every downstream measurement.

> ## A throwaway spike has already run this roadmap end to end
>
> Branch `worktree-overnight-tstrings-spike` executed SP0–SP2 and produced a
> working measure → harvest → train → evaluate loop, two independent review
> gates, and a data-scale anchor (n=24 → 0% held-out, ~100% memorized). **Its
> code is deliberately not merged and should not be reused.**
>
> Rungs below therefore read *Pending* against `main`, which still contains the
> pre-spike placeholder scripts — but they are **informed, not untried**. Before
> designing any of them, read
> [spike findings](research/2026-07-31-spike-findings.md): what was proven, the
> bug class that dominated the work, the technical traps, and the decisions that
> earned their keep versus the ones that expired.

Design source of record: the
[measure-harvest-synthesize spec](specs/2026-07-30-dataset-workflow-design.md).
Research of record: [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) —
**required pre-reading for every rung's brainstorm.** Each rung below is a
*shape*, not a spec; every rung gets its own brainstorm → spec → plan before
code, and its own Definition-of-Done.

## North-Star Steering

The sequence is **measure → harvest → synthesize**, and the order is
load-bearing rather than stylistic. Two steering rules govern the whole
roadmap:

1. **No data work before a number exists.** The cited literature's own results
   argue against fine-tuning as the default tool — documentation-in-context
   reaches ~66% executable on post-cutoff API tasks, while the only weight-update
   evidence cited is negative. SP1 exists to find out which tool wins here before
   SP2 spends effort.
2. **A negative result is a success.** SP1 R4's gate can legitimately conclude
   that retrieval beats fine-tuning for this project. That verdict closes the
   spec successfully and re-scopes SP3/SP4; it is not a failure to be
   rationalized away.

### Verified findings

Three findings, all confirmed directly against the environment on 2026-07-30,
that the roadmap is built to avoid repeating:

| ID | Finding | Status |
|----|---------|--------|
| F-CONTAM | 7 of 10 `eval.py` prompts are byte-identical to `make_data.py` training descriptions; 2 more differ cosmetically. Reported pass rates are memorization scores. | Open — closed by SP0 R1 + SP1 R3 |
| F-BLIND-ORACLE | `validate_snippet` defines success as "did not raise," so an f-string answer to a template task passes, as does `pass`. The harness cannot see the prior-fallback failure mode. | Open — closed by SP0 R3 |
| F-STALE-CPYTHON | The CPython source was a **fork** (`t-strings/cpython`) on an in-progress docs branch dated 2025-06-17, ~4 months pre-3.14.0, missing `string.templatelib.convert()` entirely — the canonical `!r`/`!s`/`!a` helper, and precisely the renderer idiom this project teaches. | **Closed 2026-07-30.** Replaced by a shallow clone of official upstream `python/cpython` at tag `v3.14.5` (`~/projects/pauleveritt/cpython-3.14.5`, 157 MB), matching the verifying interpreter. Old checkout removed; its branch survives on the fork's remote. |
| F-TDOM-RULED-OUT | An earlier plan ranked `tdom` as the highest-value harvest source and built a harvest architecture around it. Training on tdom would teach tdom's own API surface, not the PEP 750 language feature and stdlib `string.templatelib` API this project exists to teach; two independent failures (zero-t-string examples, vacuous hidden tests) were caught only by review before anything was committed. | **Closed 2026-07-31** by project-owner decision: no training example may import `tdom` or any other third-party package; harvest is stdlib-only. See [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) section 1 for the full record. |

## Active

### SP0: Scaffold + Conventions

Clears the placeholders and lays the conventions every later rung depends on.
The user has confirmed the existing scripts were placeholders; nothing here
preserves their structure. Deliberately small — this is groundwork, and the
first real evidence arrives in SP1.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Repo reset.** Retire `main.py`, `make_data.py`, `eval.py`. Preserve the 24 hand-written examples as *seed material only*, tagged as unverified-provenance so they can never silently enter a corpus (their descriptions are the F-CONTAM source and must be quarantined from the benchmark). Establish `docs/superpowers/{specs,plans,research}/`. | Pending |
| R2 | **Corpus record schema.** The format-neutral row of spec §3.6: task, reference solution, hidden tests, provenance (source file, upstream commit/tag, verifying interpreter version). Renderers to training format come later, deliberately — the FIM-vs-chat decision stays deferred. | Pending |
| R3 | **Oracle harness** (closes F-BLIND-ORACLE). pytest in a subprocess, with timeout. Three checks per task: hidden asserts, `Template`-was-constructed, and an old-form canary rejecting f-string/`.format()` solutions. **Verification obligation:** a deliberately planted f-string solution to a template task must be demonstrated to *fail*, live — not asserted in prose. | Pending |
| R4 | **Project-local skills.** `harvest-corpus`, `verify-example`, `eval-run` in `.claude/skills/`, written to encode the conventions R2/R3 actually established. Not written speculatively — a skill describing a convention that does not yet exist is a liability. | Pending |

**Done condition:** the placeholder scripts are gone, a corpus row schema with
mandatory provenance exists, the oracle rejects a planted f-string solution in a
live run, and three skills encode the conventions as built.

### SP1: Measurement Spine

The gate that decides whether this project trains a model or ships a retrieval
layer. Produces three numbers on one held-out benchmark, all from the same
harness. Blocked by SP0 R3 (the oracle is the scoring mechanism).

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Held-out benchmark.** t-string tasks with hidden-test oracles, authored to be disjoint from every harvest source. Built and authored: 11 tasks, all stdlib-only, in `benchmark/tasks.py`, from authored fixtures exercising `string.templatelib` directly rather than any third-party library's tasks. | Pending — the spike built an 11-task version worth using as a starting point, but see [spike findings](research/2026-07-31-spike-findings.md) §6.7: n=11 may be too thin to discriminate the §3.2 gate |
| R2 | **Contamination gate** (closes F-CONTAM). Automated disjointness check between benchmark and every training corpus, at both exact-match and near-paraphrase level. **Fails loudly rather than reporting a score** — a contaminated benchmark must halt the run, not annotate it. | Pending |
| R3 | **Baseline ladder.** Score base zero-shot and base + PEP 750 docs-in-context through the local oMLX endpoint (`127.0.0.1:8001/v1`, already serving via `mellum2-mlx`). Investigate reusing tainie's `src/tainie/eval/` ladder before building a new harness — it already scores models on tdom tasks (a sibling project's own benchmark; not a source of training data for this project, which is stdlib-only). | Pending |
| R4 | **Base-model audit.** Compare ≥2 candidate bases zero-shot on R1's benchmark. Qwen2.5-Coder-7B (Sept 2024) predates PEP 750's *acceptance*; a 2025/2026-cutoff base may already half-know this material, which would turn knowledge injection into the much easier problem of reinforcement. Record the choice and its reasoning. **Must happen before SP2 scales any data.** | Pending |

**Done condition:** three comparable numbers exist on one uncontaminated
benchmark, the contamination gate demonstrably halts on a planted duplicate, a
base model is chosen on evidence, and the spec §3.2 gate has a recorded verdict.

### SP2: Harvest

Converts real code into verified training data. Nearly free relative to
synthesis, and grounded in real usage per OSS-Instruct's central finding.
Blocked by SP1 R4 (base choice) and SP0 R2 (row schema).

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Assert the pin.** Source is already pinned (F-STALE-CPYTHON closed 2026-07-30: official upstream at `v3.14.5`). This rung makes it *enforced* — the harvester verifies the tree's tag matches the verifying interpreter's version and **fails the run** otherwise, rather than silently producing pre-release API examples. Use `main` only for 3.15 material, recorded as such. | Pending |
| R2 | **Stdlib-sourced harvest.** Real test function → task: signature/intent as prompt, t-string-bearing body as reference, its own assertions as hidden oracle. Sourced from the pinned CPython test suite and PEP 750/What's New examples only — `tdom` is ruled out as a corpus source (see F-TDOM-RULED-OUT above and `DATASET_METHODOLOGY.md` section 1). | Pending |
| R3 | **CPython harvest.** `Lib/test/test_string/test_templatelib.py` and the templatelib implementation, from the pinned tree, with provenance recorded per row. | Pending |
| R4 | **First training run.** mlx-lm directly, not Unsloth's MLX backend (unverified rank/alpha handling and prompt-token loss masking). Score against SP1's baselines with the same harness. | Pending |

**Done condition:** a provenance-complete corpus harvested from the pinned
CPython test suite and other stdlib-only sources, one training run scored
against the SP1 baselines, and the §3.2 gate evaluated with its verdict
recorded — including if retrieval wins.

## Planned

### SP5: Seed-and-Pattern Corpus Authoring

**Promoted ahead of SP3 — this is now the primary corpus source, not a
gap-filler.** Full brief:
[seed-and-pattern corpus authoring](research/2026-07-31-corpus-authoring-brief.md)
— **required pre-reading for this sub-project's brainstorm.**

Two facts forced this. **Third-party sources are ruled out**: examples must
teach the PEP 750 language feature and the `string.templatelib` stdlib API, not
a library's API surface, so a corpus built on `tdom` would bind the model's
notion of t-strings to one niche library. And **what remains is tiny** —
CPython's `test_templatelib.py` is 193 lines / 13 test methods, plus a few dozen
PEP 750 examples. That is 1–2 orders of magnitude below the "low thousands"
target, so harvest cannot be the primary source and SP3's framing (synthesis
gated on harvest proving insufficient) is superseded.

The design inverts the human's role: **source, not gate.** Review effort scales
with output volume; seeding effort scales with diversity needed, and each seed
multiplies. Ground truth comes from *executing* real templates, never from a
model — which is what makes a large auto-accept path safe, and is the structural
fix for the vacuous-hidden-test defect found in the spike. The method has
published precedent in
[Template-Based Data Generation](https://arxiv.org/abs/2411.18104).

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Seed extraction.** Pull real t-string *literals* out of real code — including third-party sources, whose literals are pure stdlib artifacts even though their surrounding assertions are not ("de-libraryization"). Record provenance per seed. Output is seeds only; no third-party import ever reaches the corpus. | Planned |
| R2 | **Seed authoring + gap analysis.** Owner hand-authors seeds covering shapes extraction missed. Self-Instruct's 100–200 seeds is the calibration point. Seed *diversity* is the target, not count — see the correlation risk in the brief. | Planned |
| R3 | **Pattern proposal + one-time approval.** LLM proposes parameterized exercise kinds; owner approves each once. Review is per-pattern (dozens), not per-example (hundreds). Favour patterns that **compose or transform** seeds over pure introspection, to break output correlation. | Planned |
| R4 | **Deterministic cross-product with executed ground truth.** Apply approved patterns across seeds; compute every expected value by running the template on the pinned interpreter. Route all output through the existing oracle contract plus the self-verification, on-target, and anti-vacuity gates. | Planned |
| R5 | **Adjudication surface.** Owner sees only the uncertain middle: verified-but-degenerate, near-duplicate, low-confidence. Everything cleanly verified auto-accepts; everything cleanly failing auto-rejects with a reason. | Planned |
| R6 | **Scale sweep on effective diversity.** 500 → 2k → 5k against the fixed benchmark, measuring *effective* diversity rather than row count, so the correlation risk is observable rather than theoretical. Absorbs SP3 R4. | Planned |

**Done condition:** a corpus of verified, provenance-tagged, stdlib-only
examples at a scale the harvest path cannot reach, every expected value derived
by execution, produced with the owner's time spent on seeds and pattern
approval rather than per-example review — and the scale/diversity curve
recorded.

**Prerequisite:** contamination detection must handle **code** similarity,
not prompt text alone (a prompt-only gate is structurally weakest against
generated corpora, whose prompts differ in wording even when code is
duplicated), and must add **intra-corpus** near-duplicate detection, which
the spike never had. See
[spike findings](research/2026-07-31-spike-findings.md) §6.4.

### SP3: Targeted Synthesis

> **Largely superseded by SP5 (2026-07-31).** SP3 assumed synthesis would be a
> gap-filler after a large harvest; harvest cannot reach scale under
> stdlib-only sourcing, so SP5 owns primary corpus generation. R3 (contrastive
> old→new pairs) and R4 (scale sweep) are absorbed into SP5 R3/R6. What may
> still survive as distinct: R1's gap analysis, run *against* an SP5 corpus
> rather than a harvested one. Resolve during SP5's brainstorm — open question
> 5 in the [brief](research/2026-07-31-corpus-authoring-brief.md).

**Gated on SP2 R4 showing measured gaps.** Does not start merely because
harvesting finished. If the harvested corpus already clears the baseline gate,
this sub-project may never open.

| Rung | Summary | State |
|------|---------|-------|
| R1 | Gap analysis — what the fine-tune still gets wrong, by category, from SP1's harness rather than by inspection | Planned |
| R2 | Seeded generator (OSS-Instruct shape: sample real code, generate tasks from it), execution-verified through the SP0 R3 oracle | Planned |
| R3 | Contrastive old→new pairs and negative coverage (tasks where a template is the *wrong* choice), targeting the prior-fallback failure mode | Planned |
| R4 | Scale sweep: 500 → 2k → 5k against the fixed benchmark. No published recipe fits this task; let the curve decide rather than guessing a number | Planned |

**Done condition:** synthesis exists only where measurement proved it necessary,
and the scale curve is recorded.

### SP4: Generalize Beyond t-strings

**Gated on the t-strings slice producing a trustworthy number** (either verdict).
Adds 3.14/3.15 features through the pluggable interface the earlier
sub-projects were designed around. Feature inventory must be scraped from the
actual What's New documents and changelog — not asked of a model, which will
part-confabulate 3.15. Per [PEP 790](https://peps.python.org/pep-0790/), 3.15
hit feature freeze at beta 1 on 2026-05-07 (final 2026-10-01), so its feature
set is frozen and safe to train against now.

**Done condition:** at least one non-t-string feature runs end-to-end through
the same machinery at materially lower marginal cost than the first.

## Backlog

Open questions, not queued. Each needs evidence or a trigger before it earns a
rung.

| ID | Item | Trigger |
|----|------|---------|
| B-FORMAT | FIM vs chat deployment shape. Deliberately deferred by spec §3.6; corpus is stored format-neutral so both can be trained and compared. | A deployment target is chosen, or SP2 R4 shows format is limiting |
| B-REPLAY | Replay data to mitigate forgetting. Real per the scaling laws, but forgetting scales with update steps and the placeholder run was ~36 steps — not yet urgent. Mix 10–30% generic verified Python. | Corpus reaches low-thousands scale |
| B-RANK | LoRA rank sweep with deliberate alpha adjustment (placeholder paired r=16 with alpha=16). Direction is defensible; the specific 64–128 figure is not grounded. | Data stops being the binding constraint |
| B-HEADER | Prompt-format overfitting: every placeholder example and eval prompt began `# Python 3.14 t-strings:`, a trigger phrase no real user types. Vary comment/docstring/chat framings. | SP1 R1 benchmark authoring |
| B-TOKENIZER | Confirm how `t"` / `rt"` tokenize. Likely a non-issue — byte-level BPE needs no vocab change, same as `rb"`. Five-minute check, not a workstream. | Cheap; fold into SP1 R4 |
| B-LOSS-MASK | Whether the chosen trainer masks prompt/header tokens from loss. Placeholder config likely trained on full sequences, spending gradient budget learning the header. | SP2 R4 |

## Completed

### Research + review phase (2026-07-30)

Literature review across five papers, an independent critical review that
overturned the original central claim, and direct verification of three findings
against this environment.

The reversed claim is worth recording: the first analysis argued that
[Syntax Without Semantics](https://arxiv.org/abs/2605.15607) put this project on
the easy side of the problem, since fine-tuning teaches syntax readily and only
semantics resists. Review established that PyLang had **zero competing prior**,
whereas f-strings are among the most frequent patterns in the pretraining corpus
— so on the axis that matters here, prior interference, PyLang is the *easier*
case. t-strings also carry real usage semantics (`t"..."` returns a `Template`,
not a `str`, and correct use requires the renderer idiom), which is precisely
what that paper found does not transfer. The review also corrected misquoted
failure-mode denominators, established that neither API-evolution paper actually
tested fine-tuning (so the data-design rules are inference, not evidence), and
found the volume anchor was a benchmark's density rather than a training recipe.

Output: [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) and the
[workflow spec](specs/2026-07-30-dataset-workflow-design.md).
