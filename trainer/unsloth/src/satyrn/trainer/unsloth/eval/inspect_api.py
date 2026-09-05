"""`ModelAPI` that lets inspect_ai eval a live in-memory (model, tokenizer) pair."""

from copy import copy

from inspect_ai._util.registry import RegistryInfo, set_registry_info
from inspect_ai.model._model import ModelAPI
from inspect_ai.model._providers.hf import HuggingFaceAPI


class InMemoryHuggingFaceAPI(HuggingFaceAPI):
    """Inspect-AI HuggingFaceAPI which wraps a live model and tokenizer instead of loading one.

    Skips `HuggingFaceAPI.__init__` (which always calls `from_pretrained`).
    """

    def __init__(self, model, tokenizer, enable_thinking: bool):
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
