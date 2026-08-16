"""Pydantic schema for the composed Hydra experiment config."""

import logging
import operator

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

OmegaConf.register_resolver("mul", operator.mul)
OmegaConf.register_resolver("max", lambda *values: max(values))
OmegaConf.register_resolver("basename", lambda model_id: model_id.rpartition("/")[-1])


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


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    peft: PeftConfig


class MlflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_uri: str
    experiment_name: str


class DatasetsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpt: str | None
    sft: str | None
    rl: str | None


class CptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packing: bool
    num_train_epochs: int
    learning_rate: float


class SftConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_train_epochs: int
    learning_rate: float


class RlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_generations: int
    max_prompt_length: int
    max_completion_length: int
    learning_rate: float
    reward_funcs: list[str]


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_name: str
    load_in_4bit: bool
    max_seq_length: int
    batch_size: int
    gradient_accumulation_steps: int
    optim: str
    logging_steps: int
    eval_ratio: float
    mlflow: MlflowConfig
    datasets: DatasetsConfig
    cpt: CptConfig
    sft: SftConfig
    rl: RlConfig
    model: ModelConfig


def validate_config(cfg: DictConfig) -> ExperimentConfig:
    return ExperimentConfig.model_validate(OmegaConf.to_container(cfg, resolve=True))


def log_config(cfg: DictConfig) -> None:
    logger.info("Config:\n%s", OmegaConf.to_yaml(cfg, resolve=True))
