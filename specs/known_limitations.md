# Known Limitations

This file records current shortcomings and their observable impact. It does
not own remediation planning or work-item metadata; follow the
[repository knowledge map](README.md) for those owners.

## Existing failure-policy exceptions

### gVisor falls back to ordinary Docker after a warning

SFT generation uses gVisor when `runsc` is registered. When it is unavailable,
the command warns and continues with hardened ordinary Docker. Generated-code
logic remains available, but the isolation guarantee is weaker because the
container shares the Docker host's Linux kernel. The behavior is an existing
exception to the repository's no-fallback rule.

### Per-idea SFT failures are broadly skipped

Expected quality rejections and unexpected provider, runtime, or programming
exceptions can all log `Skipping idea` and return no row. The run continues and
does not emit an aggregate accepted/rejected/error summary. A dataset can
therefore be partial without machine-readable failure accounting.

### Trainer RL does not fail the run

Corpus-builder RL fails explicitly because it is unimplemented. Trainer RL
only logs an error when an RL dataset is configured, then can finish normally.
That can make an unperformed requested stage appear successful and violates
fail-fast semantics.

## Reproducibility limitation

Parallel SFT writes rows in future-completion order. Individual rows remain
valid, but equivalent runs can produce different ordering, hashes, diffs, and
order-derived train/evaluation membership.

## Incomplete stage support

The intended sequence includes CPT, SFT, and RL. Corpus-builder and trainer RL
are not implemented; their distinct failure behaviors are described above and
in the package contracts.

## Repository governance considerations

The repository does not yet provide a `LICENSE`, `CONTRIBUTING.md`,
`CODE_OF_CONDUCT.md`, or `SECURITY.md`. Their content and introduction require
separate maintainer decisions.
