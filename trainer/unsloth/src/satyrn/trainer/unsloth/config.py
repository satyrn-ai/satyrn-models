"""Pydantic schema for the composed Hydra experiment config."""

from __future__ import annotations

import logging
import operator
from typing import Literal

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

StageName = Literal["pre", "cpt", "sft", "rl"]

OmegaConf.register_resolver("mul", operator.mul)
OmegaConf.register_resolver("max", lambda *values: max(values))
OmegaConf.register_resolver("basename", lambda model_id: model_id.rpartition("/")[-1])


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
    run_name: str


class PeftConfig(BaseModel):
    """Arguments passed to FastModel.get_peft_model."""

    model_config = ConfigDict(extra="forbid")

    r: int
    lora_alpha: int
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
    eval_steps: int
    gradient_accumulation_steps: int
    num_train_epochs: int
    learning_rate: float


class SftStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq_len: int
    batch_size: int
    eval_batch_size: int
    eval_steps: int
    gradient_accumulation_steps: int
    num_train_epochs: int
    learning_rate: float


class RlStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_size: int
    gradient_accumulation_steps: int
    num_generations: int
    max_completion_length: int
    learning_rate: float


def validate_config(cfg: DictConfig) -> ExperimentConfig:
    return ExperimentConfig.model_validate(OmegaConf.to_container(cfg, resolve=True))


def log_config(cfg: DictConfig) -> None:
    logger.info("Config:\n%s", OmegaConf.to_yaml(cfg, resolve=True))
