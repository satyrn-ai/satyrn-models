# Model training

Use the `satyrn-unsloth` package to fine-tune models with Unsloth.

## Install

Install the `satyrn-unsloth` command into your environment from the `trainer/unsloth` package.

```
uv pip install -e ./trainer/unsloth
```

Note: if using Mellum models, you may need to upgrade transformers:

```
uv pip install --upgrade transformers
```

## Run a fine-tuning experiment

Pass the name of an experiment config to `satyrn-unsloth`.

```
satyrn-unsloth --config-name experiment/python3.15-mellum2
```
