"""LLM backends: a provider-agnostic Model interface, providers, and a dispatcher."""

import json
import logging
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from openai import OpenAI

from satyrn.dataset.llm.context import Context

load_dotenv()

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class Model(ABC):
    """LLM backend base class."""

    @abstractmethod
    def generate(self, prompt: str, context: Context) -> str | dict:
        """Return the model's response to a prompt rendered with the context."""


class DeepSeekModel(Model):
    """A Model backed by DeepSeek's API."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

    def generate(self, prompt: str, context: Context) -> str | dict:
        messages = [
            {"role": "system", "content": context.system_prompt},
            {"role": "user", "content": context.render(prompt)},
        ]
        if not context.expect_json:
            response = self.client.chat.completions.create(model=self.model_name, messages=messages)
            return response.choices[0].message.content

        max_attempts = 3
        for _ in range(max_attempts):
            response = self.client.chat.completions.create(
                model=self.model_name, messages=messages, response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            try:
                return json.loads(content)
            except json.JSONDecodeError as error:
                logger.warning("DeepSeek response was not valid JSON: %s", error)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"That was not valid JSON: {error}. Try again."})

        raise ValueError(f"DeepSeek did not return valid JSON after {max_attempts} attempts")


def get_llm(provider: str, model_name: str) -> Model:
    """Return a Model for provider backed by model_name."""
    if provider == "deepseek":
        return DeepSeekModel(model_name)
    raise ValueError(f"Unknown provider: {provider}")
