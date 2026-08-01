# SP5 execution-readiness record

**Date:** 2026-08-01
**Status:** collection ready; provider-qualified production intentionally blocked

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

## Provider integration status

The provider design is at commit `b7ab02e` on
`worktree-tstrings-rebuild`; its package metadata is currently version `0.1.0`.
It has **not** published an installable contract release or canonical fixtures,
and its current plan specified subprocess isolation rather than an OS sandbox.
SP5 Task 6 remains blocked until the provider publishes all of:

1. an installable, versioned package and canonical consumer fixtures;
2. the documented `TaskRecord`/qualification/reference APIs;
3. a fail-closed OS sandbox guarantee for untrusted reference and candidate
   execution, with sandbox profile/version included in execution evidence.

The provider plan is amended with that sandbox requirement. A subprocess timeout
or run-twice result is not a substitute for it.

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
