"""Run inspect_ai evals against a live (model, tokenizer) pair mid-training.

inspect_ai's hf provider imports transformers, so every inspect_ai import is
deferred into `run_inspect_eval` to keep this module importable before unsloth.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import inspect_ai
import mlflow
from inspect_ai.model import GenerateConfig, Model

from satyrn.trainer.unsloth.eval.utils import model_in_inference_mode

if TYPE_CHECKING:
    from inspect_ai import Task
    from inspect_ai.log import EvalLog
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

    from satyrn.trainer.unsloth.config import StageName

# Stops inspect_ai.eval() resetting the root logger to WARNING on its first call
os.environ.setdefault("INSPECT_LOG_LEVEL", "NOTSET")


def run_inspect_eval(
    stage: StageName,
    model: Module,
    tokenizer: PreTrainedTokenizerBase,
    task: Task,
    enable_thinking: bool = False,
    max_new_tokens: int = 4096,
    batch_size: int = 8,
    limit: int | None = None,
) -> list[EvalLog]:

    # Lazy import to allow Unsloth patching of Torch and Transformers
    from satyrn.trainer.unsloth.eval.inspect_api import InMemoryHuggingFaceAPI

    api = InMemoryHuggingFaceAPI(model, tokenizer, enable_thinking)
    with model_in_inference_mode(model):
        log = inspect_ai.eval(
            task,
            model=Model(api, GenerateConfig(max_tokens=max_new_tokens, max_connections=batch_size)),
            limit=limit,
            max_samples=batch_size,
            display="plain",
        )

    # Per-PEP scores stay in the printed results table only
    mlflow.log_metrics(
        {
            f"{stage}_{result.eval.task_display_name}_{score.name}_{metric_name}": metric.value
            for result in log
            if result.results
            for score in result.results.scores
            for metric_name, metric in score.metrics.items()
            if metric.params.get("group_key") != "pep"
        }
    )
    return log
