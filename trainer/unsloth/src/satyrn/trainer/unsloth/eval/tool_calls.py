"""Parse tool calls from a raw completion in the native format of each model family we train.

inspect_ai's HuggingFace provider picks a parser by model name, and our in-memory model is always named
`huggingface-local`, so it falls back to a guess that only reads JSON inside `<tool_call>` tags. The families
in `configs/model` write three formats, each the inverse of what their chat template renders:

- JSON (Mellum):        <tool_call>\n{"name": "read", "arguments": {...}}\n</tool_call>
- XML (Qwen 3.6, Ornith): <tool_call>\n<function=read>\n<parameter=path>\na.py\n</parameter>\n</function>\n</tool_call>
- Gemma 4:              <|tool_call>call:read{path:<|"|>a.py<|"|>}<tool_call|>
"""

from __future__ import annotations

import json
import re
import uuid

from inspect_ai.tool import ToolCall

TAGGED = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
GEMMA = re.compile(r"<\|tool_call>call:([\w.-]+)(\{.*?\})<tool_call\|>", re.DOTALL)
XML_FUNCTION = re.compile(r"<function=([\w.-]+)>(.*?)</function>", re.DOTALL)
XML_PARAMETER = re.compile(r"<parameter=([\w.-]+)>\n?(.*?)\n?</parameter>", re.DOTALL)
GEMMA_STRING = re.compile(r'<\|"\|>(.*?)<\|"\|>', re.DOTALL)
GEMMA_KEY = re.compile(r"([{,])\s*([A-Za-z_][\w.-]*)\s*:")


def _call(function: str, arguments: dict | None, error: str | None = None) -> ToolCall:
    return ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", function=function, arguments=arguments or {}, parse_error=error)


def _xml_value(text: str) -> object:
    """A parameter value: structured values are rendered as JSON, anything else is a plain string."""
    if text[:1] in "[{":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def _tagged(body: str) -> ToolCall:
    body = body.strip()
    if function := XML_FUNCTION.search(body):
        params = {name: _xml_value(value) for name, value in XML_PARAMETER.findall(function.group(2))}
        return _call(function.group(1), params)
    try:
        data = json.loads(body)
        return _call(str(data["name"]), data.get("arguments") or {})
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        return _call("unknown", None, f"could not parse tool call: {error}")


def _gemma(name: str, body: str) -> ToolCall:
    """Gemma's arguments are a JSON-like map with bare keys and <|"|>-delimited strings."""
    strings: list[str] = []

    def stash(match: re.Match) -> str:
        strings.append(match.group(1))
        return f"\x00{len(strings) - 1}\x00"

    text = GEMMA_KEY.sub(r'\1"\2":', GEMMA_STRING.sub(stash, body))
    text = re.sub(r"\x00(\d+)\x00", lambda m: json.dumps(strings[int(m.group(1))]), text)
    try:
        return _call(name, json.loads(text))
    except json.JSONDecodeError as error:
        return _call(name, None, f"could not parse tool call arguments: {error}")


def parse_tool_calls(text: str) -> tuple[str, list[ToolCall]]:
    """The completion's text outside its tool calls, and the calls in the order written."""
    found = [(m.start(), m.end(), _tagged(m.group(1))) for m in TAGGED.finditer(text)]
    found += [(m.start(), m.end(), _gemma(m.group(1), m.group(2))) for m in GEMMA.finditer(text)]
    found.sort(key=lambda item: item[0])
    content, last = [], 0
    for start, end, _ in found:
        content.append(text[last:start])
        last = end
    content.append(text[last:])
    return "".join(content).strip(), [call for _start, _end, call in found]
