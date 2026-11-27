"""Run inspect_ai evals against a live (model, tokenizer) pair and log their metrics to MLflow."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import inspect_ai
import mlflow
from inspect_ai.model import GenerateConfig, Model
from inspect_evals.humaneval import humaneval

from satyrn.trainer.unsloth.eval.python_eval import python_eval
from satyrn.trainer.unsloth.eval.utils import model_in_inference_mode

if TYPE_CHECKING:
    from inspect_ai.log import EvalLog
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

# Stops inspect_ai.eval() resetting the root logger to WARNING on its first call
os.environ.setdefault("INSPECT_LOG_LEVEL", "NOTSET")


def run_eval_suite(model: Module, tokenizer: PreTrainedTokenizerBase, metadata: dict[str, Any]) -> list[EvalLog]:
    """Run HumanEval and PythonEval against a live model, storing metadata in the eval logs."""
    # Lazy import to allow Unsloth patching of Torch and Transformers
    from satyrn.trainer.unsloth.eval.inspect_api import InMemoryHuggingFaceAPI

    api = InMemoryHuggingFaceAPI(model, tokenizer, enable_thinking=False)
    eval_model = Model(api, GenerateConfig(max_tokens=4096, max_connections=8))
    with model_in_inference_mode(model), eval_model:
        return inspect_ai.eval(
            [humaneval(sandbox="local"), python_eval()],
            model=eval_model,
            metadata=metadata,
            max_samples=8,
            display="plain",
        )


def log_eval_metrics(logs: list[EvalLog], step: int, run_id: str | None = None) -> None:
    """Log the metrics of the eval logs to an MLflow run, the active one when run_id is None."""
    # Per-PEP scores stay in the printed results table only
    mlflow.log_metrics(
        {
            f"{log.eval.task_display_name}_{score.name}_{metric_name}": metric.value
            for log in logs
            if log.results
            for score in log.results.scores
            for metric_name, metric in score.metrics.items()
            if metric.params.get("group_key") != "pep"
        },
        step=step,
        run_id=run_id,
    )
