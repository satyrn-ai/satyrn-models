# Developer Notes for Unsloth Trainer

Operational pitfalls when preparing an environment for `satyrn-unsloth`.
Declared dependencies are owned by [`pyproject.toml`](pyproject.toml),
per-model requirements by the files under [`configs/model`](configs/model),
and runtime behavior by the
[Unsloth-trainer contract](../../specs/contracts/unsloth_trainer.md).

The pinned `unsloth` distribution resolves `trl`, `transformers`, and `torch`
transitively rather than through `pyproject.toml`. The adjustments below are
therefore applied after installing the package, and are undone by a reinstall.

## Upgrade `trl` after installing

Unsloth resolves `trl==0.24.0`, which carries
[trl#6105](https://github.com/huggingface/trl/issues/6105). Upgrade it:

```sh
uv pip install "trl==1.7.0"
```

## Match `transformers` to the model

Models require different `transformers` versions, and those requirements are
mutually exclusive: one environment does not serve every model config. Newer
architectures need a version recent enough to know their `model_type`, while
others fail on that same version.

Each file in [`configs/model`](configs/model) records the version it was tested
against in its header comment. Read the header of the model you intend to train
and install that version together with the matching torch build:

```sh
uv pip install "transformers==<version>" "torch==2.11.0" "torchvision==0.26.0"
```

Reinstalling `transformers` alone can pull an incompatible torch, so pin all
three in the same command.

## Select the CUDA build

PyPI `torch==2.11.0` is a CUDA 13 build (`+cu130`). On 570-series Nvidia
drivers with CUDA 12.8, install the CUDA 12.8 build from `pytorch.org`:

```sh
uv pip install "torch==2.11.0" "torchvision==0.26.0" \
  --extra-index-url https://download.pytorch.org/whl/cu128
```
