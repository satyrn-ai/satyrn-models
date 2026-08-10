# Dataset generation

Use the `corpus_builder` package to generate fine-tuning datasets.

## Install

Install the `satyrn-dataset` command into your environment from the `corpus_builder` package.

```sh
uv pip install -e ./corpus_builder
```

## Collecting input material

Before generating a dataset, gather the source documents it draws from.

### Python Enhancement Proposals

Download the PEPs for a Python version into `datasets/python3.15/input/docs/`

```sh
satyrn-dataset download-inputs 3.15
```

### Changes in CPython Docs

Clone CPython:

```sh
git clone --depth 1 https://github.com/python/cpython.git /path/to/cpython
```

Collect the documentation sections tied to changes in a Python version:

```sh
satyrn-dataset collect-doc-changes 3.15 /path/to/cpython/Doc
```

Writes to `datasets/python3.15/input/docs/changes/`.

## Generating datasets

Each subcommand generates one dataset type, reading source material from `--input-dir` and writing JSONL to 
`--output-dir`.

```sh
satyrn-dataset cpt --input-dir DIR --output-dir DIR   # Continued Pretraining (CPT)
satyrn-dataset sft --input-dir DIR --output-dir DIR   # Supervised Fine-Tuning (SFT)
satyrn-dataset rl  --input-dir DIR --output-dir DIR   # Reinforcement Learning (RL)
```
