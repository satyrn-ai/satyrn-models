# Superseded dataset workflow spec

> **Historical context only.** This spec is retained at its original path so
> old references remain understandable, but it is no longer the source of
> truth for implementation on `main`. See the current
> [product design](../../../../../specs/design.md) and
> [contracts](../../../../../specs/contracts/).

The project now uses a provider/consumer split:

- `worktree-tstrings-rebuild` owns verification, dataset contracts,
  contamination controls, benchmarks, training, and evaluation.
- `worktree-sp5-corpus-brainstorm` owns t-string source collection, seed and
  pattern authoring, data generation, and dataset snapshots.

Use the repository's current specs and GitHub issues for new work. The original
spec and its decisions remain available in Git history.
