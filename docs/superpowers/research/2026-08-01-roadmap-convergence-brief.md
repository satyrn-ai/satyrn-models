# Project-boundary brief: provider and t-string training data

## Decision

The two efforts are a provider and a consumer, not co-owners of a shared
implementation.

- `worktree-tstrings-rebuild` owns verification, dataset ingest, common gates,
  the independent benchmark, training, and evaluation.
- `worktree-sp5-corpus-brainstorm` owns t-string training data: sources, seeds,
  properties, patterns, generated rows, reports, and dataset snapshots.

The SP5 effort uses the provider. It does not build a verification core and it
does not train or score models.

## Boundary

| Concern | Provider effort | T-string-data effort |
|---|---|---|
| Dataset/task wire contract | Owns | Consumes |
| Reference execution and candidate oracle | Owns | Calls |
| Rejection stages and adversarial runner | Owns | Supplies t-string cases/policy |
| Feature policy mechanism | Owns protocol/execution | Implements t-string policy |
| Benchmark and baselines | Owns | Records fingerprint for contamination |
| Training and evaluation | Owns | Publishes datasets only |
| CPython/PEP source pinning and extraction | Consumes rows | Owns |
| Third-party literal de-libraryization | — | Owns |
| Seeds, properties, patterns, composition | — | Owns |
| Data diversity and build reports | Consumes manifest | Owns |
| 500/2k/5k scale experiment | Trains and scores | Publishes matched snapshots |

## Artifacts crossing the boundary

The provider publishes:

- versioned `TaskRecord`, `CheckSpec`, `Provenance`, and `DatasetSnapshot`
  schemas;
- the reset/package baseline on which the consumer installs its `authoring`
  package; SP5 consumes this before it starts collection implementation;
- reference-execution and verification APIs;
- `FeaturePolicy` protocol and typed stages;
- halting contamination API plus benchmark fingerprint;
- dataset and execution contract fixtures.

The t-string-data project publishes:

- immutable dataset snapshots;
- source/seed/pattern/decision fingerprints;
- a versioned data-owner composition profile and a self-contained
  row→seed→occurrence source/license lineage bundle with required NOTICE
  material;
- t-string policy implementation and adversarial cases;
- composition and effective-diversity metrics;
- drop and build reports;
- composition-matched 500, 2k, and 5k manifests.

Expected values are not trusted boundary inputs. A row contains a reference
program and declarative checks; the provider executes the reference and derives
the observations used to verify candidates.

Integration is through the installed provider package and its canonical JSON
fixture, never by importing from the other worktree's filesystem. Dataset
snapshots carry `PolicyRef(id, version, config)`, not executable policy code;
the provider resolves the data project's `TStringPolicy` through a trusted
registry. `config` is the producer's versioned declarative `PolicyIntent`, not
an import path: it gives the isolated policy the requirements needed to make
degenerate candidates. Any benchmark contamination conflict halts publication
and training.

## Roadmap consequences

1. SP0 R1 reset/quarantine is provider-owned and lands first. SP5 merges or
   rebases onto that package baseline before collection implementation; this is
   a shared-repository prerequisite, not a provider API dependency.
2. The provider contract and verifier branch lands next; SP5 merges or rebases
   onto it before claiming contract compatibility. The provider must not be
   imported through a cross-worktree path.
3. The provider contract and verifier land before SP5 can publish verified
   rows. SP5 may validate sources and prepare seeds after the reset baseline is
   consumed, without calling provider APIs.
4. CPython/PEP harvest moves into the t-string-data project because it creates
   domain data, not infrastructure.
5. SP5's former oracle/cache/process-pool work becomes provider integration;
   no second runner is implemented.
6. SP6 benchmark redesign, baseline ladders, training format, loss masking,
   LoRA runs, memorization checks, and model verdicts remain provider work.
7. SP5's final scale rung publishes matched datasets. The provider performs
   the 500 → 2k → 5k training/evaluation experiment.

## Data-project completion

SP5 is complete when it can reproduce and publish verified, stdlib-only,
provenance-complete t-string datasets at 500, 2k, and 5k rows, with composition
held constant against a versioned data-owner profile, effective diversity
reported, and snapshot-contained lineage. It does not need—and must not claim—a
model-performance verdict.
