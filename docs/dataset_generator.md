# Dataset generation

Use the `corpus_builder` package to generate fine-tuning datasets.

## Install

Install the `satyrn-dataset` command into your environment from the `corpus_builder` package.

```sh
uv pip install -e ./corpus_builder
```

## Generating datasets

Each subcommand generates one dataset type, reading source material from `--input-dir` and writing JSONL to 
`--output-dir`.

```sh
satyrn-dataset cpt --input-dir DIR --output-dir DIR   # Continued Pretraining (CPT)
satyrn-dataset sft --input-dir DIR --output-dir DIR   # Supervised Fine-Tuning (SFT)
satyrn-dataset rl  --input-dir DIR --output-dir DIR   # Reinforcement Learning (RL)
```
