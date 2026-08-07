"""Pydantic schema for the composed Hydra experiment config."""

from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, ConfigDict


class LoraConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    alpha: int
    dropout: float
    target_modules: list[str]


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    lora: LoraConfig


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
    mlflow: MlflowConfig
    datasets: DatasetsConfig
    cpt: CptConfig
    sft: SftConfig
    rl: RlConfig
    model: ModelConfig


def validate_config(cfg: DictConfig) -> ExperimentConfig:
    return ExperimentConfig.model_validate(OmegaConf.to_container(cfg, resolve=True))
