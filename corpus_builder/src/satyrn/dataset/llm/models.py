"""LLM backends: a provider-agnostic Model interface, providers, and a dispatcher."""

import json
import logging
import os
from abc import ABC, abstractmethod

import jsonschema
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

    def __init__(self, model_name: str, thinking: bool = False, reasoning_effort: str | None = None) -> None:
        self.model_name = model_name
        self.extra_body = {"thinking": {"type": "enabled" if thinking else "disabled"}}
        self.reasoning_effort = reasoning_effort
        self.client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

    def generate(self, prompt: str, context: Context) -> str | None:
        messages = [
            {"role": "system", "content": context.system_prompt},
            {"role": "user", "content": context.render(prompt)},
        ]
        create_kwargs = {"model": self.model_name, "messages": messages, "extra_body": self.extra_body}
        if self.reasoning_effort is not None:
            create_kwargs["reasoning_effort"] = self.reasoning_effort

        if not context.expect_json:
            response = self.client.chat.completions.create(**create_kwargs)
            return response.choices[0].message.content

        create_kwargs["response_format"] = {"type": "json_object"}
        max_attempts = 3
        for _ in range(max_attempts):
            response = self.client.chat.completions.create(**create_kwargs)
            content = response.choices[0].message.content
            try:
                parsed = json.loads(content)
                jsonschema.validate(parsed, context.json_schema)
                return parsed
            except (json.JSONDecodeError, jsonschema.ValidationError) as error:
                logger.warning("DeepSeek response did not match the schema: %s", error)
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {"role": "user", "content": f"That did not match the required schema: {error}. Try again."}
                )

        raise ValueError(f"DeepSeek did not return a schema-conforming response after {max_attempts} attempts")


def get_llm(provider: str, model_name: str, thinking: bool = False) -> Model:
    """Return a Model for provider backed by model_name."""
    if provider == "deepseek":
        return DeepSeekModel(model_name, thinking=thinking)
    raise ValueError(f"Unknown provider: {provider}")
