"""Shared helpers for the eval stages."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torch.nn import Module


@contextlib.contextmanager
def model_in_inference_mode(model: Module):
    """Disable model in training mode for the duration of the block.

    Changes:
        - disable dropout
        - disable gradient checkpointing optimization
        - enable KV cache
        - for MoE models disable router's load-balancing loss (`output_router_logits`)
    """
    from unsloth import FastModel

    text_config = model.config.get_text_config()
    prev_router_logits = getattr(text_config, "output_router_logits", None)
    if prev_router_logits is not None:
        text_config.output_router_logits = False

    FastModel.for_inference(model)
    try:
        yield model
    finally:
        FastModel.for_training(model)
        if prev_router_logits is not None:
            text_config.output_router_logits = prev_router_logits
