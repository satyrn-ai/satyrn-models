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

## Convergence status

The SP0–SP2 rebuild and SP5 authoring work now converge through one shared
foundation, not two pipelines. The detailed rationale and required ordering are
in the [roadmap convergence brief](research/2026-08-01-roadmap-convergence-brief.md).

- SP0 R1 remains the next executable task and is unchanged in scope.
- The shared foundation after R1 owns the final corpus row, provenance,
  subprocess verifier, expected-value execution, and common contamination/
  deduplication controls. `harvest` and `authoring` consume it; neither
  reimplements it.
- SP2 is the small, high-trust source and fixture path. SP5 is the primary
  scale path.
- SP6 owns the independent measurement instrument. No corpus may be emitted
  for training until its base and strengthened-docs baselines exist.

## North-Star Steering

The sequence is **measure → harvest → synthesize**, and the order is
load-bearing rather than stylistic. Two steering rules govern the whole
roadmap:

1. **No training corpus before a number exists.** Source inventory, seed
   evaluation, and coverage preparation may proceed, but no corpus is emitted
   or consumed for training until SP6 has established base and
   strengthened-docs baselines on its independent benchmark. The cited
   literature argues against fine-tuning as the default tool; measurement must
   therefore precede the scale path.
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
| F-TDOM-RULED-OUT | An earlier plan ranked `tdom` as the highest-value harvest source and built a harvest architecture around it. Training on tdom would teach tdom's own API surface, not the PEP 750 language feature and stdlib `string.templatelib` API this project exists to teach; two independent failures (zero-t-string examples, vacuous hidden tests) were caught only by review before anything was committed. | **Closed 2026-07-31** by project-owner decision: no training example may **import** `tdom` or any other third-party package. **Narrowed 2026-07-31:** third-party *literals* remain valid **seed** material — `t"<div class={cls}>{body}</div>"` is 100% PEP 750, and only the surrounding library assertions are not. See SP5 §1.1 ("de-libraryization") and [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) section 1. |

## Active

### SP0: Scaffold + Conventions

Clears the placeholders and lays the conventions every later rung depends on.
The user has confirmed the existing scripts were placeholders; nothing here
preserves their structure. Deliberately small — this is groundwork, and the
first real evidence arrives in SP1.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Repo reset.** Retire `main.py`, `make_data.py`, `eval.py`. Preserve the 24 hand-written examples as *seed material only*, tagged as unverified-provenance so they can never silently enter a corpus (their descriptions are the F-CONTAM source and must be quarantined from the benchmark). Establish `docs/superpowers/{specs,plans,research}/`. | Pending |
| R2 | **Corpus record schema.** Moved into the Shared Foundation so both harvest and authoring consume one format-neutral task/provenance contract. | Planned after R1 |
| R3 | **Oracle harness** (closes F-BLIND-ORACLE). Moved into the Shared Foundation: isolated subprocess verification, feature and old-form checks, executed expected values, and live adversarial fixtures. | Planned after R1 |
| R4 | **Project-local skills.** `harvest-corpus`, `verify-example`, `eval-run` in `.claude/skills/`, written after the Shared Foundation establishes their conventions. | Blocked by Shared Foundation |

**R1 done condition:** the placeholder scripts are gone and the 24 legacy
examples are inert quarantine records. The remaining former SP0 deliverables
are owned by the Shared Foundation below.

### Shared Foundation: one verifier and task contract

This milestone is planned immediately after SP0 R1. It reconciles the
SP0–SP2 threat-model requirements with SP5's seed/exercise/property model
before either track implements a second core.

| Rung | Summary | State |
|------|---------|-------|
| F1 | **Merged design and implementation plan.** Define the final corpus row, provenance union, reference-execution path, verifier stage semantics, and authoring/harvest adapters. The reviewed standalone rebuild implementation plan is not executable as written. | Planned after R1 |
| F2 | **Verification core.** Subprocess oracle, old-form and feature checks, hidden expectations derived from executed reference code, typed stage outcomes, and live adversarial fixtures. | Blocked by F1 |
| F3 | **Common gates and adapters.** Benchmark/corpus contamination, intra-corpus dedup, pin enforcement, and adapters from CPython harvest and SP5 rendering into the shared row. | Blocked by F2 |

**Done condition:** one task row verifies through one oracle regardless of
source; a planted f-string, self-referential hidden test, vacuous test, and
wrong-stage rejection each fail live; no authoring-specific verifier exists.

### SP1: Measurement Spine

The gate that decides whether this project trains a model or ships a retrieval
layer. Produces three numbers on one held-out benchmark, all from the same
harness. It starts after the Shared Foundation; SP6 provides its benchmark.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Held-out benchmark.** Superseded by SP6's redesigned 30–40 task benchmark, including a naturalistic pre-pattern slice. | Owned by SP6 |
| R2 | **Contamination gate** (closes F-CONTAM). Implemented in the Shared Foundation and exercised by SP6 against every corpus source. | Owned by Shared Foundation / SP6 |
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

### SP6: Benchmark Redesign

**Blocks corpus emission for training, pilot training, and SP5 R8.** Source
inventory and seed preparation may proceed while SP6 is built, but a generated
corpus cannot become training input before its independent benchmark and
base/docs baselines exist. Runs on measurement, not corpus, so it belongs
outside SP5: the same instrument scores SP1's baseline ladder, SP2's harvest
path, and SP5's sweep, and SP5 must not own the instrument it is itself scored
by.

The benchmark is **no longer frozen**. The
[spike findings](research/2026-07-31-spike-findings.md) §5 moved that discipline
to *expired*: the attached baselines are two 0% numbers that a greedy-decoding
rerun reproduces in minutes, so freezing an 11-task instrument to protect them
is a bad trade.

Four things it must settle:

1. **Size.** At `n=11`, 0/11 carries a ~25% upper confidence bound by the rule
   of three — thin enough that a later "0% → 27%" sits at the edge of meaning,
   and far too thin to read SP5 R8's 500 → 2k → 5k differences.
2. **Naturalistic completion tasks**, scored only on "used a template
   correctly" rather than on an introspectable property value. **Authored
   before any SP5 pattern exists**, so they cannot be shaped by whichever
   patterns turn out to be easy to write. This is the only available mitigation
   for the verifiability-bias risk in SP5 spec §8: corpus and benchmark are
   currently drawn from the same execution-checkable distribution, so the scale
   curve could rise while real prior-fallback behaviour stays flat and no number
   in the system would show it.
3. **Retrieval-arm strength** ([spike findings](research/2026-07-31-spike-findings.md)
   §6.6, raised at Gate 1 and never decided). The spike's with-docs arm was an
   8-line comment summary fed to a *base* model at greedy decode — weak by
   construction. `base + docs = 0%` supports "this base does not know
   t-strings"; it does **not** support "retrieval loses." Either strengthen the
   arm or narrow what the §3.2 gate may conclude.
4. **Composition targets** — the balance between authoring t-strings, consuming
   templates, and constructor-API usage. The `n=24` anchor is polluted by having
   only ~9 of 24 rows contain a t-string literal, so curve points must be
   composition-matched to be comparable.

Supersedes SP1 R1's open question. **Done condition:** a benchmark whose size
and composition can discriminate the §3.2 gate, carrying a naturalistic slice
authored ahead of any pattern, with baselines re-measured and the retrieval-arm
decision recorded.

### SP5: Seed-and-Pattern Corpus Authoring

**Promoted ahead of SP3 — this is now the primary corpus source, not a
gap-filler.** **Specced 2026-07-31:**
[seed-and-pattern corpus design](specs/2026-07-31-seed-and-pattern-corpus-design.md)
is the source of truth; the
[brief](research/2026-07-31-corpus-authoring-brief.md) is its input and is
superseded wherever the two differ.

Two facts forced this. **No training example may import a third-party
package** — examples must teach the PEP 750 language feature and the
`string.templatelib` stdlib API, not a library's API surface. Third-party
*literals* nonetheless remain valid **seed** material (spec §1.1); the brief's
blanket "all third-party sources are ruled out" is narrowed accordingly. And
**what remains to harvest is tiny** — CPython's `test_templatelib.py` is 193
lines / 13 test methods, plus a few dozen PEP 750 examples. That is 1–2 orders
of magnitude below the "low thousands" target, so harvest cannot be the primary
source and SP3's framing is superseded.

The design inverts the human's role: **source, not gate.** Review effort scales
with output volume; seeding effort scales with diversity needed, and each seed
multiplies. Ground truth comes from *executing* real templates, never from a
model — which is what makes a large auto-accept path safe. **No LLM call exists
in the pipeline**: patterns are drafted in chat and land as reviewed source.
Published precedent:
[Template-Based Data Generation](https://arxiv.org/abs/2411.18104).

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Source validation + extraction.** `grep -c 't"' ≥ 1` across every candidate repo *before* building extraction — the F-TDOM-RULED-OUT corrective, made standing. `sources.toml` records URL, pinned SHA, license, and post-extraction novel-skeleton contribution. AST extraction of literals with free names and palette-proposed bindings; content-derived seed ids. | Planned |
| R2a | **Oracle + pytest failed-vs-error stage parser**, with output fixtures. | Planned |
| R2b | **Data model** — `Seed`, `Exercise`, `Property` tagged union, arity invariant enforced at construction. | Planned |
| R2c | **Row-level gate chain** + planted defects 1, 3, 4, 7. | Planned |
| R2d | **Assertion-grammar checker** + planted defects 2, 8. | Planned |
| R3 | **Seed evaluation + review CLI.** Subprocess evaluator run twice for determinism, repr round-trip enforced. Facts-first review with palette auto-accept and cached binding decisions. Seed dedup by fingerprint bucket. | Planned |
| R4 | **Coverage analysis + seed authoring.** Grammar-shape × task-type matrix, not API-name coverage. Owner authors seeds filling measured gaps; Self-Instruct's 100–200 is the floor for the combined budget. | Planned |
| R5 | **Patterns and generation.** Renderers, cross-projection consistency check, composition classifier, pattern registry with approvals keyed on source hash, `audit-pattern`. Planted defects 5, 6. | Planned |
| R6a | **Oracle cache + process pool**, with cold/warm equivalence tests. | Planned |
| R6b | **Build-gate integration** — contamination, intra-corpus dedup, composition-mix reporting. | Planned |
| R6c | **Reports** — `build.md`, committed `dropped.jsonl` with full row content. | Planned |
| R6d | **Adjudication CLI** + migration report. UI rather than verification; may trail R7. | Planned |
| R7 | **Pilot + threshold derivation.** ~500 rows; diversity thresholds, classifier tolerance band, contamination drop-rate bound, and review-budget fraction each committed with their derivation. | Planned |
| R8 | **Scale sweep.** 500 → 2k → 5k, composition held constant, decision rule applied. Absorbs SP3 R4. **Blocked by SP6.** | Planned |

Rungs are deliberately small around verification-heavy work: each planted defect
is *designed to fail first*, so bundling several into one rung builds in several
fix rounds — the shape that cost the spike a task needing two fix rounds, a
pivot, and deletion.

**Done condition (falsifiable — full form in spec §9):** `authoring build
--no-cache` reproduces the corpus byte-identically from committed inputs; all
eight planted defects fail live in CI; ≥5k rows within the R7 bands with no
contamination above bound; human decisions ≤ the R7 review-budget fraction; and
three composition-matched sweep points recorded with the decision rule's
verdict — **either verdict counts**, per the negative-result rule above.

**Prerequisite — partially closed.** The code-similarity half is **closed**: the
spike's dual-axis gate (prompt at 0.85, normalized code at 0.70, thresholds from
a measured distribution) covers it, though 0.70 was derived from an 11×24
distribution and must be re-derived at scale. **Intra-corpus** near-duplicate
detection, which the spike never had, is now owned by SP5 spec §5.1 and gates
from build one. Note the residual the spike documented: some real duplication is
uncatchable by text similarity on either axis, so "gate passes" never means "no
contamination."

### SP3: Targeted Synthesis

> **Superseded by SP5 (2026-07-31), resolved at SP5's brainstorm.** SP3 assumed
> synthesis would be a gap-filler after a large harvest; harvest cannot reach
> scale under stdlib-only sourcing, so SP5 owns primary corpus generation.
> Disposition of each rung: **R2** (seeded generator) and **R3** (contrastive
> old→new pairs, negative coverage) are absorbed into SP5's pattern registry —
> negative coverage is the `NegativeControl` variant of SP5's `Property` union.
> **R4** (scale sweep) is SP5 R8. **R1** (gap analysis) survives in altered
> form as SP5 R4's coverage analysis, run against seeds rather than against a
> fine-tune's errors; a post-training gap analysis may still earn a rung once
> SP5 R8 produces a curve.
>
> **This sub-project is closed. It will not open as written.**

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
| B-HEADER | Prompt-format overfitting: every placeholder example and eval prompt began `# Python 3.14 t-strings:`, a trigger phrase no real user types. Vary comment/docstring/chat framings. **Returns at corpus scale**: SP5's prompts come from a few dozen renderer phrasings, so the model can learn format→answer mappings and transfer nothing. Tracked as SP5's prompt-text diversity metric (spec §5.1), which gates pattern approval. | SP6 benchmark authoring; SP5 R5 renderers |
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
