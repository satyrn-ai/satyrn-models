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

### Execution prerequisite: consume the provider reset

Before Task 1, the provider's Task 0 reset must have landed on `main` and this
branch must merge or rebase onto that package/test baseline. Tasks 1–5 are
provider-independent in their *behavior*: they neither import provider
contracts nor make provider calls. They are not independent of the shared
repository scaffold that supplies the `src/` layout, `uv` environment, test
configuration, and `authoring` command installation point. Do not recreate
that scaffold in SP5 or import it from another worktree. Prove the prerequisite
with a clean `uv sync` and the provider's package-import smoke test before
starting Task 1.

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

Extend the committed policy-only `sources.toml` with versioned `[[source]]`
records; create `src/satyrn_model/authoring/sources.py` and
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

Create `src/satyrn_model/authoring/models.py`,
`src/satyrn_model/authoring/seeds.py`, and
`tests/authoring/test_models.py`.

- Define `SeedOccurrence` (origin/ref/path/span/license plus content `seed_id`),
  normalized `Seed` (literal/bindings and `occurrence_ids`), `TaskIntent`,
  `SourceEvidence`, `SourceExerciseCandidate`, and `Property` variants:
  `Introspect`, `Render`, `Transform`, `Construct`, and `NegativeControl`.
- A `TaskIntent` has a non-empty ordered tuple of properties and a canonical,
  versioned `PolicyIntent` projection. The renderer serializes only that
  projection in `PolicyRef.config`, giving the dependency-isolated
  `TStringPolicy` enough declarative input to derive degenerates without
  importing authoring code.
- Make generated-exercise arity for every property in that tuple and
  `requires_template=False` on negative controls constructible and validated
  by the public constructors. A source candidate preserves its aligned
  `LocalCheckIntent` tuple; it must never silently keep only one assertion.
- JSONL round-trips preserve tuples and all origins; identical seed content
  retains multiple occurrence records rather than one arbitrary origin.

Start with `test_same_seed_two_origins_is_not_lost`,
`test_construct_property_is_representable`, and `test_negative_control_is_not_template_required`.
Run `uv run pytest tests/authoring/test_models.py -q`.

### Task 3: Safe AST extraction into candidates

Create `src/satyrn_model/authoring/extract.py`, fixtures under
`tests/authoring/fixtures/`, and
`tests/authoring/test_extract.py`.

- Extract exact literal spans and source evidence without importing source
  modules. The harvest unit is an assertion block/case, not an entire test
  method.
- Translate only directly representable cases to `SourceExerciseCandidate`.
  Split multi-case methods only at clear assertion boundaries; reject loops,
  subtests, private-helper calls, unresolved/shadowed names, and no-evidence
  cases unless the fixture demonstrates a safe direct transformation.
- Preserve every representable observation in a case as aligned properties and
  local check intents. Before accepting it, reconcile the source's descriptive
  evidence (test name, comment, or docstring), asserted subject/path, and
  translated property. Reject a contradiction or an assertion block that needs
  an unsupported relationship; provider self-verification cannot prove that
  extraction asked the question the source described.
- Apply a pre-provider AST safety grammar: safe literals/containers and a small
  approved stdlib value palette only; reject calls, comprehensions, lambdas,
  walrus, dynamic imports, file/network/process access, and non-approved
  attribute access.

Start with fixtures/tests for multiline literals, nested scopes and shadowing,
multi-case methods, loops/subtests, helper calls, no docstring, `__import__`,
file read, subprocess call, a deterministic side effect, a multi-observation
case, and evidence/assertion disagreement (for example, `.values` prose with
`.strings` assertions). Run
`uv run pytest tests/authoring/test_extract.py -q`.

### Task 4: Coverage, authoring, and collection checkpoint

Create `src/satyrn_model/authoring/coverage.py`,
`src/satyrn_model/authoring/review.py`,
`tests/authoring/test_coverage.py`, and the commands `authoring coverage` /
`authoring review seeds`.

- Build `reports/coverage.md` from extracted and authored candidates alone:
  grammar shape × property/task type, source kind, domain, license inventory,
  and structural-bucket distribution.
- Support Cover→Author→Cover using committed `seeds/authored.jsonl`; record
  decisions by content hash and preserve occurrence provenance.
- Write an explicit `reports/collection-checkpoint.md`: counts, uncovered
  cells, safety drops, and the statement that no row is provider-qualified.
- Commit a data-owner-reviewed `composition.toml` before pattern authoring. It
  declares the target proportions and mandatory strata for property,
  source-kind, domain, and negative controls, with no implicit uniform default.
  It is a target profile, not a provider benchmark requirement; Task 10 derives
  its tolerance band and records any versioned revision from the pilot.

Start with `test_coverage_runs_without_provider`,
`test_authored_seed_closes_reported_gap`, and
`test_same_skeleton_distinct_semantics_are_retained`. Run
`uv run pytest tests/authoring/test_coverage.py -q`.

### Task 5: Collection import and exact-dedup gates

Create `src/satyrn_model/authoring/static_gates.py` and
`tests/authoring/test_static_gates.py`.

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

Requires provider Tasks 0–2, an installable versioned provider release and
canonical fixtures, and its fail-closed OS sandbox profile for untrusted
reference/candidate code. Create `src/satyrn_model/authoring/render.py`,
`src/satyrn_model/authoring/provider.py`, and
`tests/authoring/test_provider_adapter.py`.

- Render exactly one minimal provider `TaskRecord` from each canonical
  `TaskIntent`; prompt, reference program, declarative checks, and the
  `PolicyRef.config` `PolicyIntent` are all projections of that intent. No
  expected value is serialized by SP5.
- Validate imported provider types/version fixtures; pass `TaskRecord` plus
  `cache=` to `materialize_reference` and `qualify_task` exactly as published.
- Require sandbox profile/version in provider execution evidence; refuse to
  qualify third-party-derived material if the required profile is unavailable.
- Use source candidates only after this rendering step; never add a competing
  raw-expression inspect API unless the provider explicitly publishes one.

Start with `test_renderer_returns_provider_task_record`,
`test_prompt_checks_and_policy_config_share_intent`,
`test_raw_expression_cannot_reach_provider`,
and `test_missing_sandbox_profile_blocks_qualification`.
Run `uv run pytest tests/authoring/test_provider_adapter.py -q`.

### Task 7: Facts, review, policy, and qualification

Create `src/satyrn_model/authoring/facts.py`,
`src/satyrn_model/tstrings_policy/`, and
`tests/authoring/test_facts.py` / `test_policy.py`.

- Materialize rendered tasks twice through the provider and reject differing
  observations or unsupported provider serialization. Persist decisions keyed
  by intent content and provider contract/environment fingerprint.
- Supply the dependency-isolated t-string policy/plugin and property-to-
  `CheckSpec` mapping. It imports provider contracts but no authoring modules;
  it derives every degenerate from the rendered task plus validated
  `PolicyIntent`, not from candidate AST shape or an authoring import.
- Add live adversarial tests for f-string fallback, candidate-derived expected
  values, vacuity, `AnnAssign` vacuity, construct/convert requirements, and
  `requires_template=False`. Include `t"{v:{w}}"` as valid and a genuine nested
  f-string inside its format-spec expression as invalid.

Run `uv run pytest tests/authoring/test_facts.py tests/authoring/test_policy.py -q`.

### Task 8: Patterns, transitive approval, and generated cache

Requires the provider's frozen benchmark fingerprint before pattern authoring.
Create `src/satyrn_model/authoring/patterns/`,
`src/satyrn_model/authoring/generate.py`, and
`tests/authoring/test_patterns.py`.

- Patterns declare every helper/template/renderer dependency. Build a
  `pattern_input_fingerprint` over those inputs, generator version, policy and
  configuration versions, and render-contract version.
- `authoring audit-pattern ID` records that fingerprint and blast radius;
  generation refuses stale/missing approval and self-invalidates its transient
  cache if any input changes.
- Add cross-projection and composition-classifier gates. The classifier derives
  labels from every `Property`, including `Construct` and negative controls,
  and generation/audit reports each pattern's contribution against the committed
  composition profile.

Start with `test_helper_change_invalidates_approval`,
`test_prompt_values_check_strings_fails`, and
`test_property_feature_mismatch_fails_pattern`. Run
`uv run pytest tests/authoring/test_patterns.py -q`.

### Task 9: Build, reports, and provider contamination

Create `src/satyrn_model/authoring/build.py`,
`src/satyrn_model/authoring/diversity.py`,
`tests/authoring/test_build.py`, and `authoring build`.

- Render qualified source and generated intents; apply local gates, provider
  qualification, exact dedup, and `check_contamination(snapshot, benchmark)`.
  A contamination conflict halts publication.
- Atomically write corpus, full-content `reports/dropped.jsonl`, `build.md`,
  source/license inventory, a row-to-seed-to-occurrence lineage bundle with
  immutable source refs/licenses and pattern/decision links, and a manifest
  containing provider/execution, interpreter, policy, decision, pattern-input,
  composition-profile, and lineage fingerprints.
- Structural fingerprints and optional external embedding report are diversity
  metrics only. If emitted, embeddings record model/revision/settings and have
  no acceptance effect.

Start with `test_contamination_halts_publication`, `test_drop_has_full_content`,
`test_no_cache_is_byte_reproducible`, and `test_interrupted_write_is_atomic`.
Run `uv run pytest tests/authoring/test_build.py -q`.

### Task 10: Pilot and calibrated thresholds

Create `sampling.toml`, `reports/threshold-derivation.md`, and
`tests/authoring/test_sampling.py`.

- Build a qualified ~500-row pilot against the committed composition profile
  and commit derivations for diversity, composition tolerance, review budget,
  and any semantic-near gate. If the profile changes, version the decision,
  regenerate the nested selection, and rerun calibration rather than declaring
  an old pilot to match a new target. Supply
  calibration rows to the provider; SP5 never selects contamination thresholds.
- Commit a nested, stratified selection plan for source kind, property,
  pattern, and seed. Decide explicitly whether the pilot itself is the 500
  snapshot; otherwise rerun calibration on the final selected 500.

Start with `test_sampling_is_nested_and_stratified` and
`test_final_500_requires_calibration_record`. Run
`uv run pytest tests/authoring/test_sampling.py -q`.

### Task 11: Publish 500 ⊂ 2k ⊂ 5k snapshots

Create `src/satyrn_model/authoring/publish.py` and
`tests/authoring/test_publish.py`.

- Produce immutable, composition-matched nested snapshots and manifests with
  fixed row IDs, strata, fingerprints, exact-duplicate result, source/license
  inventory, self-contained row-to-seed-to-occurrence lineage and NOTICE
  material, provider benchmark fingerprint, and effective-diversity reports.
- Recheck provider qualification and contamination under the calibrated policy
  before publishing each snapshot.

Start with `test_snapshot_ids_are_nested`, `test_manifest_has_all_strata`,
`test_snapshot_lineage_is_self_contained`, and
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
- The provider reset/package baseline is consumed before Task 1; no SP5-local
  substitute scaffold or cross-worktree import exists.
- Every final row is stdlib-only, source/license-attributed, safe to offer to
  the provider, and provider-qualified.
- Exact duplicates are absent; structural/embedding measures remain metrics,
  not false duplicate proofs.
- All ten planted defects fail live at the named stage.
- `authoring build --no-cache` is byte-reproducible and published 500 ⊂ 2k ⊂
  5k snapshots are stratified, composition-matched to a versioned data-owner
  profile, lineage-complete, and fingerprinted.
