# Roadmap convergence brief: SP0–SP2 rebuild and SP5 authoring

## Purpose

Update the project roadmap so the SP0–SP2 rebuild and SP5 corpus-authoring
work form one programme rather than two competing pipelines. This is a brief
for the roadmap revision, not a replacement implementation specification.

## Decisions to preserve

1. **SP0 R1 lands first and substantially unchanged.** Retire the placeholder
   scripts and quarantine the 24 legacy examples. Quarantine is not a corpus
   type and must never feed a benchmark or training run.
2. **One shared foundation, two corpus inputs.** `harvest` and `authoring`
   must share the final corpus-row format, verifier, provenance contract, and
   contamination controls. Neither track reimplements an oracle or gate chain.
3. **SP2 is a small, high-trust source.** CPython/PEP harvest supplies
   provenance-rich examples, fixtures, and regression cases; it cannot supply
   the corpus scale required for the decision.
4. **SP5 is the primary scale path.** Its seed-and-pattern system produces the
   generated corpus, with its existing reproducibility, planted-defect, and
   effective-diversity requirements retained.
5. **SP6 owns the measurement instrument.** Benchmark redesign is independent
   of both corpus sources. It must produce a 30–40 task benchmark, including
   a naturalistic slice authored before patterns, plus strengthened retrieval
   baselines.
6. **Stdlib-only applies to emitted rows.** Third-party literals may be seed
   material only after de-libraryization; no generated or harvested row may
   import a third-party library.

## Required roadmap changes

### Introduce a shared-foundation milestone after SP0 R1

It owns the single package-level contracts needed by both routes:

- final, format-neutral corpus row and provenance model;
- subprocess verifier with timeout, feature-use and old-form checks;
- hidden expectations derived by executing the reference solution under the
  verifying interpreter;
- structured stage/rejection reporting, with adversarial fixtures for every
  rejecting stage;
- benchmark/corpus contamination and intra-corpus deduplication.

The SP0–SP2 rebuild design's threat-model obligations remain requirements, but
its current implementation plan must be revised before use. In particular,
the shared foundation must not inherit a bypassable expected-value factory,
the generic AST-mutant anti-vacuity design, or a separate authoring oracle.

### Reorder the programme

| Order | Work | Gate before the next stage |
|---|---|---|
| 1 | SP0 R1 — reset and quarantine | Legacy material is inert and the package/test scaffold works. |
| 2 | Shared foundation | Cross-source task rows verify through one oracle; adversarial fixtures pass. |
| 3 | SP6 benchmark redesign + SP1 baseline ladder | Independent benchmark, halting contamination gate, and base/real-docs measurements exist. |
| 4 | SP2 harvest and SP5 seed preparation | Harvest rows self-verify; seed extraction, evaluation, and coverage work, but no training corpus is emitted. |
| 5 | SP5 patterns, build gates, and 500-row pilot | Reproducible pilot; thresholds and composition targets are derived and committed. |
| 6 | Training-format decision and composition-held 500 → 2k → 5k sweep | Same benchmark, full-corpus memorization check, and effective-diversity report at every point. |
| 7 | Decision | Record fine-tune-vs-docs result, or the evidenced negative result (correlation or task-distribution bias). |

Seed inventory and authoring may prepare during the measurement work, but no
training corpus may be emitted or consumed before the SP6 baseline numbers
exist. No training run may consume the pilot until its thresholds are derived.

## Explicit ownership

| Concern | Owner |
|---|---|
| Reset and quarantine | SP0 R1 |
| Corpus row, verifier, provenance, and common gates | Shared foundation |
| Independent benchmark and baseline ladder | SP6 / SP1 |
| Small trusted source corpus | SP2 harvest |
| Seed extraction, patterns, reproducible large corpus, and sweep | SP5 |
| Training rendering and loss-masking decision | Training milestone before the sweep |

## Completion framing

The programme succeeds when it produces a trustworthy decision, not when it
necessarily proves fine-tuning superior. A retrieval win, a correlated-corpus
finding, or evidence of benchmark/task-distribution bias are valid outcomes if
they were measured through the shared verifier and independent benchmark.
