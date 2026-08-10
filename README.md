# satyrn-models

Fine-tuning pipeline for SatyrnAI models.

## Layout

- `corpus_builder/` — dataset generation (`satyrn-dataset` CLI)
- `trainer/unsloth/` — model fine-tuning (`satyrn-unsloth` CLI)
- `spikes/` — experiments which are not part of the main pipeline
- `datasets/`, `results/` — generated artifacts

## Quickstart

1. Generating datasets — see [docs/dataset_generator.md](docs/dataset_generator.md).
2. Fine-tuning models — see [docs/trainer_unsloth.md](docs/trainer_unsloth.md).
