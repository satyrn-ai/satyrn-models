# Model training

Use the `satyrn-unsloth` package to fine-tune models with Unsloth.

## Install

Install the `satyrn-unsloth` command into your environment from the `trainer/unsloth` package.

```sh
uv pip install -e ./trainer/unsloth
```

Note: if using Mellum models, you may need to upgrade transformers:

```sh
uv pip install --upgrade transformers
```

## Run a fine-tuning experiment

Pass the name of an experiment config to `satyrn-unsloth`.

```sh
satyrn-unsloth --config-name experiment/python3.15-mellum2
```

For example:

```sh
satyrn-unsloth --config-name experiment/pep750-qwen2.5-0.5b
```
