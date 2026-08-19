# Unsloth Trainer

The `satyrn-unsloth` package runs configured training stages with Unsloth.
Complete behavior and failure semantics are in the
[Unsloth-trainer contract](../../specs/contracts/unsloth_trainer.md).

## Install

Use Python 3.13 and install from the repository root:

```sh
uv pip install -e ./trainer/unsloth
```

Set the Hugging Face and MLflow variables listed in
[`.env.example`](../../.env.example). The runtime requires the hardware and
drivers supported by the pinned Unsloth distribution.

## Run the shipped experiment

```sh
satyrn-unsloth --config-name experiment/pep750-qwen2.5-0.5b
```

Hydra overrides may be appended to that command. The
`configs/model/mellum2-12b-a2.5.yaml` file is a selectable model group, not a
complete experiment.
