"""Pydantic schema for the composed Hydra experiment config."""

from __future__ import annotations

import logging
import math
import operator
from pathlib import Path
from typing import Literal

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

StageName = Literal["pre", "cpt", "sft", "rl"]


def basename(path: str) -> str:
    """Return the final path segment."""
    return Path(path).name


OmegaConf.register_resolver("mul", operator.mul)
OmegaConf.register_resolver("max", lambda *values: max(values))
OmegaConf.register_resolver("basename", basename)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpt: CptStageConfig
    sft: SftStageConfig
    rl: RlStageConfig
    datasets: DatasetsConfig
    model: ModelConfig
    mlflow: MlflowConfig

    eval_ratio: float
    load_in_4bit: bool
    logging_steps: int
    max_seq_length: int
    max_steps: int
    optim: str
    eval_stages: list[StageName]
    pre_model_eval: bool
    rng_seed: int
    run_name: str

    push_to_hub: bool
    push_to_hub_path: str | None


class PeftConfig(BaseModel):
    """LoRA adapter settings."""

    model_config = ConfigDict(extra="forbid")

    r: int
    lora_alpha: int
    adapter_scale: float
    lora_dropout: float
    target_modules: list[str] | None
    finetune_attention_modules: bool
    finetune_mlp_modules: bool
    finetune_language_layers: bool
    finetune_vision_layers: bool
    finetune_audio_layers: bool


class TemplateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction_part: str
    response_part: str


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enable_thinking: bool
    peft: PeftConfig
    template: TemplateConfig


class MlflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_uri: str
    experiment_name: str


class DatasetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpt: str | list[str] | None
    sft: str | list[str] | None
    rl: str | list[str] | None


class CptStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packing: bool
    prepack_dataset: bool
    seq_len: int
    batch_size: int
    eval_batch_size: int
    eval_steps: int | None
    checkpoint_steps: int | None
    gradient_accumulation_steps: int
    num_train_epochs: int
    learning_rate: float


class SftStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq_len: int
    batch_size: int
    eval_batch_size: int
    eval_steps: int | None
    checkpoint_steps: int | None
    gradient_accumulation_steps: int
    num_train_epochs: int
    learning_rate: float


class RlStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_size: int
    gradient_accumulation_steps: int
    num_generations: int
    max_completion_length: int
    num_train_epochs: int
    learning_rate: float
    beta: float


def validate_config(cfg: DictConfig) -> ExperimentConfig:
    return ExperimentConfig.model_validate(OmegaConf.to_container(cfg, resolve=True))


def is_evaluated(config: ExperimentConfig, stage: StageName) -> bool:
    """Return whether the eval suite runs after stage; pre_model_eval=false also skips pre."""
    return stage in config.eval_stages and (stage != "pre" or config.pre_model_eval)


def log_config(cfg: DictConfig) -> None:
    logger.info("Config:\n%s", OmegaConf.to_yaml(cfg, resolve=True))


def calculate_eval_steps(
    train_row_count: int,
    stage: CptStageConfig | SftStageConfig,
    max_steps: int,
    max_eval_count: int = 12,
) -> int:
    """Return the smallest multiple-of-5 eval interval with at most max_eval_count evals."""
    if max_steps > 0:
        total_steps = max_steps
    else:
        batches_per_epoch = math.ceil(train_row_count / stage.batch_size)
        steps_per_epoch = max(1, math.ceil(batches_per_epoch / stage.gradient_accumulation_steps))
        total_steps = steps_per_epoch * stage.num_train_epochs

    min_eval_steps = (total_steps // (max_eval_count + 1)) + 1
    eval_steps = max(5, math.ceil(min_eval_steps / 5) * 5)
    return eval_steps
