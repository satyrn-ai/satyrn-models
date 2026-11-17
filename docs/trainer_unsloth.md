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

### MoE models

With Unsloth 2026.11.5, Mellum2.1 needs `UNSLOTH_BLOCK_MOE=outside`. Without it, training runs out of GPU memory at
the first CPT step on an A100 80 GB and an RTX PRO 6000 96 GB, with this error:

```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1.12 GiB. GPU 0 has a total capacity of 94.97 GiB of which 443.56 MiB is free. Process 1 has 94.52 GiB memory in use. Of the allocated memory 93.63 GiB is allocated by PyTorch, and 142.51 MiB is reserved by PyTorch but unallocated.
```

If you see this error with Mellum or another MoE model, set the flag before training:

```sh
export UNSLOTH_BLOCK_MOE=outside
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
