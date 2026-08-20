# Unsloth-trainer Contract

## Package and invocation

The `satyrn-unsloth` distribution provides the `satyrn-unsloth` CLI. Hydra
composes the configuration named by `--config-name` from
`trainer/unsloth/configs/` and applies command-line overrides. Invocation
without a composed configuration prints a usage hint and returns without
training. Runnable commands live in the
[trainer README](../../trainer/unsloth/README.md).

## Configuration

Pydantic rejects extra fields after Hydra composition. Field types are
validated, but numeric ranges are not. The configuration groups cover:

- run name, quantization, sequence length, batching, optimizer, logging, and
  evaluation split;
- MLflow tracking URI and experiment name;
- nullable CPT, SFT, and RL dataset paths, each one file or a list of files;
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
model/tokenizer pair loads with the global maximum sequence length, and one
PEFT/LoRA model is created. Enabled stages then run in order against that same
model: CPT, SFT, and finally the RL branch.

A fixed three-question QA evaluation runs before training and again after each
completed CPT and SFT stage. Each answer is generated through the model's chat
template, decoded without special tokens, logged, and recorded as an MLflow
trace whose session id is the stage name.

Each stage reads its dataset file — or its list of files, concatenated in
order — fully into memory; blank lines are ignored and rows are not
schema-validated before dataset construction. Each implemented stage uses
`train_test_split(test_size=eval_ratio, seed=42)` and configures:

- the stage's train batch size and the shared evaluation batch size;
- configured gradient accumulation, optimizer, logging, and evaluation
  interval;
- MLflow reporting;
- the stage's maximum sequence length; and
- BF16 when CUDA reports support, otherwise FP16.

CPT trains on the `text` field and applies its packing, epoch, and
learning-rate values. With `prepack_dataset` enabled, documents are tokenized
and packed into sequences of the stage's length before the train/test split,
and trainer-side packing turns off. SFT applies its epoch and learning-rate
values without an explicit formatting function or dataset text field.

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
  CPT/SFT stage runs, dataset paths, training-row counts, per-stage QA
  evaluation traces, and the completed local log as `train.log`.

There is no explicit final-model export, Hub publication, or RL artifact.

## Failure behavior

Configuration is logged before validation. Configuration, secret, model,
PEFT, JSON, split, trainer, CUDA, and MLflow failures propagate without a
fallback model or backend. A failure before final log upload can leave the
local log without an MLflow `train.log` artifact.

The nonfatal RL branch is the current exception; see
[known limitations](../known_limitations.md).
