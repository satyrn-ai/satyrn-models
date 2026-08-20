# Project Structure

## System flow

```text
Python source material
        |
        v
corpus_builder --satyrn-dataset--> datasets/*.jsonl
        |
        v
trainer/unsloth --satyrn-unsloth--> outputs/ + results/ + MLflow
```

The repository contains two independently packaged Python applications. There
is no root Python distribution or shared runtime package.

## Corpus-builder boundary

`corpus_builder` owns source acquisition, documentation extraction, CPT
rendering, SFT generation, execution checks, and dataset serialization. It may
call remote source and model services and executes generated Python in Docker.
Its public boundary is the `satyrn-dataset` CLI and the JSONL formats described
by the [corpus-builder contract](../contracts/corpus_builder.md).

## Trainer boundary

`trainer/unsloth` owns Hydra experiment composition, configuration validation,
model loading, LoRA setup, stage orchestration, training artifacts, and MLflow
tracking. Its public boundary is the `satyrn-unsloth` CLI, experiment YAML, and
the behavior described by the
[Unsloth-trainer contract](../contracts/unsloth_trainer.md).

The trainer consumes datasets as files. It does not import corpus-builder
internals or generate source examples.

## Repository-owned data and evidence

- `datasets/` holds checked-in or locally generated dataset artifacts.
- `outputs/` holds trainer stage outputs and is ignored by Git.
- `results/` holds run logs and other run evidence; only its placeholder is
  tracked by default.
- `spikes/` holds dated, non-normative experiments and research.

Exact dependency versions, entry-point declarations, model identifiers, and
configuration values remain owned by package manifests, source, and
YAML configuration rather than this architecture document.
