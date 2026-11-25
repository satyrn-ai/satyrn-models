"""Preserving thinking in `ContentReasoning` without affecting `humaneval` scoring."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import inspect_ai
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import (
    ChatMessageUser,
    ContentReasoning,
    ContentText,
    GenerateConfig,
    Model,
    ModelName,
    ModelOutput,
)
from inspect_ai.model._providers.hf import HuggingFaceAPI
from inspect_ai.scorer import CORRECT, Target
from inspect_ai.solver import TaskState, generate
from inspect_ai.util import ExecResult
from inspect_evals.humaneval.humaneval import verify

from satyrn.trainer.unsloth.eval.inspect_api import InMemoryHuggingFaceAPI


def stub_api_and_sandbox(monkeypatch) -> tuple[InMemoryHuggingFaceAPI, list[list[str]]]:
    """Return an `InMemoryHuggingFaceAPI` with mocked generation and a captured `humaneval` sandbox."""
    raw_completion = (
        "<think>\n```python\ndef add(a, b):\n    return a - b\n```\n</think>"
        "\n\n```python\ndef add(a, b):\n    return a + b\n```"
    )
    raw_output = ModelOutput.from_content("huggingface-local", raw_completion)
    monkeypatch.setattr(HuggingFaceAPI, "generate", AsyncMock(return_value=raw_output))

    tokenizer = MagicMock()
    tokenizer.pad_token = "<pad>"
    api = InMemoryHuggingFaceAPI(MagicMock(), tokenizer, enable_thinking=True)

    executed_commands: list[list[str]] = []

    async def fake_exec(cmd: list[str], timeout: int) -> ExecResult:
        executed_commands.append(cmd)
        return ExecResult(True, 0, "", "")

    humaneval_module = importlib.import_module("inspect_evals.humaneval.humaneval")
    fake_sandbox = MagicMock()
    fake_sandbox.exec = fake_exec
    monkeypatch.setattr(humaneval_module, "sandbox", lambda: fake_sandbox)
    return api, executed_commands


def assert_thinking_preserved_and_answer_scored(
    output: ModelOutput,
    score_value: object,
    score_answer: str | None,
    executed_commands: list[list[str]],
) -> None:
    """Assert `ContentReasoning` and `ContentText` are preserved while only the answer is scored."""
    content = output.choices[0].message.content
    assert isinstance(content, list)
    assert isinstance(content[0], ContentReasoning)
    assert "return a - b" in content[0].reasoning
    assert isinstance(content[1], ContentText)
    assert "return a + b" in content[1].text
    assert "<think>" not in output.completion

    assert score_value == CORRECT
    assert score_answer == "    return a + b\n"
    assert len(executed_commands) == 1
    assert "return a + b" in executed_commands[0][2]
    assert "return a - b" not in executed_commands[0][2]


def test_humaneval_verify_ignores_preserved_thinking(monkeypatch) -> None:
    """`InMemoryHuggingFaceAPI.generate` keeps `ContentReasoning` while `humaneval.verify` scores only the answer."""
    api, executed_commands = stub_api_and_sandbox(monkeypatch)
    prompt = [ChatMessageUser(content="Write add(a, b)")]

    output = asyncio.run(api.generate(prompt, [], "auto", GenerateConfig()))

    state = TaskState(
        model=ModelName("huggingface-local/huggingface-local"),
        sample_id="HumanEval/add",
        epoch=1,
        input="Write add(a, b)",
        messages=prompt,
        output=output,
        metadata={
            "prompt": "def add(a, b):\n",
            "test": "def check(fn):\n    assert fn(1, 2) == 3\n",
            "entry_point": "add",
        },
    )
    scorer = verify()
    score = asyncio.run(scorer(state, Target("")))
    assert_thinking_preserved_and_answer_scored(output, score.value, score.answer, executed_commands)


def test_eval_log_roundtrip_preserves_thinking_for_humaneval(monkeypatch, tmp_path: Path) -> None:
    """`inspect_ai.eval` scores the stripped answer and persists `ContentReasoning` into the `.eval` log."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg_cache"))
    api, executed_commands = stub_api_and_sandbox(monkeypatch)
    sample = Sample(
        id="HumanEval/add",
        input="Write add(a, b)",
        target="",
        metadata={
            "prompt": "def add(a, b):\n",
            "test": "def check(fn):\n    assert fn(1, 2) == 3\n",
            "entry_point": "add",
        },
    )
    task = Task(dataset=[sample], solver=generate(), scorer=verify())
    model = Model(api, GenerateConfig())

    logs = inspect_ai.eval(task, model=model, log_dir=str(tmp_path), display="plain")
    reloaded = read_eval_log(logs[0].location)
    logged_sample = reloaded.samples[0]
    score = logged_sample.scores["verify"]

    assert_thinking_preserved_and_answer_scored(logged_sample.output, score.value, score.answer, executed_commands)


def test_tool_calls_are_parsed_from_the_raw_completion(monkeypatch) -> None:
    """With tools, the template still renders them, but the calls come from our parser, not inspect's."""
    from inspect_ai.tool import ToolInfo, ToolParams

    raw = (
        '<think>\nplan\n</think>\nReading.\n<tool_call>\n{"name": "read", "arguments": {"path": "a.py"}}\n</tool_call>'
    )
    seen_tools = []
    monkeypatch.setattr(
        HuggingFaceAPI, "generate", AsyncMock(return_value=ModelOutput.from_content("huggingface-local", raw))
    )
    monkeypatch.setattr(HuggingFaceAPI, "hf_chat", lambda self, messages, tools: seen_tools.append(tools) or "")
    tokenizer = MagicMock()
    tokenizer.pad_token = "<pad>"
    api = InMemoryHuggingFaceAPI(MagicMock(), tokenizer, enable_thinking=True)
    tools = [ToolInfo(name="read", description="Read a file", parameters=ToolParams())]

    output = asyncio.run(api.generate([ChatMessageUser(content="hi")], tools, "auto", GenerateConfig()))

    assert HuggingFaceAPI.generate.call_args.args[1] == []  # inspect's own parser never runs
    api.hf_chat([ChatMessageUser(content="hi")], [])
    message = output.choices[0].message
    assert [(c.function, c.arguments) for c in message.tool_calls] == [("read", {"path": "a.py"})]
    assert message.text == "Reading."
    assert output.completion == "Reading."


# The part of Qwen3.8's chat template that renders earlier tool calls, including its check for a name
TOOL_CALL_TEMPLATE = (
    "{%- for message in messages %}{%- for tool_call in message.tool_calls or [] %}"
    "{%- if tool_call.function is defined %}{%- set tool_call = tool_call.function %}{%- endif %}"
    "{%- if tool_call.name is not defined or tool_call.name is none %}"
    "{{- raise_exception('Tool call is missing a function name.') }}{%- endif %}"
    "<function={{ tool_call.name }}>{%- for key, value in tool_call.arguments | items %}"
    "<parameter={{ key }}>{{ value }}</parameter>{%- endfor %}</function>"
    "{%- endfor %}{%- endfor %}"
)


def render_tool_calls(conversation: list[dict], *args, **kwargs) -> str:
    """Render as `apply_chat_template` does, with transformers' own compiled (sandboxed) template."""
    from transformers.utils.chat_template_utils import _compile_jinja_template

    return _compile_jinja_template(TOOL_CALL_TEMPLATE).render(messages=conversation)


def test_earlier_tool_calls_render_through_the_chat_template() -> None:
    """The second agent turn re-renders the first turn's tool call; the template must find its name."""
    import jinja2
    import pytest
    from inspect_ai.model import ChatMessageAssistant, ChatMessageTool
    from inspect_ai.tool import ToolCall, ToolInfo, ToolParams

    tokenizer = MagicMock()
    tokenizer.pad_token = "<pad>"
    tokenizer.apply_chat_template = render_tool_calls
    api = InMemoryHuggingFaceAPI(MagicMock(), tokenizer, enable_thinking=False)
    call = ToolCall(id="call_1", function="bash", arguments={"command": "ls"})
    messages = [
        ChatMessageUser(content="List the files."),
        ChatMessageAssistant(content="", tool_calls=[call]),
        ChatMessageTool(content="a.py", tool_call_id="call_1", function="bash"),
    ]
    tools = [ToolInfo(name="bash", description="Run a command", parameters=ToolParams())]

    assert api.hf_chat(messages, tools) == "<function=bash><parameter=command>ls</parameter></function>"
    with pytest.raises(jinja2.exceptions.TemplateError, match="missing a function name"):
        render_tool_calls([message.model_dump(exclude_none=True) for message in messages])  # inspect's own form
