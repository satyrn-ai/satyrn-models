# Dataset generation

Use the `corpus_builder` package to generate fine-tuning datasets.

## Install

Install the `satyrn-dataset` command into your environment from the `corpus_builder` package.

```sh
uv pip install -e ./corpus_builder
```

## Collecting input material

Before generating a dataset, gather the source documents it draws from.

### Gather Python Enhancement Proposals (PEPs)

Download the PEPs for a Python version into `datasets/python3.15/input/docs/`

```sh
satyrn-dataset download-inputs 3.15
```

### Gather recent changes in CPython Docs

To collect and download the documentation changes for CPython, perform the following steps.

Clone CPython into any path on your system:

```sh
git clone --depth 1 https://github.com/python/cpython.git /path/to/cpython
```

Collect the documentation sections tied to changes in a Python version (note: make sure that you use `Doc` directory of the CPython repo as the input):

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

### Continued Pretraining (CPT) datasets

`cpt` converts every `.rst` file under `input-dir` to Markdown and writes one row per file to
a `cpt.jsonl` file in `output-dir`.

Usage example:

```sh
satyrn-dataset cpt --input-dir datasets/python3.14/input/docs --output-dir datasets/python3.14/
satyrn-dataset cpt --input-dir datasets/python3.15/input/docs --output-dir datasets/python3.15/
```
