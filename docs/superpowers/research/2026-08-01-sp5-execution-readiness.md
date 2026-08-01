# SP5 execution-readiness record

**Date:** 2026-08-01
**Status:** collection fixtures and local policy are ready; collection
implementation awaits the provider-owned reset/package baseline;
provider-qualified production is intentionally blocked

## Resolved local prerequisites

- The worktree and package require exactly CPython **3.14.5**. This matches the
  official CPython harvest checkout tag `v3.14.5`; each implementation run must
  still record `sys.version` in its manifest.
- [`sources.toml`](../../../sources.toml) defines the initial allowed SPDX set:
  `PSF-2.0`, `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, and `ISC`.
  Every source must provide an immutable ref, license identifier, attribution,
  and any required NOTICE text before it can enter a snapshot.
- Embedding clustering is deferred from v1. It is optional report-only work,
  has no acceptance effect, and must not introduce a model call into SP5.

## Shared package prerequisite

The current checkout has not yet consumed provider Task 0's reset/package
baseline. SP5 Tasks 1–5 do not call provider APIs, but they require that shared
`src` layout, `uv` test configuration, and `authoring` command installation
point; they must not recreate a competing scaffold. Before Task 1, land the
provider reset on `main`, merge or rebase this branch onto it, and prove a clean
`uv sync` plus the provider package-import smoke test. The source policy and
fixture inventory below are ready to use immediately after that precondition.

## Provider integration status

The provider design is at commit `bb93318` on
`worktree-tstrings-rebuild`; its package metadata is currently version `0.1.0`.
Its plan now requires a fail-closed OS sandbox, but it has **not** published an
installable contract release, canonical fixtures, or an implemented sandbox
guarantee. SP5 Task 6 remains blocked until the provider publishes all of:

1. an installable, versioned package and canonical consumer fixtures;
2. the documented `TaskRecord`/qualification/reference APIs;
3. a fail-closed OS sandbox guarantee for untrusted reference and candidate
   execution, with sandbox profile/version included in execution evidence.

A subprocess timeout or run-twice result is not a substitute for that
guarantee.

## Fixture corpus reserved for implementation

These fixture IDs are source-only. The concrete Python-source cases are
committed in [`tests/authoring/fixtures/collection_cases.json`](../../../tests/authoring/fixtures/collection_cases.json);
the Task 2–3 test suite turns them into executable fixtures before extractor
code is written.

| ID | Shape | Expected outcome |
|---|---|---|
| `literal_multiline` | multiline t-string literal | extract exact span |
| `nested_shadowing` | same name in nested scope | reject unresolved/shadowed binding |
| `multiple_cases` | two independent assertions in one method | split at assertion boundary |
| `multi_observation` | one described case with related `.strings` and `.values` assertions | preserve aligned properties/checks |
| `evidence_assertion_mismatch` | test-name evidence says `.values`; assertion checks `.strings` | reject before provider |
| `loop_subtest` | loop/subtest-generated cases | reject unless directly transformed |
| `private_helper` | CPython-style private assertion helper | reject; do not inline |
| `no_evidence` | no method/docstring/comment intent | reject |
| `multi_origin` | identical literal from two source locations | preserve both occurrences |
| `exact_repeat` | byte-identical candidate row | hard reject at build |
| `same_skeleton` | same AST skeleton, distinct static domain/semantics | retain and report |
| `unsafe_import` | `__import__`/dynamic import | reject before provider |
| `unsafe_file_process` | file read or subprocess/process primitive | reject before provider |
| `side_effect` | deterministic write/mutation expression | reject before provider |
| `format_spec_valid` | `t"{v:{w}}"` | preserve as valid |
| `format_spec_nested_fstring` | nested f-string in format spec expression | reject by policy |

This inventory is deliberately separate from provider adversarial cases: the
first eleven exercise SP5 collection and static gates; the final two establish
t-string policy precision after provider integration.
