"""`ModelAPI` that lets inspect_ai eval a live in-memory (model, tokenizer) pair."""

from copy import copy

from inspect_ai._util.registry import RegistryInfo, set_registry_info
from inspect_ai.model import GenerateConfig
from inspect_ai.model._model import ModelAPI
from inspect_ai.model._providers.hf import HuggingFaceAPI


class InMemoryHuggingFaceAPI(HuggingFaceAPI):
    """Inspect-AI HuggingFaceAPI which wraps a live model and tokenizer instead of loading one.

    Skips `HuggingFaceAPI.__init__` (which always calls `from_pretrained`).
    """

    def __init__(
        self,
        model,
        tokenizer,
        enable_thinking: bool,
        reasoning_effort: str = "medium",
        config: GenerateConfig | None = None,
    ):
        name = "huggingface-local"
        if not config:
            config = GenerateConfig()
        ModelAPI.__init__(self, model_name=name, config=config)
        set_registry_info(self, RegistryInfo(type="modelapi", name=name))

        self.model = model
        self.tokenizer = copy(tokenizer)

        # attributes normally set by HuggingFaceAPI.__init__
        self.batch_size = None
        self.chat_template = None
        self.use_chat_template = None
        self.enable_thinking = enable_thinking
        self.reasoning_effort = reasoning_effort
        self.tokenizer_call_args = {}
        self.hidden_states = None
        self.do_sample = False  # greedy decode for eval

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"

    def _apply_chat_template(self, hf_messages, tools_list, chat_template):
        # Apply reasoning effort
        return self.tokenizer.apply_chat_template(
            hf_messages,
            add_generation_prompt=True,
            tokenize=False,
            tools=tools_list if len(tools_list) > 0 else None,
            enable_thinking=self.enable_thinking,
            reasoning_effort=self.reasoning_effort,
        )
