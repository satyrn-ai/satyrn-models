"""Extracting the answer code from a completion that may contain thinking."""

from satyrn.trainer.unsloth.rl.code_tester import find_code, split_thinking


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


def test_split_thinking_extracts_reasoning_and_answer() -> None:
    """Return both thinking and answer for closed, prompt-prefixed, unclosed, and plain outputs."""
    assert split_thinking("<think>\nstep 1\n</think>\nfinal()") == ("step 1", "\nfinal()")
    assert split_thinking("step 1\n</think>\nfinal()") == ("step 1", "\nfinal()")
    assert split_thinking("<think>\ncut off") == ("cut off", "")
    assert split_thinking("final()") == ("", "final()")
