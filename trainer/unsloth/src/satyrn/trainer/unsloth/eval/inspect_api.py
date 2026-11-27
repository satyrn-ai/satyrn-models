"""`ModelAPI` that lets inspect_ai eval a live in-memory (model, tokenizer) pair."""

from __future__ import annotations

from contextvars import ContextVar
from copy import copy
from typing import TYPE_CHECKING

from inspect_ai._util.registry import RegistryInfo, set_registry_info
from inspect_ai.model import ContentReasoning, ContentText
from inspect_ai.model._model import ModelAPI
from inspect_ai.model._providers.hf import HuggingFaceAPI

from satyrn.trainer.unsloth.eval.agent_eval.tool_calls import parse_tool_calls
from satyrn.trainer.unsloth.rl.code_tester import split_thinking

# The tools of the generate call in progress: rendered into the chat template, but parsed by us
_render_tools: ContextVar[list | None] = ContextVar("render_tools", default=None)

if TYPE_CHECKING:
    from inspect_ai.model import ChatMessage, GenerateConfig, ModelOutput
    from inspect_ai.tool import ToolChoice, ToolInfo
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase


def standard_tool_calls(messages: list) -> list:
    """Messages with each tool call in the Hugging Face chat-template format.

    inspect_ai dumps a tool call flat, as `{"id", "function": "<name>", "arguments"}`. Chat templates (Qwen,
    Mellum, Gemma) expect `{"type": "function", "function": {"name", "arguments"}}`; Qwen3.8's raises
    "Tool call is missing a function name" on the flat form, so every agent turn after the first failed.
    """
    converted = []
    for message in messages:
        if getattr(message, "tool_calls", None):  # inspect_ai before 0.3.290 passes ChatMessage objects
            message = message.model_dump(exclude_none=True)
        calls = message.get("tool_calls") if isinstance(message, dict) else None
        if calls:
            message = message | {
                "tool_calls": [
                    call
                    if isinstance(call.get("function"), dict)
                    else {
                        "type": "function",
                        "id": call.get("id"),
                        "function": {"name": call["function"], "arguments": call.get("arguments") or {}},
                    }
                    for call in calls
                ]
            }
        converted.append(message)
    return converted


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

        # inspect_ai only reshapes earlier tool calls for a chat template when the model name names the family,
        # and ours is always `huggingface-local`, so reshape them here (on our copy of the tokenizer only)
        render = self.tokenizer.apply_chat_template
        self.tokenizer.apply_chat_template = lambda conversation, *args, **kwargs: render(
            standard_tool_calls(conversation), *args, **kwargs
        )

    async def generate(
        self, input: list[ChatMessage], tools: list[ToolInfo], tool_choice: ToolChoice, config: GenerateConfig
    ) -> ModelOutput:
        """Generate as `HuggingFaceAPI` does, stripping thinking from `completion` while keeping it on the message.

        With tools, the template still renders them, but inspect_ai's parser is skipped (it chooses a format by
        model name, and ours is always `huggingface-local`) and the calls are parsed in the family's own format.
        """
        token = _render_tools.set(tools)
        try:
            output = await super().generate(input, [], tool_choice, config)
        finally:
            _render_tools.reset(token)
        thinking, answer = split_thinking(output.completion)
        calls = []
        if tools:
            answer, calls = parse_tool_calls(answer, tools)
        output.completion = answer
        if output.choices:
            message = output.choices[0].message
            if thinking:
                message.content = [ContentReasoning(reasoning=thinking), ContentText(text=answer)]
            elif tools:
                message.content = answer
            if calls:
                message.tool_calls = calls
        return output

    def hf_chat(self, messages: list[ChatMessage], tools: list[ToolInfo]) -> str:
        """Render the chat with the tools of the generate call in progress."""
        return super().hf_chat(messages, tools or _render_tools.get() or [])
