"""`ModelAPI` that lets inspect_ai eval a live in-memory (model, tokenizer) pair."""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING

from inspect_ai._util.registry import RegistryInfo, set_registry_info
from inspect_ai.model import ContentReasoning, ContentText
from inspect_ai.model._model import ModelAPI
from inspect_ai.model._providers.hf import HuggingFaceAPI

from satyrn.trainer.unsloth.rl.code_tester import split_thinking

if TYPE_CHECKING:
    from inspect_ai.model import ChatMessage, GenerateConfig, ModelOutput
    from inspect_ai.tool import ToolChoice, ToolInfo
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase


class InMemoryHuggingFaceAPI(HuggingFaceAPI):
    """Inspect-AI HuggingFaceAPI which wraps a live model and tokenizer instead of loading one.

    Skips `HuggingFaceAPI.__init__` (which always calls `from_pretrained`).
    """

    def __init__(self, model: Module, tokenizer: PreTrainedTokenizerBase, enable_thinking: bool) -> None:
        name = "huggingface-local"
        ModelAPI.__init__(self, model_name=name)
        set_registry_info(self, RegistryInfo(type="modelapi", name=name))

        self.model = model
        self.tokenizer = copy(tokenizer)

        # attributes normally set by HuggingFaceAPI.__init__
        self.batch_size = None
        self.chat_template = None
        self.use_chat_template = None
        self.enable_thinking = enable_thinking
        self.tokenizer_call_args = {}
        self.hidden_states = None
        self.do_sample = False  # greedy decode for eval

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"

    async def generate(
        self, input: list[ChatMessage], tools: list[ToolInfo], tool_choice: ToolChoice, config: GenerateConfig
    ) -> ModelOutput:
        """Generate as `HuggingFaceAPI` does, stripping thinking from `completion` while keeping it on the message."""
        output = await super().generate(input, tools, tool_choice, config)
        thinking, answer = split_thinking(output.completion)
        output.completion = answer
        if thinking and output.choices:
            content = [ContentReasoning(reasoning=thinking), ContentText(text=answer)]
            output.choices[0].message.content = content
        return output
