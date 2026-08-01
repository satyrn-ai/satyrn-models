# T-String Training-Data Implementation Plan

**Status:** Planned and executable after the provider contracts land.

Each task is test-first: add the stated failing fixture/invariant, implement the
smallest data-side behavior, run the focused suite, then run the full authoring
suite. Tasks 1–2 may proceed in parallel with provider work; later blocking
dependencies are explicit below.

## Goal

Produce reproducible, provenance-complete, stdlib-only t-string training
datasets at useful scale. This project owns the data and nothing downstream of
it: it does not implement the verifier, benchmark, trainer, model client, or
evaluation ladder.

The provider effort on `worktree-tstrings-rebuild` supplies versioned dataset,
verification, policy, and contamination contracts. This project consumes those
contracts and publishes immutable dataset snapshots for the provider to train.

## Deliverables

- source manifests and pinned source caches;
- extracted and hand-authored t-string seeds;
- source-derived CPython/PEP exercise intents and rows;
- reviewed `Property` and pattern definitions;
- deterministic generated rows conforming to the provider contract;
- build/drop/diversity/composition reports;
- composition-matched 500, 2k, and 5k dataset snapshots plus manifests.

Not deliverables: benchmark tasks, baseline measurements, adapters, LoRA
training, memorization scores, or a fine-tune-vs-retrieval verdict.

## External contract required

Before Task 3, provider Tasks 0–2 must land and this branch must merge or rebase
onto the installed package and fixtures. No cross-worktree path imports. The
provider publishes:

- `TaskRecord`, `CheckSpec`, `Provenance`, and `DatasetSnapshot`;
- `FeaturePolicy`, trusted policy registration, and domain-case entry points;
- reference execution and candidate verification;
- typed rejection stages;
- dataset/execution contract versions.

Before Task 6, the provider seals the independent benchmark's naturalistic
slice and publishes its fingerprint, so pattern authors cannot shape that slice.
Before Task 9, the provider publishes the calibrated contamination API/policy
from its 500-row-pilot gate.

Before Task 5's live qualification cases, provider Task 3 must also land.

This project may build sources and seeds before the provider is ready. It may
not declare an emitted row qualified until provider contract fixtures pass
locally, and it may not publish a final dataset snapshot until the calibrated
contamination policy passes.

The adapter calls the provider's canonical API without redefining its types:

```python
materialize_reference(task: TaskRecord, *, cache: CacheMode) -> ReferenceOutcome
qualify_task(task: TaskRecord, *, cache: CacheMode) -> QualificationOutcome
check_contamination(snapshot: DatasetSnapshot, benchmark: BenchmarkRef) -> ContaminationReport
```

`ReferenceOutcome` may expose observations for facts-first authoring, but those
facts never become trusted fields in a snapshot. On ingest the provider derives
or retrieves its own evidence from the task/environment key.

## Task 1: Source manifest, pinning, and suitability

Create `sources.toml` with source URL, immutable ref, license, extraction mode,
and expected contribution type. Source classes include:

- official CPython at the interpreter-matching tag;
- PEP 750 and What's New examples;
- third-party repositories used only for de-libraryized t-string literals;
- quarantined legacy examples used only as candidate seeds.

Validate suitability before extraction. Each code source must contain actual
`TemplateStr` nodes; text search may be a cheap preflight but AST confirmation
is authoritative. Pin checks verify the exact commit and canonical remote. A
source that contributes no novel skeleton is reported and may be removed from
future refreshes.

Acceptance:

- fork, tag/interpreter mismatch, mutable ref, missing license, and zero-target
  sources fail with distinct reasons;
- source manifests round-trip deterministically;
- no source module is imported during extraction.

Target files: `src/satyrn_model/authoring/sources.py`,
`src/satyrn_model/authoring/extract.py`, `sources.toml`, and
`tests/authoring/test_sources.py`.

## Task 2: Source exercises, seed extraction, and authored seeds

Walk source ASTs for t-string literals and capture seeds:

- literal source and free names;
- proposed stdlib-only binding expressions;
- origin repository, ref, path, and exact span;
- content-derived seed ID;
- extracted/authored kind.

CPython test methods and PEP examples are source material here, not provider
implementation tasks. Do not transplant private CPython test helpers into rows.
Third-party literals are stripped from their library context and rebuilt with
stdlib-only bindings.

Also emit `SourceExercise` intents from self-contained CPython/PEP examples:
origin, extracted intent, complete stdlib-only reference program, and
`Property`. Do not implement cross-module dependency resolution or inlining.
Same-file closure, shadowing, and exact-span selection remain gated extraction
risks with adversarial fixtures; provider self-verification is not claimed to
prove extraction intent.

Acceptance:

- class methods, nested scopes, shadowed names, and multiline literals have
  adversarial fixtures;
- extracted source spans reproduce the literal exactly;
- duplicate content IDs collapse only after provenance is retained;
- authored seeds use the same schema and checks as extracted seeds.
- a source-derived exercise has no fictional `pattern_id` or seed origin;
- a cross-module helper dependency is rejected rather than inlined.

This task owns CPython/PEP extraction. It does not copy CPython private helpers
or create provider modules.

## Task 3: Facts and seed review through the provider

Call the provider reference-execution API for each seed expression and binding
set. Run twice to detect nondeterminism. Store `Facts` keyed by expression and
bindings, not merely by seed ID, because composed template facts are not
derivable from their parts.

Review is facts-first. Persist decisions by content hash so a changed seed or
binding invalidates approval. Reject non-evaluable observations unless an
approved comparison representation is explicit.

Acceptance:

- nondeterministic, timeout, execution-error, and non-round-trippable cases are
  reported distinctly;
- review decisions invalidate on content change;
- no local subprocess evaluator duplicates provider behavior.

Blocking dependency: provider reference execution and observation
serialization. Target files: `authoring/facts.py`, `authoring/provider.py`, and
`tests/authoring/test_facts.py`.

## Task 4: Exercise intent and rendering

Implement the t-string-specific model:

- `Seed`;
- `Property` variants (`Introspect`, `Render`, `Transform`,
  `NegativeControl`);
- `ExerciseIntent = SourceExercise | GeneratedExercise`;
- `GeneratedExercise` with pattern/seed provenance and property arity enforced
  at construction;
- `SourceExercise` with exact source provenance and no pattern fields;
- prompt, reference-program, `CompletionSpec`, `CheckSpec`, and policy
  projections.

Expected values are absent from both exercise variants. The provider derives them by
executing the rendered reference program and evaluating its declarative checks.
Prompt and check are projections of one property intent.

Acceptance:

- generated arity mismatch is unrepresentable through the public constructor;
- source and generated provenance variants round-trip without empty fictional
  fields;
- golden tests cover every property/renderer pair;
- a cross-projection adversarial case catches `.values` versus `.strings`
  drift;
- rendered records validate against the provider's contract fixture.

Blocking dependency: provider `TaskRecord`, `CompletionSpec`, `CheckSpec`,
`PolicyRef`, and provenance unions. Generic candidate assembly and check grammar
are not reimplemented here.

## Task 5: T-string policy and data-quality rules

Implement only domain-specific policy/configuration:

- correct `TemplateStr` detection, including nested format specs;
- f-string/`.format()`/string-`%` fallback rules;
- property-specific feature requirements, including convert-only tasks;
- property-to-`CheckSpec` compatibility and t-string-specific banned
  observations;
- intent-derived degenerate candidates for anti-vacuity;
- composition labels derived from property variants.

The provider executes policies and returns typed stages. This project does not
implement a second runner or oracle cache.

Acceptance uses live provider calls for the eight planted defects in the SP5
spec. Each case asserts the expected provider stage, not merely rejection.

The data package contributes `TStringPolicy` and case data through the
provider's trusted registration/entry-point mechanism. A dataset snapshot
contains only `PolicyRef`; it never embeds executable policy code.
Keep that plugin in `src/satyrn_model/tstrings_policy/`, depending only on
provider contracts. It must not import `satyrn_model.authoring`, sources, seeds,
or patterns; the provider may load the plugin without loading data-production
code.

## Task 6: Patterns, approval, and generation

Author deterministic pattern functions that map approved seeds to exercises.
Pattern approval is keyed to the pattern source hash. Editing a pattern
invalidates its approval, audit, generated cache, and affected row decisions.

Generation is a pure function of committed seeds, patterns, decisions,
generator version, and sampling configuration. The transient generated file
self-invalidates when its input fingerprint changes.

Blocking dependency: the provider has frozen and fingerprinted the complete
benchmark, including its naturalistic slice. SP5 receives the fingerprint and
contamination service, not benchmark authoring ownership.

Acceptance:

- `audit-pattern` shows representative rows and blast radius;
- stale approvals halt generation;
- identical inputs produce byte-identical exercises;
- no model call exists in the package.

## Task 7: Dataset build and reports

Render source-derived and generated exercises to provider `TaskRecord`s,
validate them through the provider,
apply data-project gates, and write atomically:

- `corpus/tstrings.jsonl`;
- `reports/build.md`;
- `reports/dropped.jsonl` with full row content;
- dataset manifest and content fingerprint.

Data-project gates cover property/check compatibility, cross-projection consistency,
composition, deterministic generation, and intra-corpus fingerprints. Provider
gates cover contract validity, reference/candidate verification, and benchmark
contamination. A benchmark fingerprint supplied by the provider is recorded;
this project does not author or score the benchmark.

Acceptance:

- clean `--no-cache` builds are byte-identical;
- interrupted writes leave the last committed artifact intact;
- every dropped row has source/pattern attribution and typed reason;
- provider rejection blast radius is grouped by pattern.

Any provider contamination conflict halts publication. There is no tolerated
drop-rate for benchmark conflicts and no local reinterpretation of provider
verdicts.

## Task 8: Pilot and thresholds

Build approximately 500 qualified candidate rows. Derive and commit
data-quality thresholds for:

- distinct structural fingerprints;
- prompt-template diversity;
- composition tolerance;
- intra-corpus duplicate rate;
- human review-budget fraction.

Threshold derivations use planted known-similar and known-diverse pairs plus
human inspection. SP5 supplies the 500-row calibration material for the
provider's prompt/code contamination threshold derivation, but does not set
that threshold. The provider reruns the pilot under the versioned calibrated
policy before Task 9. No model training is performed here.

## Task 9: Publish composition-matched dataset slices

Publish immutable 500, 2k, and 5k snapshots selected by a committed sampling
rule and seed. Hold composition constant and record effective diversity for
each snapshot.

Each manifest contains:

- dataset and provider-contract versions;
- row and structural-fingerprint counts;
- composition and diversity metrics;
- source, seed, pattern, and decision fingerprints;
- benchmark fingerprint used for contamination;
- verifying interpreter and provider version.

The provider project consumes these snapshots for training and evaluation. Its
score curve and model verdict are not SP5 artifacts.

## Final verification

- Every final row imports only the standard library.
- All provider contract fixtures pass from this worktree.
- All eight planted defects fail at their expected provider/data-policy stage.
- `authoring build --no-cache` is byte-reproducible.
- 500, 2k, and 5k snapshots are composition-matched and fingerprinted.
- No module implements model inference, benchmark scoring, LoRA training, or a
  subprocess oracle.
