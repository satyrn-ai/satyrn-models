# satyrn-model Roadmap

The specs in `docs/superpowers/specs/` and plans in `docs/superpowers/plans/`
are the source of truth for *what* each task does. This file is the cross-task
index: sequence, status, and links.

**Next integration task:** provider SP0 R1 — repo reset. It must land before
this branch merges provider code or publishes rows because it discards the
placeholder scripts whose two verified defects
([contamination](#verified-findings), [blind oracle](#verified-findings))
would otherwise contaminate every downstream measurement. SP5 source-manifest
and seed-preparation work may proceed independently meanwhile.

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

Data-project source of record: the
[seed-and-pattern design](specs/2026-07-31-seed-and-pattern-corpus-design.md)
and [t-string training-data plan](plans/2026-08-01-tstring-training-data.md).
The earlier measure-harvest-synthesize spec is historical programme context and
does not override the provider/consumer boundary.
Research of record: [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) —
**required pre-reading for every rung's brainstorm.** Each rung below is a
*shape*, not a spec; every rung gets its own brainstorm → spec → plan before
code, and its own Definition-of-Done.

## Project boundary

This worktree is the **t-string training-data producer**. The detailed boundary
is in the [provider/consumer brief](research/2026-08-01-roadmap-convergence-brief.md).

- `worktree-tstrings-rebuild` owns dataset contracts, reference/candidate
  verification, common contamination controls, the independent benchmark,
  training, and evaluation.
- This effort owns all t-string data production: CPython/PEP and third-party
  literal sources, seeds, properties, patterns, generated rows, reports, and
  composition-matched dataset snapshots.
- The provider executes this project's t-string policy and adversarial cases.
  This project does not implement a second oracle, benchmark, trainer, or model
  client.

## North-Star Steering

The programme still sequences **measure → data → train**, but ownership is now
explicit. Two steering rules govern it:

1. **Data publication and model consumption are separate gates.** This project
   may build and publish reproducible datasets once provider verification and
   contamination contracts are available. The provider decides when a dataset
   is eligible for training and records the base/docs measurements first.
2. **A negative result is a provider success, not a data-project gate.** The
   provider may conclude that retrieval beats fine-tuning. That changes later
   model strategy without retroactively invalidating reproducible t-string
   dataset publication.

### Verified findings

Three findings, all confirmed directly against the environment on 2026-07-30,
that the roadmap is built to avoid repeating:

| ID | Finding | Status |
|----|---------|--------|
| F-CONTAM | 7 of 10 `eval.py` prompts are byte-identical to `make_data.py` training descriptions; 2 more differ cosmetically. Reported pass rates are memorization scores. | Open — closed by SP0 R1 + SP1 R3 |
| F-BLIND-ORACLE | `validate_snippet` defines success as "did not raise," so an f-string answer to a template task passes, as does `pass`. The harness cannot see the prior-fallback failure mode. | Open — closed by SP0 R3 |
| F-STALE-CPYTHON | The CPython source was a **fork** (`t-strings/cpython`) on an in-progress docs branch dated 2025-06-17, ~4 months pre-3.14.0, missing `string.templatelib.convert()` entirely — the canonical `!r`/`!s`/`!a` helper, and precisely the renderer idiom this project teaches. | Official upstream at `v3.14.5` is now present, but the installed worktree interpreter reports `3.14.2`; the former claim of an exact match is therefore **open pending an enforced exact-tag/interpreter check**. |
| F-TDOM-RULED-OUT | An earlier plan ranked `tdom` as the highest-value harvest source and built a harvest architecture around it. Training on tdom would teach tdom's own API surface, not the PEP 750 language feature and stdlib `string.templatelib` API this project exists to teach; two independent failures (zero-t-string examples, vacuous hidden tests) were caught only by review before anything was committed. | **Closed 2026-07-31** by project-owner decision: no training example may **import** `tdom` or any other third-party package. **Narrowed 2026-07-31:** third-party *literals* remain valid **seed** material — `t"<div class={cls}>{body}</div>"` is 100% PEP 750, and only the surrounding library assertions are not. See SP5 §1.1 ("de-libraryization") and [`DATASET_METHODOLOGY.md`](../../DATASET_METHODOLOGY.md) section 1. |

## Active

### External provider prerequisite: SP0 Scaffold + Conventions

Clears the placeholders and lays the conventions every later rung depends on.
The user has confirmed the existing scripts were placeholders; nothing here
preserves their structure. Deliberately small — this is groundwork, and the
first real evidence arrives in SP1.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Repo reset.** Retire `main.py`, `make_data.py`, `eval.py`. Preserve the 24 hand-written examples as *seed material only*, tagged as unverified-provenance so they can never silently enter a corpus (their descriptions are the F-CONTAM source and must be quarantined from the benchmark). Establish `docs/superpowers/{specs,plans,research}/`. | Pending |
| R2 | **Dataset contract.** Provider-owned format-neutral task/provenance wire contract consumed by this project. | External dependency |
| R3 | **Oracle harness** (closes F-BLIND-ORACLE). Provider-owned reference/candidate execution and typed stages; this project supplies t-string policy. | External dependency |
| R4 | **Provider workflow skills.** Written by the provider against its established contracts. | External dependency |

**Data-project dependency:** the placeholder scripts are gone, legacy examples
are inert quarantine records, and this branch must consume the resulting
package/test baseline before collection implementation. Provider contract
fixtures are a later dependency for qualified rows, not for local collection
behavior.

### External provider: verification and dataset contracts

This milestone is implemented on `worktree-tstrings-rebuild`. After the SP0 R1
package/reset baseline is consumed, SP5 blocks only where it needs the provider
API; source validation and seed preparation may proceed without provider calls.

| Rung | Summary | State |
|------|---------|-------|
| F1 | **Versioned consumer contract.** `TaskRecord`, declarative checks, policy protocol, provenance, and dataset manifest fixtures. | Provider-owned |
| F2 | **Verification core.** Reference-derived observations, candidate oracle, typed stages, and executable adversarial registry. | Provider-owned |
| F3 | **Common consumer services.** Benchmark contamination, ingest validation, training, and evaluation APIs. Source pinning and intra-corpus composition remain data work. | Provider-owned |

**Done condition for SP5 integration:** provider fixtures pass in this
worktree, and a rendered t-string row plus every planted defect returns the
expected provider stage without local oracle code.

### External provider: SP1 Measurement Spine

The provider gate that decides whether it trains a model or recommends a
retrieval layer. It produces comparable numbers on one held-out benchmark. SP5
records the benchmark fingerprint only for contamination.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Held-out benchmark.** Superseded by the provider's redesigned 30–40 task benchmark, including a naturalistic pre-pattern slice. | Provider-owned |
| R2 | **Contamination gate** (closes F-CONTAM). Provider API exercised by SP5 builds against a supplied benchmark fingerprint. | Provider-owned; consumed here |
| R3 | **Baseline ladder.** Provider scores base zero-shot and a strengthened, cited PEP 750 docs-in-context arm through its model client and retains raw artifacts. SP5 neither selects the endpoint nor implements the harness. | Provider-owned |
| R4 | **Base-model audit.** Provider compares at least two eligible bases on the frozen benchmark and records cutoff, tokenizer, license, hardware fit, score, and contamination rationale before scale training. This does not block SP5 data production. | Provider-owned |

**Done condition:** three comparable numbers exist on one uncontaminated
benchmark, the contamination gate demonstrably halts on a planted duplicate, a
base model is chosen on evidence, and the spec §3.2 gate has a recorded verdict.

### SP2: Harvest

Converts real code into verified training data. Nearly free relative to
synthesis, and grounded in real usage per OSS-Instruct's central finding.
Blocked by the provider dataset/verification contract, not by model choice.
These rungs are the source-derived path inside the t-string training-data plan,
not a separate package or provider milestone.

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Assert the pin.** Official upstream is available at `v3.14.5`, but F-STALE-CPYTHON stays open until the harvester verifies an exact tree-tag ↔ verifying-interpreter match and **fails the run** otherwise. Use `main` only for 3.15 material, recorded as such. | Pending |
| R2 | **Stdlib-sourced harvest.** Real test function → task: signature/intent as prompt, t-string-bearing body as reference program, and assertions translated into declarative provider checks without private CPython helpers. Sourced from pinned CPython and PEP 750/What's New only. | Pending |
| R3 | **CPython harvest.** `Lib/test/test_string/test_templatelib.py` and the templatelib implementation, from the pinned tree, with provenance recorded per row. | Pending |
| R4 | **Harvested dataset handoff.** Publish verified rows and a manifest through the provider contract; no training run occurs in this project. | Pending |

**Done condition:** a provenance-complete harvested dataset from pinned
CPython/PEP sources validates through the provider and is available as seed and
row input to SP5. Training and baseline verdicts are external.

## Planned

### SP6: Benchmark Redesign

**Provider-owned.** It does not block source, seed, facts, or policy work. Its
naturalistic slice must be sealed before SP5 pattern authoring begins. A final
SP5 snapshot requires the benchmark fingerprint and the provider's calibrated
contamination result. The provider blocks training until the benchmark and
base/docs baselines exist.

The old 11-task benchmark is **no longer frozen**. The replacement is frozen
before baselines and pattern authoring. The
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
   before SP5 pattern authoring**, so they cannot be shaped by whichever
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
multiplies. Provider observations come from *executing* real templates, never
from a model; policy, qualification, and data gates make the automated path
auditable rather than infallible. **No LLM call exists in the pipeline**:
patterns are drafted in chat and land as reviewed source.
Published precedent:
[Template-Based Data Generation](https://arxiv.org/abs/2411.18104).

| Rung | Summary | State |
|------|---------|-------|
| R1 | **Manifest + local collection model.** After consuming the provider-owned reset/package baseline, exact source/verifier pins, allowed licenses and attribution, `SeedOccurrence` → multi-origin normalized `Seed`, canonical multi-property task intent plus policy-intent projection, and source-exercise candidates. No provider API dependency. | Planned |
| R2 | **Safe extraction + collection checkpoint.** AST extraction never imports sources; a pure-expression safety grammar precedes provider execution. Cover→Author→Cover creates committed coverage, source/license inventory, a data-owner composition profile, and an explicitly unqualified collection checkpoint. | Planned |
| R3a | **Provider adapter + render-to-task fixtures.** Render a minimal `TaskRecord` plus policy-intent configuration from canonical intent before consuming reference execution, candidate verification, and typed stages; implement no oracle. | Planned |
| R3b | **Provider facts, policy, and qualification.** Facts/review are keyed by rendered task and provider environment; t-string policy includes construct/convert and dynamic-format-spec precision. | Planned |
| R4 | **Patterns and generation.** Renderers, cross-projection consistency check, composition classifier, and `audit-pattern`; approval/cache keys use transitive pattern-input fingerprints, so helper/renderer changes invalidate approval. | Planned |
| R6a | **Provider integration + generation cache.** Contract compatibility, provider cold/warm equivalence, and pure-generation cache invalidation. | Planned |
| R6b | **Build-gate integration** — provider contamination/eligibility, exact intra-corpus dedup, structural diversity reporting/sampling caps, composition reporting, and planted defect 8. | Planned |
| R6c | **Reports** — `build.md`, committed `dropped.jsonl` with full row content, and snapshot-contained source/seed lineage plus NOTICE material. | Planned |
| R6d | **Adjudication CLI** + migration report. UI rather than verification; may trail R7. | Planned |
| R7 | **Pilot + threshold derivation.** ~500 rows; diversity thresholds, classifier tolerance band, and review-budget fraction committed with derivations. Supply calibration material for provider-owned contamination thresholds; any conflict still halts. | Planned |
| R8 | **Dataset slice publication.** Immutable nested, stratified 500 ⊂ 2k ⊂ 5k snapshots with composition held constant against the versioned data-owner profile, self-contained lineage manifests, and effective-diversity reports. Provider trains and scores them. | Planned |

Rungs are deliberately small around verification-heavy work: each planted defect
is *designed to fail first*, so bundling several into one rung builds in several
fix rounds — the shape that cost the spike a task needing two fix rounds, a
pivot, and deletion.

**Done condition (falsifiable — full form in spec §9):** `authoring build
--no-cache` reproduces the corpus byte-identically from committed inputs; all
ten planted defects fail at their expected provider/data-policy stages; ≥5k
rows fall within R7 bands; and immutable, composition-matched 500/2k/5k
snapshots are published. No model-performance verdict is required here.

**Prerequisite — provider-owned.** The spike established that prompt and code
similarity need separate axes, but its 0.85/0.70 thresholds came from an 11×24
distribution and are not carried forward as truth. The provider recalibrates
them against SP5's 500-row pilot and halts on any benchmark conflict. SP5 owns
exact intra-corpus dedup from build one; structural fingerprints are diversity
metrics, not duplicate proof. Semantic duplicates that score low on both axes
remain an explicit residual risk.

### SP3: Targeted Synthesis

**Closed and absorbed into SP5.** Seeded generation and negative controls live
in SP5 patterns; seed-side gap analysis lives in SP5 coverage. The former scale
sweep is split correctly: SP5 publishes matched 500/2k/5k snapshots and the
provider trains/scores them. No SP3 implementation work remains.

### SP4: Generalize Beyond t-strings

**Out of scope for this project.** This branch is t-string training data only.
A non-t-string corpus would be a separate data project consuming the same
provider protocol; it does not become an SP5 rung or broaden this package.

## Backlog

Open questions, not queued. Each needs evidence or a trigger before it earns a
rung.

| ID | Item | Trigger |
|----|------|---------|
| B-HEADER | Prompt-format overfitting: every placeholder example and eval prompt began `# Python 3.14 t-strings:`, a trigger phrase no real user types. Vary comment/docstring/chat framings. **Returns at corpus scale**: SP5's prompts come from a few dozen renderer phrasings, so the model can learn format→answer mappings and transfer nothing. Tracked as SP5's prompt-text diversity metric (spec §5.1), which gates pattern approval. | SP6 benchmark authoring; SP5 R5 renderers |

Training format, replay, LoRA rank, tokenizer analysis, and loss masking are
provider backlog, not SP5 backlog.

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
