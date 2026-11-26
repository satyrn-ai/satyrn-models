"""Unit test for SFT dataset line generation flow."""

from pathlib import Path

from satyrn.dataset import sft
from satyrn.dataset.llm.context import Context
from satyrn.dataset.utils.generation import Idea


class FakeModel:
    """Stub LLM recording prompts/schemas and returning canned responses for each stage."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def generate(self, prompt: str, context: Context, thinking: bool = False, effort: str = "medium") -> dict:
        self.calls.append((prompt, context.json_schema))
        required = set((context.json_schema or {}).get("required", []))
        if required == {"code", "expected_output"}:
            return {"code": "print(sentinel('X'))", "expected_output": "X\n"}
        if required == {"prompt", "explanation", "trace"}:
            return {
                "prompt": "How do I create a sentinel?",
                "explanation": "Use `sentinel('X')`.",
                "trace": "API info.\n\nI need to create a sentinel.\n\n1. Call `sentinel('X')`.",
            }
        return {"judgement": "Looks good.", "passed": True}


class FakeSandbox:
    """Stub sandbox returning fixed output per Python version."""

    def __init__(self, python_version: str, output: str) -> None:
        self.python_version = python_version
        self.output = output

    def run(self, code: str) -> str:
        return self.output


def test_build_dataset_line_generates_trace_in_conversation(tmp_path: Path) -> None:
    doc_path = tmp_path / "PEP661.rst"
    doc_path.write_text("PEP 661 sentinel documentation.", encoding="utf-8")
    idea = Idea(doc_path=doc_path, description="Create a sentinel.", python_version="3.15", kind="sft")
    model = FakeModel()
    sandbox = FakeSandbox("3.15", "X\n")
    predecessor_sandbox = FakeSandbox("3.14", "NameError: sentinel\n")

    row = sft.build_dataset_line(model, idea, sandbox, predecessor_sandbox)

    assert row is not None
    assert len(model.calls) == 3
    assert row["trace"] == "API info.\n\nI need to create a sentinel.\n\n1. Call `sentinel('X')`."
    assert row["completion"] == [
        {"role": "assistant", "content": "Use `sentinel('X')`.\n\n```python\nprint(sentinel('X'))\n```"}
    ]
    judge_prompt = model.calls[2][0]
    assert row["trace"] in judge_prompt
