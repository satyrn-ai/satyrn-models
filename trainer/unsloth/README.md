# Unsloth Trainer

The `satyrn-unsloth` package runs configured training stages with Unsloth.
Complete behavior and failure semantics are in the
[Unsloth-trainer contract](../../specs/contracts/unsloth_trainer.md).

## Install

Use a Python version matching `requires-python` in
[`pyproject.toml`](pyproject.toml) and install from the repository root:

```sh
uv pip install -e ./trainer/unsloth
```

Adjust the transitive `trl`, `transformers`, and `torch` versions after
installing; [`DEV_NOTES.md`](DEV_NOTES.md) owns those caveats and the CUDA
build selection.

Set the Hugging Face and MLflow variables listed in
[`.env.example`](../../.env.example). The runtime requires the hardware and
drivers supported by the pinned Unsloth distribution.

## Run an experiment

Pass the name of a config from [`configs/experiment`](configs/experiment):

```sh
satyrn-unsloth --config-name experiment/pep750-qwen2.5-0.5b
```

An experiment that declares a `/model` defaults group takes a model swap on
the command line, naming any config in [`configs/model`](configs/model). Those
files are selectable model groups, not complete experiments:

```sh
satyrn-unsloth --config-name experiment/py3.15 model=qwen3.6-27b
```

Append Hydra overrides for anything the experiment config sets:

```sh
satyrn-unsloth --config-name experiment/py3.15 model=qwen3-coder-30b-a3b load_in_4bit=true cpt.batch_size=2
```
