# T-string training-data implementation plan

**Status:** Planned. Tasks 1–5 are provider-independent collection work. Tasks
6–12 consume the provider contracts; no task implements an oracle, benchmark,
trainer, model client, or evaluation.

## Goal and boundary

Produce reproducible, provenance-complete, stdlib-only t-string training-data
snapshots. The provider project supplies its versioned `TaskRecord`,
`CheckSpec`, provenance, execution, qualification, and contamination contracts.
SP5 supplies only t-string source material, intent, patterns, rendering,
data-specific policy, reports, and snapshots.

Provider calls have these fixed signatures:

```python
materialize_reference(task: TaskRecord, *, cache: CacheMode) -> ReferenceOutcome
qualify_task(task: TaskRecord, *, cache: CacheMode) -> QualificationOutcome
check_contamination(snapshot: DatasetSnapshot, benchmark: BenchmarkRef) -> ContaminationReport
```

No raw `(expression, bindings)` is passed to `materialize_reference`: SP5 first
renders a minimal `TaskRecord` from a canonical local intent. Collection may
proceed without the provider, but artifacts are candidates—not qualified rows
or publishable snapshots—until tasks 6–12 pass.

## Shared delivery rules

Every task is TDD: add its named failing fixture first, implement the smallest
behavior, run its focused test command, then `uv run pytest tests/authoring -q`.
New commands are installed as `authoring ...`; artifacts use atomic writes.
Target paths and test names below are contracts for implementation, not merely
illustrative names.

The exact CPython tag and resolved verifying interpreter must agree (for
example `v3.14.5` / `3.14.5`); a `3.14` minor pin is not sufficient. Snapshot
manifests always record the resolved interpreter build.

## Phase A — independently useful collection

### Task 1: Source manifest, exact pins, and license policy

Create `sources.toml`, `src/satyrn_model/authoring/sources.py`, and
`tests/authoring/test_sources.py`.

- Define immutable URL/SHA, source class, allowed license, attribution fields,
  extraction mode, and expected contribution schema.
- Implement canonical-remote/SHA validation and an exact CPython-tag ↔ verifier
  check. Emit `reports/source-inventory.json` and required NOTICE material.
- Report novel structural skeletons as a selection metric only; never reject a
  source merely for sharing a skeleton.

Start with failing tests `test_rejects_mutable_ref`, `test_rejects_disallowed_license`,
`test_records_all_source_attribution`, and `test_rejects_tag_interpreter_mismatch`.
Run `uv run pytest tests/authoring/test_sources.py -q`.

### Task 2: Local model for occurrences, seeds, and task intent

Create `authoring/models.py`, `authoring/seeds.py`, and
`tests/authoring/test_models.py`.

- Define `SeedOccurrence` (origin/ref/path/span/license plus content `seed_id`),
  normalized `Seed` (literal/bindings and `occurrence_ids`), `TaskIntent`,
  `SourceEvidence`, `SourceExerciseCandidate`, and `Property` variants:
  `Introspect`, `Render`, `Transform`, `Construct`, and `NegativeControl`.
- Make generated-exercise arity and `requires_template=False` on negative
  controls constructible and validated by the public constructors.
- JSONL round-trips preserve tuples and all origins; identical seed content
  retains multiple occurrence records rather than one arbitrary origin.

Start with `test_same_seed_two_origins_is_not_lost`,
`test_construct_property_is_representable`, and `test_negative_control_is_not_template_required`.
Run `uv run pytest tests/authoring/test_models.py -q`.

### Task 3: Safe AST extraction into candidates

Create `authoring/extract.py`, fixtures under `tests/authoring/fixtures/`, and
`tests/authoring/test_extract.py`.

- Extract exact literal spans and source evidence without importing source
  modules. The harvest unit is an assertion block/case, not an entire test
  method.
- Translate only directly representable cases to `SourceExerciseCandidate`.
  Split multi-case methods only at clear assertion boundaries; reject loops,
  subtests, private-helper calls, unresolved/shadowed names, and no-evidence
  cases unless the fixture demonstrates a safe direct transformation.
- Apply a pre-provider AST safety grammar: safe literals/containers and a small
  approved stdlib value palette only; reject calls, comprehensions, lambdas,
  walrus, dynamic imports, file/network/process access, and non-approved
  attribute access.

Start with fixtures/tests for multiline literals, nested scopes and shadowing,
multi-case methods, loops/subtests, helper calls, no docstring, `__import__`,
file read, subprocess call, and a deterministic side effect. Run
`uv run pytest tests/authoring/test_extract.py -q`.

### Task 4: Coverage, authoring, and collection checkpoint

Create `authoring/coverage.py`, `authoring/review.py`,
`tests/authoring/test_coverage.py`, and the commands `authoring coverage` /
`authoring review seeds`.

- Build `reports/coverage.md` from extracted and authored candidates alone:
  grammar shape × property/task type, source kind, domain, license inventory,
  and structural-bucket distribution.
- Support Cover→Author→Cover using committed `seeds/authored.jsonl`; record
  decisions by content hash and preserve occurrence provenance.
- Write an explicit `reports/collection-checkpoint.md`: counts, uncovered
  cells, safety drops, and the statement that no row is provider-qualified.

Start with `test_coverage_runs_without_provider`,
`test_authored_seed_closes_reported_gap`, and
`test_same_skeleton_distinct_semantics_are_retained`. Run
`uv run pytest tests/authoring/test_coverage.py -q`.

### Task 5: Collection import and exact-dedup gates

Create `authoring/static_gates.py` and `tests/authoring/test_static_gates.py`.

- Add a versioned stdlib import allowlist, reject dynamic imports, and reject
  de-libraryized retained third-party API names.
- Reject exact content duplicates at build time. Treat structural fingerprints
  only as diversity metrics/optional sampling caps; report semantic-near pairs
  without calling them duplicates.

Start with `test_dynamic_import_rejected`, `test_third_party_surface_rejected`,
`test_exact_repeat_rejected`, and `test_shared_skeleton_is_not_duplicate`.
Run `uv run pytest tests/authoring/test_static_gates.py -q`.

## Phase B — provider-qualified corpus production

### Task 6: Provider adapter and render-to-task boundary

Requires provider Tasks 0–2 and installed fixtures. Create `authoring/render.py`,
`authoring/provider.py`, and `tests/authoring/test_provider_adapter.py`.

- Render exactly one minimal provider `TaskRecord` from each canonical
  `TaskIntent`; prompt, reference program, and declarative checks are all
  projections of that intent. No expected value is serialized by SP5.
- Validate imported provider types/version fixtures; pass `TaskRecord` plus
  `cache=` to `materialize_reference` and `qualify_task` exactly as published.
- Use source candidates only after this rendering step; never add a competing
  raw-expression inspect API unless the provider explicitly publishes one.

Start with `test_renderer_returns_provider_task_record`,
`test_prompt_and_check_share_intent`, and `test_raw_expression_cannot_reach_provider`.
Run `uv run pytest tests/authoring/test_provider_adapter.py -q`.

### Task 7: Facts, review, policy, and qualification

Create `authoring/facts.py`, `tstrings_policy/`, and
`tests/authoring/test_facts.py` / `test_policy.py`.

- Materialize rendered tasks twice through the provider and reject differing
  observations or unsupported provider serialization. Persist decisions keyed
  by intent content and provider contract/environment fingerprint.
- Supply the dependency-isolated t-string policy/plugin and property-to-
  `CheckSpec` mapping. It imports provider contracts but no authoring modules.
- Add live adversarial tests for f-string fallback, candidate-derived expected
  values, vacuity, `AnnAssign` vacuity, construct/convert requirements, and
  `requires_template=False`. Include `t"{v:{w}}"` as valid and a genuine nested
  f-string inside its format-spec expression as invalid.

Run `uv run pytest tests/authoring/test_facts.py tests/authoring/test_policy.py -q`.

### Task 8: Patterns, transitive approval, and generated cache

Requires the provider's frozen benchmark fingerprint before pattern authoring.
Create `authoring/patterns/`, `authoring/generate.py`, and
`tests/authoring/test_patterns.py`.

- Patterns declare every helper/template/renderer dependency. Build a
  `pattern_input_fingerprint` over those inputs, generator version, policy and
  configuration versions, and render-contract version.
- `authoring audit-pattern ID` records that fingerprint and blast radius;
  generation refuses stale/missing approval and self-invalidates its transient
  cache if any input changes.
- Add cross-projection and composition-classifier gates. The classifier derives
  labels from `Property`, including `Construct` and negative controls.

Start with `test_helper_change_invalidates_approval`,
`test_prompt_values_check_strings_fails`, and
`test_property_feature_mismatch_fails_pattern`. Run
`uv run pytest tests/authoring/test_patterns.py -q`.

### Task 9: Build, reports, and provider contamination

Create `authoring/build.py`, `authoring/diversity.py`,
`tests/authoring/test_build.py`, and `authoring build`.

- Render qualified source and generated intents; apply local gates, provider
  qualification, exact dedup, and `check_contamination(snapshot, benchmark)`.
  A contamination conflict halts publication.
- Atomically write corpus, full-content `reports/dropped.jsonl`, `build.md`,
  source/license inventory, and a manifest containing provider/execution,
  interpreter, policy, decision, and pattern-input fingerprints.
- Structural fingerprints and optional external embedding report are diversity
  metrics only. If emitted, embeddings record model/revision/settings and have
  no acceptance effect.

Start with `test_contamination_halts_publication`, `test_drop_has_full_content`,
`test_no_cache_is_byte_reproducible`, and `test_interrupted_write_is_atomic`.
Run `uv run pytest tests/authoring/test_build.py -q`.

### Task 10: Pilot and calibrated thresholds

Create `sampling.toml`, `reports/threshold-derivation.md`, and
`tests/authoring/test_sampling.py`.

- Build a qualified ~500-row pilot and commit derivations for diversity,
  composition tolerance, review budget, and any semantic-near gate. Supply
  calibration rows to the provider; SP5 never selects contamination thresholds.
- Commit a nested, stratified selection plan for source kind, property,
  pattern, and seed. Decide explicitly whether the pilot itself is the 500
  snapshot; otherwise rerun calibration on the final selected 500.

Start with `test_sampling_is_nested_and_stratified` and
`test_final_500_requires_calibration_record`. Run
`uv run pytest tests/authoring/test_sampling.py -q`.

### Task 11: Publish 500 ⊂ 2k ⊂ 5k snapshots

Create `authoring/publish.py` and `tests/authoring/test_publish.py`.

- Produce immutable, composition-matched nested snapshots and manifests with
  fixed row IDs, strata, fingerprints, exact-duplicate result, source/license
  inventory, provider benchmark fingerprint, and effective-diversity reports.
- Recheck provider qualification and contamination under the calibrated policy
  before publishing each snapshot.

Start with `test_snapshot_ids_are_nested`, `test_manifest_has_all_strata`, and
`test_publish_requires_calibrated_provider_result`. Run
`uv run pytest tests/authoring/test_publish.py -q`.

### Task 12: End-to-end and adversarial release gate

Create `tests/adversarial/` and `tests/authoring/test_e2e.py`.

- Maintain a 3-seed × 2-pattern golden mini-corpus through collection,
  rendering, provider qualification, and build.
- Run all ten planted defects live at their required local/provider stage,
  including safety violations and format-spec precision.
- Verify provider cold/warm equivalence, no-cache reproducibility, and that no
  SP5 module contains a subprocess oracle, benchmark scorer, or model call.

Run `uv run pytest tests/authoring tests/adversarial -q`.

## Final acceptance

- Provider-independent collection checkpoint exists before provider integration.
- Every final row is stdlib-only, source/license-attributed, safe to offer to
  the provider, and provider-qualified.
- Exact duplicates are absent; structural/embedding measures remain metrics,
  not false duplicate proofs.
- All ten planted defects fail live at the named stage.
- `authoring build --no-cache` is byte-reproducible and published 500 ⊂ 2k ⊂
  5k snapshots are stratified, composition-matched, and fingerprinted.
