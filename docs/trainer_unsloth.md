# Model training

Use the `satyrn-unsloth` package to fine-tune models with Unsloth.

## Install

Prerequisites:
- make sure you have a Python version matching `>=3.13.9,<3.15`
- make sure you have an Nvidia driver for CUDA 13, CUDA 12.8 is not supported

Install the `satyrn-unsloth` command into your environment from the `trainer/unsloth` package.

```sh
uv pip install -e ./trainer/unsloth
```

## Run a fine-tuning experiment

Pass the name of an experiment config to `satyrn-unsloth`.

```sh
satyrn-unsloth --config-name experiment/pep750-qwen2.5-0.5b
```

In experiment config `py3.15` you can swap the model with `model=`, naming any config in 
`trainer/unsloth/configs/model`:

```sh
satyrn-unsloth --config-name experiment/py3.15 model=qwen3.6-27b
```

Anything set in the experiment config can be overridden on the same line:

```sh
satyrn-unsloth --config-name experiment/py3.15 model=qwen3-coder-30b-a3b load_in_4bit=true cpt.batch_size=2
```
