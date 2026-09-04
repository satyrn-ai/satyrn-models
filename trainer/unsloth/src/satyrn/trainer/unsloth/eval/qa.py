"""Generate answers to a fixed set of questions, to compare a model before and after training."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import mlflow

from satyrn.trainer.unsloth.config import StageName

if TYPE_CHECKING:
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

logger = logging.getLogger(__name__)

# Do not remove. SFTTrainer calls transformers.set_seed(), which resets the global RNG that
# OpenTelemetry uses for trace IDs. Without this setting, every stage produces the same IDs and
# overwrites the previous stage's eval traces in MLflow.
os.environ.setdefault("MLFLOW_TRACE_USE_ISOLATED_RANDOM_ID_GENERATOR", "true")

QUESTIONS = [
    "What is the latest Python version?",
    "Using Python t-strings: greet a user by name with a reusable template",
    "Using Python lazy imports: load the json module only when it is first used",
]


def run_eval_qa(stage: StageName, model: Module, tokenizer: PreTrainedTokenizerBase) -> None:
    """Ask every question in QUESTIONS and log the answers."""
    session_id = f"{stage}-{mlflow.active_run().info.run_id[:8]}"

    @mlflow.trace
    def answer_question(prompt: str) -> str:
        """Return the model's answer to one question."""
        mlflow.update_current_trace(session_id=session_id)
        if span := mlflow.get_current_active_span():
            span.set_inputs(prompt)

        inputs = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            enable_thinking=False,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)

        max_new_tokens = 256
        output = model.generate(**inputs, max_new_tokens=max_new_tokens)
        generated = output[0][inputs["input_ids"].shape[-1] :]
        return tokenizer.decode(generated, skip_special_tokens=True)

    from satyrn.trainer.unsloth.eval.utils import model_in_inference_mode

    with model_in_inference_mode(model):
        for question in QUESTIONS:
            logger.info("%s\n%s\n\n", question, answer_question(question))
