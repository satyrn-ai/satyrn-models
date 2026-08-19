# Product Design

## Purpose

Satyrn Models is an open-source, community-owned, local-first pipeline for
producing datasets and training and evaluating models on Python features
introduced after a base model's knowledge cutoff.

The intended learning sequence is:

1. continued pretraining (CPT) on source material;
2. supervised fine-tuning (SFT) on verified prompt/response examples; and
3. reinforcement learning (RL) against an explicit reward signal.

Local-first means contributors can inspect source data, generated examples,
training configuration, logs, and artifacts on hardware they control. External
model, registry, and source services remain explicit dependencies rather than
hidden execution backends.

## Current capabilities

- The corpus builder downloads selected Python 3.14 and 3.15 source documents,
  extracts CPython documentation changes, renders CPT JSONL, and generates
  execution-checked SFT JSONL.
- The Unsloth trainer runs configured CPT and SFT stages, evaluates a fixed
  train/test split during those stages, answers a fixed question set before and
  after each stage, and records training results and answer traces in MLflow.
- The repository includes historical PEP 750 experiments as evidence, not as
  current pipeline contracts.

Complete observable behavior is owned by the
[corpus-builder](contracts/corpus_builder.md) and
[Unsloth-trainer](contracts/unsloth_trainer.md) contracts.

## Planned capabilities

Everything in this section is planned and is not implemented unless a current
contract says otherwise.

- **RL dataset production:** generate and verify reward-learning inputs.
- **RL training:** train against configured reward functions and fail clearly
  when the requested stage cannot run.
- **Reproducible dataset generation:** make parallel SFT output identity stable
  across equivalent runs and report rejected examples by category.
- **Explicit sandbox policy:** make the selected isolation level visible and
  prevent an unapproved security downgrade.

GitHub issues own the scope, priority, dependencies, and status of work that
implements these capabilities.

## Deliberate boundaries

- Satyrn Models does not hide training or corpus generation behind a hosted
  control plane.
- Historical spike plans do not define current product behavior.
- MLflow is the model registry and training-results tracker; it does not define
  product acceptance.
