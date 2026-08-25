# satyrn-model roadmap

> **Superseded on `main`.** This file is retained as a signpost, not as the
> current execution plan. Its earlier roadmap and decisions remain available in
> Git history. Current work is owned by GitHub issues; see the
> [current product design](../../../../specs/design.md).

The project is now split across worktrees:

- `worktree-tstrings-rebuild` owns provider infrastructure: dataset contracts,
  verification, contamination controls, benchmarks, training, and evaluation.
- `worktree-sp5-corpus-brainstorm` owns t-string training-data production:
  sources, seeds, patterns, generated rows, and dataset snapshots.
- `worktree-overnight-tstrings-spike` is historical evidence only. Its code is
  deliberately not merged or reused.

The worktree pointers below are historical. The former measure → harvest →
synthesize roadmap is retained only as context.
