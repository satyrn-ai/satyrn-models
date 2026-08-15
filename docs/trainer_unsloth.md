# Model training

Use the `satyrn-unsloth` package to fine-tune models with Unsloth.

## Install

Install the `satyrn-unsloth` command into your environment from the `trainer/unsloth` package.

```sh
uv pip install -e ./trainer/unsloth
```

Unsloth installs older `trl` and `transformers` than we need.

- `transformers>=5.10.1` for the Mellum model
- `trl>=1.7.0` fixes [trl#6105](https://github.com/huggingface/trl/issues/6105)

```sh
uv pip install --upgrade "trl==1.7.0" "transformers==5.15.0" "torch==2.11.0" "torchvision==0.26.0"
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
satyrn-unsloth --config-name experiment/py3.15 model=qwen3-coder-30b-a3b load_in_4bit=true batch_size=2
```
