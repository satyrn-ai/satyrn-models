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

# transformers.set_seed() (called by SFTTrainer for training reproducibility) reseeds the same
# global random module OpenTelemetry's default IdGenerator draws trace/span IDs from, causing
# eval traces from different stages to collide. Isolate trace-ID generation from that seed.
os.environ.setdefault("MLFLOW_TRACE_USE_ISOLATED_RANDOM_ID_GENERATOR", "true")

QUESTIONS = [
    "What is the latest Python version?",
    "Using Python t-strings: greet a user by name with a reusable template",
    "Using Python lazy imports: load the json module only when it is first used",
]


def run_eval_qa(stage: StageName, model: Module, tokenizer: PreTrainedTokenizerBase) -> None:
    """Ask every question in QUESTIONS and log the answers."""

    @mlflow.trace
    def answer_question(prompt: str) -> str:
        """Return the model's answer to one question."""
        mlflow.update_current_trace(session_id=stage)
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

    # For MoE models, output_router_logits carries the router's load-balancing loss during
    # training. Generation collects no router logits, so it must be off here.
    config = model.config.get_text_config()
    if getattr(config, "output_router_logits", None) is not None:
        config.output_router_logits = False

    # Training mode keeps dropout on, gradient checkpointing recomputing, and the KV cache off
    from unsloth import FastModel

    FastModel.for_inference(model)
    try:
        for question in QUESTIONS:
            logger.info("%s\n%s\n\n", question, answer_question(question))
    finally:
        FastModel.for_training(model)
