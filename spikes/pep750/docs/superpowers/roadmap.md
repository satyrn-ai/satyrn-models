# satyrn-model roadmap

> **Superseded on `main`.** This file is retained as a signpost, not as the
> current execution plan. Its earlier roadmap and decisions remain available in
> Git history.

The project is now split across worktrees:

- `worktree-tstrings-rebuild` owns provider infrastructure: dataset contracts,
  verification, contamination controls, benchmarks, training, and evaluation.
- `worktree-sp5-corpus-brainstorm` owns t-string training-data production:
  sources, seeds, patterns, generated rows, and dataset snapshots.
- `worktree-overnight-tstrings-spike` is historical evidence only. Its code is
  deliberately not merged or reused.

For active work, read the relevant worktree's `README.md`, roadmap, spec, and
plan. The provider/consumer boundary is the current project structure; the
former measure → harvest → synthesize roadmap is historical context.
