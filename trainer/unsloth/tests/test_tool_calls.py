"""Parsing tool calls from raw completions in each trained model family's native format."""

import pytest

from satyrn.trainer.unsloth.eval.agent_eval.tool_calls import parse_tool_calls

EDIT_ARGS = {"path": "app.py", "edits": [{"oldText": "a = 1", "newText": "a = 2"}]}

# Each string is what the family's chat template renders for an assistant turn calling edit(**EDIT_ARGS)
JSON_STYLE = (  # Mellum
    'Fixing it.\n<tool_call>\n{"name": "edit", "arguments": '
    '{"path": "app.py", "edits": [{"oldText": "a = 1", "newText": "a = 2"}]}}\n</tool_call>'
)
XML_STYLE = (  # Qwen 3.6, Ornith
    "Fixing it.\n\n<tool_call>\n<function=edit>\n<parameter=path>\napp.py\n</parameter>\n"
    '<parameter=edits>\n[{"oldText": "a = 1", "newText": "a = 2"}]\n</parameter>\n</function>\n</tool_call>'
)
GEMMA_STYLE = (  # Gemma 4
    'Fixing it.<|tool_call>call:edit{edits:[{newText:<|"|>a = 2<|"|>,oldText:<|"|>a = 1<|"|>}],'
    'path:<|"|>app.py<|"|>}<tool_call|>'
)


@pytest.mark.parametrize("raw", [JSON_STYLE, XML_STYLE, GEMMA_STYLE], ids=["json", "xml", "gemma"])
def test_each_native_format_parses_to_the_same_call(raw: str) -> None:
    """The three formats carry the same call; the text before it stays as content."""
    content, calls = parse_tool_calls(raw)
    assert content == "Fixing it."
    assert [(c.function, c.arguments, c.parse_error) for c in calls] == [("edit", EDIT_ARGS, None)]


def test_gemma_strings_may_hold_commas_colons_and_braces() -> None:
    """Delimited strings are taken whole, so code inside them does not confuse the parser."""
    raw = '<|tool_call>call:write{content:<|"|>d = {"a": 1, "b": [2, 3]}\n<|"|>,path:<|"|>x.py<|"|>}<tool_call|>'
    _content, [call] = parse_tool_calls(raw)
    assert call.arguments == {"content": 'd = {"a": 1, "b": [2, 3]}\n', "path": "x.py"}


def test_several_calls_in_one_turn() -> None:
    """Every call in the turn is returned, in order."""
    raw = JSON_STYLE + '\n<tool_call>\n{"name": "read", "arguments": {"path": "b.py"}}\n</tool_call>'
    _content, calls = parse_tool_calls(raw)
    assert [c.function for c in calls] == ["edit", "read"]
    assert calls[0].id != calls[1].id


def test_broken_json_is_a_parse_error_not_a_crash() -> None:
    """A malformed call is reported as one call with parse_error set, so it counts as invalid."""
    _content, [call] = parse_tool_calls('<tool_call>\n{"name": "read", "arguments": {"path": }\n</tool_call>')
    assert call.parse_error


def test_plain_text_has_no_calls() -> None:
    """An answer without tool-call markup is just content."""
    assert parse_tool_calls("All done, the tests pass.") == ("All done, the tests pass.", [])


def test_xml_values_take_the_type_their_schema_declares() -> None:
    """XML parameters are bare text; the tool schema says whether `5` is a number or a string."""
    from inspect_ai.tool import ToolInfo, ToolParam, ToolParams

    params = ToolParams(
        properties={
            "path": ToolParam(type="string"),
            "offset": ToolParam(type="number"),
            "flag": ToolParam(type="boolean"),
            "edits": ToolParam(type="array"),
        }
    )
    tools = [ToolInfo(name="read", description="Read a file", parameters=params)]
    raw = (
        "<tool_call>\n<function=read>\n<parameter=path>\n5\n</parameter>\n<parameter=offset>\n5\n</parameter>\n"
        "<parameter=flag>\ntrue\n</parameter>\n<parameter=edits>\n[1]\n</parameter>\n"
        "<parameter=extra>\n7\n</parameter>\n</function>\n</tool_call>"
    )
    _content, [call] = parse_tool_calls(raw, tools)
    assert call.arguments == {"path": "5", "offset": 5, "flag": True, "edits": [1], "extra": "7"}


def test_an_xml_value_that_is_not_its_declared_type_stays_text() -> None:
    """A value that does not parse stays text, so schema validation reports it rather than the parser guessing."""
    from inspect_ai.tool import ToolInfo, ToolParam, ToolParams

    tools = [
        ToolInfo(name="read", description="", parameters=ToolParams(properties={"offset": ToolParam(type="number")}))
    ]
    raw = "<tool_call>\n<function=read>\n<parameter=offset>\ntwo\n</parameter>\n</function>\n</tool_call>"
    assert parse_tool_calls(raw, tools)[1][0].arguments == {"offset": "two"}
