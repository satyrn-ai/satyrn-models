"""Generate answers to a fixed set of questions, to compare a model before and after training."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

logger = logging.getLogger(__name__)

QUESTIONS = [
    "What is the latest Python version?",
    "Using Python t-strings: greet a user by name with a reusable template",
    "Using Python lazy imports: load the json module only when it is first used",
]


def answer_question(
    model: Module,
    tokenizer: PreTrainedTokenizerBase,
    question: str,
    max_new_tokens: int = 250,
) -> str:
    """Return the model's answer to one question."""
    inputs = tokenizer.apply_chat_template(
        [{"role": "user", "content": question}],
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    output = model.generate(**inputs, max_new_tokens=max_new_tokens)
    generated = output[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=False)


def log_answers(model: Module, tokenizer: PreTrainedTokenizerBase) -> None:
    """Ask every question in QUESTIONS and log the answers."""
    for question in QUESTIONS:
        logger.info("%s\n%s\n\n", question, answer_question(model, tokenizer, question))
