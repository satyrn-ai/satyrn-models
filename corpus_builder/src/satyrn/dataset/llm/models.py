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
    def generate(self, prompt: str, context: Context, thinking: bool = False, effort: str = "medium") -> str | dict:
        """Return the model's response to a prompt rendered with the context.

        Args:
            prompt: The prompt text sent to the model.
            context: Bundles the system prompt, reference documents, and expected output shape.
            thinking: Enable extended thinking.
            effort: One of low, medium, high, xhigh, max.
        """


class DeepSeekModel(Model):
    """A Model backed by DeepSeek's API."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

    def generate(self, prompt: str, context: Context, thinking: bool = False, effort: str = "medium") -> str | dict:
        messages = [
            {"role": "system", "content": context.system_prompt},
            {"role": "user", "content": context.render(prompt)},
        ]
        create_kwargs = {"model": self.model_name, "messages": messages}
        if thinking:
            create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            create_kwargs["reasoning_effort"] = effort

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


def get_llm(provider: str, model_name: str) -> Model:
    """Return a Model for provider backed by model_name."""
    if provider == "deepseek":
        return DeepSeekModel(model_name)
    raise ValueError(f"Unknown provider: {provider}")
