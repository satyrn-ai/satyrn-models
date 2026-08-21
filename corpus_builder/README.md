# Corpus Builder

The `satyrn-corpus-builder` package provides the `satyrn-dataset` command.
Complete behavior and failure semantics are in the
[corpus-builder contract](../specs/contracts/corpus_builder.md).

## Install

From the repository root, with a Python 3.13-or-newer environment active:

```sh
python -m pip install -e ./corpus_builder
```

SFT generation also requires Docker and `DEEPSEEK_API_KEY`; copy the relevant
entry from [`.env.example`](../.env.example) into your environment or `.env`.

## Collect source material

```sh
satyrn-dataset download-inputs 3.15
git clone --depth 1 https://github.com/python/cpython.git /path/to/cpython
satyrn-dataset collect-doc-changes 3.15 /path/to/cpython/Doc
```

The first command writes selected source documents below
`datasets/python3.15/input/docs/`. The second Satyrn command extracts matching
CPython documentation changes into that tree.

## Generate datasets

```sh
satyrn-dataset cpt \
  --input-dir datasets/python3.15/input/docs \
  --output datasets/python3.15/cpt.jsonl

satyrn-dataset sft \
  --input datasets/python3.15/input/docs \
  --output datasets/python3.15/sft.jsonl \
  --python-version 3.15 \
  --workers 4 \
  --preview
```
