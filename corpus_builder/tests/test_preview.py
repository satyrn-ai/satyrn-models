"""Tests for printing dataset lines."""

import pytest

from satyrn.dataset.utils import preview


def test_print_messages_handles_tool_calls_and_tool_results(capsys: pytest.CaptureFixture[str]) -> None:
    messages = [
        {"role": "user", "content": "Fix render.py"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"function": {"name": "bash", "arguments": '{"command": "ls"}'}}],
        },
        {"role": "tool", "content": "[red]render.py[/red] # not markdown"},
        {"role": "assistant", "content": "Done"},
    ]

    preview.print_messages(messages)

    output = capsys.readouterr().out
    assert "bash" in output
    assert "[red]render.py[/red] # not markdown" in output
    assert "Done" in output
