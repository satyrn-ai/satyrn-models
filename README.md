# satyrn-models

Fine-tuning pipeline for SatyrnAI models.

## Training plan

Models go through three training stages, building on one another:

1. **CPT** (Continued Pretraining) - train on raw text.
2. **SFT** (Supervised Fine-Tuning) - train on prompt/response pairs.
3. **RL** (Reinforcement Learning) - train on a reward signal.

## Repository layout

- `corpus_builder/` - dataset generation (`satyrn-dataset` CLI)
- `trainer/unsloth/` - model fine-tuning (`satyrn-unsloth` CLI)
- `benchmark/` - model benchmarking with evalplus (`satyrn-benchmark` CLI, marimo notebook)
- `spikes/` - experiments which are not part of the main pipeline
- `datasets/`, `results/` - generated artifacts

## Quickstart

1. Generating datasets - see [docs/dataset_generator.md](docs/dataset_generator.md).
2. Fine-tuning models - see [docs/trainer_unsloth.md](docs/trainer_unsloth.md).
3. Benchmarking models - see [docs/benchmark_evalplus.md](docs/benchmark_evalplus.md).
