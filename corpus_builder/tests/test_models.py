"""Tests for the LLM backends, focused on the branch's error and config changes."""

from types import SimpleNamespace
from typing import Any

import pytest

from satyrn.dataset.llm import models
from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import DeepSeekModel, SchemaValidationError, get_llm


@pytest.fixture(autouse=True)
def _deepseek_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every model needs an API key in the environment to be constructed."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


class StubCompletions:
    """Return canned message contents in order, recording each call."""

    def __init__(self, contents: list[str]) -> None:
        self.contents = contents
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        content = self.contents[len(self.calls) - 1]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class StubClient:
    def __init__(self, contents: list[str]) -> None:
        self.chat = SimpleNamespace(completions=StubCompletions(contents))


def make_model(contents: list[str]) -> tuple[DeepSeekModel, StubClient]:
    """Build a DeepSeekModel whose API calls are served by a stub client."""
    model = DeepSeekModel("test-model")
    client = StubClient(contents)
    model.client = client  # type: ignore[assignment]
    return model, client


def json_context() -> Context:
    context = Context()
    context.set_json_schema(
        {
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": {"type": "string"}}},
            "required": ["ideas"],
        }
    )
    return context


def test_deepseek_model_reads_base_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test/v1")
    captured: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(models, "OpenAI", fake_openai)

    DeepSeekModel("test-model")

    assert captured["base_url"] == "https://example.test/v1"


def test_deepseek_model_defaults_base_url_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    captured: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(models, "OpenAI", fake_openai)

    DeepSeekModel("test-model")

    assert captured["base_url"] == "https://api.deepseek.com"


def test_generate_returns_parsed_json_on_first_attempt() -> None:
    model, client = make_model(['{"ideas": ["a", "b"]}'])

    result = model.generate("prompt", json_context())

    assert result == {"ideas": ["a", "b"]}
    assert len(client.chat.completions.calls) == 1
    assert client.chat.completions.calls[0]["response_format"] == {"type": "json_object"}


def test_generate_recovers_after_malformed_response() -> None:
    model, client = make_model(["not json", '{"ideas": ["recovered"]}'])

    result = model.generate("prompt", json_context())

    assert result == {"ideas": ["recovered"]}
    assert len(client.chat.completions.calls) == 2
    # The second call must include the failed attempt and retry instruction.
    follow_up = client.chat.completions.calls[1]["messages"]
    assert follow_up[-2] == {"role": "assistant", "content": "not json"}
    assert "did not match the required schema" in follow_up[-1]["content"]


def test_generate_raises_schema_validation_error_after_retries() -> None:
    model, client = make_model(["nope", "still bad", "{}"])

    with pytest.raises(SchemaValidationError):
        model.generate("prompt", json_context())

    assert len(client.chat.completions.calls) == 3


def test_generate_passes_thinking_options() -> None:
    model, client = make_model(['{"ideas": []}'])

    model.generate("prompt", json_context(), thinking=True, effort="high")

    call = client.chat.completions.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert call["reasoning_effort"] == "high"


def test_generate_returns_plain_text_without_schema() -> None:
    model, _ = make_model(["plain answer"])
    context = Context()
    context.system_prompt = "system"

    result = model.generate("prompt", context)

    assert result == "plain answer"


def test_get_llm_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        get_llm("nope", "model")
