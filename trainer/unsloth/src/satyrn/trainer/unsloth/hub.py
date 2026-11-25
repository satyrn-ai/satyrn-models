"""Publish trained models and their provenance to the Hugging Face Hub."""

from __future__ import annotations

import logging
import os
import re
import shlex
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import mlflow
from huggingface_hub import ModelCard
from hydra.core.hydra_config import HydraConfig
from jinja2 import Template
from mlflow.utils.git_utils import get_git_branch, get_git_commit
from mlflow.utils.mlflow_tags import MLFLOW_GIT_BRANCH, MLFLOW_GIT_COMMIT

if TYPE_CHECKING:
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase, ProcessorMixin

    from satyrn.trainer.unsloth.config import ExperimentConfig

logger = logging.getLogger(__name__)
CARD_START = "<!-- satyrn-training-card:start -->"
CARD_END = "<!-- satyrn-training-card:end -->"


def log_code_version() -> None:
    """Record the trainer's git revision on the active run before training."""
    code_dir = str(Path(__file__).resolve().parent)
    tags = {
        MLFLOW_GIT_BRANCH: get_git_branch(code_dir),
        MLFLOW_GIT_COMMIT: get_git_commit(code_dir),
    }
    mlflow.set_tags({key: value for key, value in tags.items() if value is not None})


def render_model_card(repo_id: str, config: ExperimentConfig, *, is_gguf: bool = False) -> str:
    """Render the Satyrn card section from the active training run."""
    run = mlflow.active_run()
    if run is None:
        raise RuntimeError("An active MLflow run is required to publish a model card")

    hydra_config = HydraConfig.get()
    tags = mlflow.get_run(run.info.run_id).data.tags
    config_name = hydra_config.job.config_name
    commit = tags.get(MLFLOW_GIT_COMMIT) or "Unavailable"
    config_url = None
    if (
        config_name
        and re.fullmatch(r"[\w./-]+", config_name)
        and not config_name.startswith("/")
        and ".." not in config_name.split("/")
        and re.fullmatch(r"[0-9a-fA-F]{7,40}", commit)
        and (Path(__file__).resolve().parents[4] / "configs" / f"{config_name}.yaml").is_file()
    ):
        config_url = (
            "https://github.com/satyrn-ai/satyrn-models/blob/" f"{commit}/trainer/unsloth/configs/{config_name}.yaml"
        )
    today = date.today()
    model_name = repo_id.rpartition("/")[-1]
    template = Template(Path(__file__).with_name("model_card.md.j2").read_text(encoding="utf-8"))
    return template.render(
        date=today.isoformat(),
        year=today.year,
        repo_id=repo_id,
        model_name=model_name,
        base_model=config.model.name,
        is_gguf=is_gguf,
        rl_enabled=config.datasets.rl is not None,
        citation_key="satyrn_" + re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_"),
        mlflow_run=(
            f"{mlflow.get_tracking_uri().rstrip('/')}/#/experiments/{run.info.experiment_id}/runs/{run.info.run_id}"
        ),
        config=config_name or "Unavailable",
        config_url=config_url,
        overrides=shlex.join(hydra_config.overrides.task),
        branch=tags.get(MLFLOW_GIT_BRANCH) or "Unavailable",
        commit=commit,
    )


def push_model_card(repo_id: str, rendered_card: str) -> None:
    """Preserve Unsloth's card and replace any previously published Satyrn section."""
    card = ModelCard.load(repo_id)
    section = f"{CARD_START}\n{rendered_card.strip()}\n{CARD_END}"
    before, marker, after = card.text.partition(CARD_START)
    if marker and CARD_END in after:
        card.text = before + section + after.split(CARD_END, 1)[1]
    else:
        card.text = f"{card.text.rstrip()}\n\n{section}\n"
    card.push_to_hub(repo_id)


def upload_to_hub(model: Module, processor: ProcessorMixin | PreTrainedTokenizerBase, config: ExperimentConfig) -> None:
    """Publish merged and GGUF models, preserving each generated card's metadata."""
    hub_model_id = config.push_to_hub_path or f"{os.environ['HF_USERNAME']}/{config.model.name.rpartition('/')[-1]}"
    gguf_hub_model_id = f"{hub_model_id}-GGUF"
    rendered_card = render_model_card(hub_model_id, config)
    rendered_gguf_card = render_model_card(gguf_hub_model_id, config, is_gguf=True)

    logger.info("Pushing merged model to Hugging Face Hub: https://huggingface.co/%s", hub_model_id)
    model.push_to_hub_merged(hub_model_id, processor, save_method="merged_16bit")
    push_model_card(hub_model_id, rendered_card)

    logger.info("Pushing GGUF model to Hugging Face Hub: https://huggingface.co/%s", gguf_hub_model_id)
    model.push_to_hub_gguf(gguf_hub_model_id, processor, quantization_method="q4_k_m")
    push_model_card(gguf_hub_model_id, rendered_gguf_card)
