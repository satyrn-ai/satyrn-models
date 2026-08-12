# Dataset generation

Use the `corpus_builder` package to generate fine-tuning datasets.

## Install

Install the `satyrn-dataset` command into your environment from the `corpus_builder` package.

Activate a Python virtual environment and install the package. Use an editable install (`-e`) 
if you plan to change the `corpus_builder` code, so edits take effect without reinstalling:

```sh
$ source /path/to/venv/bin/activate
(venv) $ pip install -e ./corpus_builder
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

Collect the documentation sections tied to changes in a Python version. Make sure that you use `Doc` 
directory of the CPython repo as the input:

```sh
satyrn-dataset collect-doc-changes 3.15 /path/to/cpython/Doc
```

Writes to `datasets/python3.15/input/docs/changes/`.

## Generating datasets

Each subcommand generates one dataset type, writing JSONL to `--output-dir`. `cpt` reads source material
from `--input-dir` (a directory); `sft` and `rl` read from `--input` (a directory or a single doc file).

```sh
satyrn-dataset cpt --input-dir DIR --output-dir DIR   # Continued Pretraining (CPT)
satyrn-dataset sft --input PATH --output-dir DIR      # Supervised Fine-Tuning (SFT)
satyrn-dataset rl  --input PATH --output-dir DIR      # Reinforcement Learning (RL)
```

### Generate Continued Pretraining (CPT) datasets

`cpt` converts every `.rst` file under `input-dir` to Markdown and writes one row per file to
a `cpt.jsonl` file in `output-dir`.

Usage example:

```sh
satyrn-dataset cpt --input-dir datasets/python3.14/input/docs --output-dir datasets/python3.14/
satyrn-dataset cpt --input-dir datasets/python3.15/input/docs --output-dir datasets/python3.15/
```

### Generate Supervised Fine-Tuning (SFT) datasets

`sft` uses an LLM to generate prompt-response pairs demonstrating new Python features based on documentation.

Each idea is verified by running in a sandboxed Docker container.

Docker is _required_, gVisor (`runsc` runtime) is _recommended_ for sandbox safety. You can verify if both are set 
up in your environment:

```sh
docker run --rm hello-world
docker run --rm --runtime=runsc hello-world
```

Output is written one row per conversation to a `sft.jsonl` file in `output-dir`, appending as it goes so
partial progress survives an interruption.

A `DEEPSEEK_API_KEY` is required in your environment (or a `.env` file - see `.env.example`).

Pass `--preview` to print each generated conversation to the terminal as it's saved, useful for
sanity-checking output quality while a run is in progress.

Usage example:

```sh
satyrn-dataset sft --input datasets/python3.15/input/docs --output-dir datasets/python3.15/ --python-version 3.15
```

Generating examples from a single source file with preview:

```sh
satyrn-dataset sft -i datasets/python3.14/input/docs/PEP750.rst -o datasets/python3.14/ --python-version 3.14 --preview
```
