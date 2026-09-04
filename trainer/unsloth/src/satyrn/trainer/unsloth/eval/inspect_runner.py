"""Run inspect_ai evals against a live (model, tokenizer) pair mid-training.

inspect_ai's hf provider imports transformers, so every inspect_ai import is
deferred into `run_inspect_eval` to keep this module importable before unsloth.
"""

import inspect_ai
import mlflow
from inspect_ai.model import GenerateConfig, Model
from inspect_evals.humaneval import humaneval

from satyrn.trainer.unsloth.eval.utils import model_in_inference_mode


def run_inspect_eval(stage, model, tokenizer, enable_thinking=False, max_new_tokens=16384, batch_size=8, limit=None):

    # Lazy import to allow Unsloth patching of Torch and Transformers
    from satyrn.trainer.unsloth.eval.inspect_api import InMemoryHuggingFaceAPI

    api = InMemoryHuggingFaceAPI(model, tokenizer, enable_thinking)
    with model_in_inference_mode(model):
        log = inspect_ai.eval(
            humaneval(sandbox="local"),
            model=Model(api, GenerateConfig(max_tokens=max_new_tokens, max_connections=batch_size)),
            limit=limit,
            max_samples=batch_size,
            display="plain",
        )

    mlflow.log_metrics(
        {
            f"{stage}_{task.eval.task_display_name}_{score.name}_accuracy": score.metrics["accuracy"].value
            for task in log
            if task.results
            for score in task.results.scores
            if score.metrics and "accuracy" in score.metrics
        }
    )
    return log
