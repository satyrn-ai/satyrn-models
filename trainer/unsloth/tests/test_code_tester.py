"""Extracting the answer code from a completion that may contain thinking."""

from satyrn.trainer.unsloth.rl.code_tester import find_code


def test_skips_draft_block_in_thinking() -> None:
    """A fenced draft inside the thinking loses to the fenced block after it."""
    completion = "<think>\n```python\ndraft()\n```\n</think>\n\n```python\nfinal()\n```"
    assert find_code(completion) == "final()\n"


def test_unfenced_answer_after_thinking() -> None:
    """Without a fence, only the text after `</think>` is returned."""
    assert find_code("reasoning\n</think>\n\nfinal()") == "\n\nfinal()"


def test_unclosed_thinking_is_empty() -> None:
    """Thinking cut off before `</think>` yields no code."""
    assert find_code("<think>\n```python\ndraft()\n```") == ""
