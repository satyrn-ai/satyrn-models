# Unsloth-trainer Contract

## Package and invocation

The `satyrn-unsloth` distribution requires Python 3.13 and provides the
`satyrn-unsloth` CLI. Hydra composes configuration from
`trainer/unsloth/configs/`.

The shipped experiment runs with:

```sh
satyrn-unsloth --config-name experiment/pep750-qwen2.5-0.5b
```

Hydra command-line overrides remain available. Invocation without a composed
configuration prints a usage hint and returns without training.

## Configuration

Pydantic rejects extra fields after Hydra composition. Field types are
validated, but numeric ranges are not. The configuration groups cover:

- run name, quantization, sequence length, batching, optimizer, logging, and
  evaluation split;
- MLflow tracking URI and experiment name;
- nullable CPT, SFT, and RL dataset paths;
- stage-specific training parameters; and
- model identifier and LoRA parameters.

The exact schema and values are owned by `config.py` and the YAML configuration
files. The default Hydra run directory is
`results/${now:%Y%m%d-%H%M}-${run_name}`.

After Unsloth initializes, `.env` is loaded and these variables are asserted
non-empty:

- `HF_TOKEN`
- `HF_USERNAME`
- `MLFLOW_TRACKING_USERNAME`
- `MLFLOW_TRACKING_PASSWORD`

A missing value raises `AssertionError`.

## Model and stage execution

Unsloth initializes before downstream training libraries. One base
model/tokenizer and one PEFT/LoRA model are created. Enabled stages then run in
order against that same model: CPT, SFT, and finally the RL branch.

Dataset JSONL is read fully into memory; blank lines are ignored and rows are
not schema-validated before dataset construction. Each implemented stage uses
`train_test_split(test_size=eval_ratio, seed=42)` and configures:

- equal per-device train and evaluation batch sizes;
- configured gradient accumulation, optimizer, logging, and evaluation
  interval;
- MLflow reporting;
- configured maximum sequence length; and
- BF16 when CUDA reports support, otherwise FP16.

CPT reads the configured CPT path, uses the `text` field, and applies its
packing, epoch, and learning-rate values. SFT reads the configured SFT path and
applies its epoch and learning-rate values without an explicit formatting
function or dataset text field.

Null dataset paths skip their stages. A configuration with all dataset paths
null is valid and can complete without training.

RL training is not implemented. A non-null RL dataset logs
`Unimplemented: RL training` but does not fail the run.

## Outputs and MLflow

- Hydra creates the timestamped run directory.
- Standard output and error are teed to `run.log` in append mode while the run
  body executes. Escape-sequence lines are omitted; carriage-return output
  retains only its final visible fragment.
- Stage output directories are `outputs/cpt` and `outputs/sft`.
- MLflow records system metrics, a root run, base-model/LoRA parameters, nested
  CPT/SFT stage runs, dataset paths, training-row counts, and the completed
  local log as `train.log`.

There is no explicit final-model export, Hub publication, or RL artifact.

## Failure behavior

Configuration is logged before validation. Configuration, secret, model,
PEFT, JSON, split, trainer, CUDA, and MLflow failures propagate without a
fallback model or backend. A failure before final log upload can leave the
local log without an MLflow `train.log` artifact.

The nonfatal RL branch is the current exception; see
[known limitations](../known_limitations.md).
