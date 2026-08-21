# PEP 750 Historical Spike

> **Historical and non-normative.** This subtree records an earlier experiment.
> It does not define current product design, setup, agent workflow, or runtime
> behavior. Start from the [repository README](../../README.md),
> [product design](../../specs/design.md), and
> [knowledge map](../../specs/README.md).

The spike explored how a small local code model might learn Python 3.14
[template strings](https://peps.python.org/pep-0750/). Its value is the
evidence it captured, including failed directions and defects that ordinary
happy-path testing did not reveal.

## Evidence index

- [`DATASET_METHODOLOGY.md`](DATASET_METHODOLOGY.md) — literature review,
  dataset analysis, and corrected directions
- [`docs/superpowers/roadmap.md`](docs/superpowers/roadmap.md) — superseded
  coordination snapshot
- [Superseded dataset workflow spec](docs/superpowers/specs/2026-07-30-dataset-workflow-design.md)
- [Spike findings](docs/superpowers/research/2026-07-31-spike-findings.md)
- [Corpus-authoring brief](docs/superpowers/research/2026-07-31-corpus-authoring-brief.md)
- [Harvest architecture pivot](docs/superpowers/research/2026-07-31-harvest-architecture-pivot.md)

## Historical artifacts

The scripts, configuration, data, setup notes, branch names, model choices, and
provider guidance in this subtree describe the experiment at the time they were
written. They are retained for reproducibility and provenance, not as current
instructions or evidence that the present pipeline implements the same design.

Current behavior is owned by the repository's
[package contracts](../../specs/contracts/) and current work is owned by GitHub
issues.
