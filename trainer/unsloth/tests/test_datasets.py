"""Reading JSONL training data."""

from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer

from satyrn.trainer.unsloth.dataset_packing import pack_documents
from satyrn.trainer.unsloth.run import load_dataset, render_conversations_into_text_field


def test_reads_one_or_many_files(tmp_path: Path) -> None:
    """A lone path and a list of paths both load; the list concatenates in order."""
    first = tmp_path / "first.jsonl"
    first.write_text('{"text": "one"}\n{"text": "two"}\n')
    second = tmp_path / "second.jsonl"
    second.write_text('{"text": "three"}\n')

    assert list(load_dataset(str(first))["text"]) == ["one", "two"]
    assert list(load_dataset([str(first), str(second)])["text"]) == ["one", "two", "three"]


def test_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "padded.jsonl"
    path.write_text('\n{"text": "one"}\n\n{"text": "two"}\n\n')

    assert list(load_dataset(str(path))["text"]) == ["one", "two"]


def test_packed_sequences_fit_seq_len() -> None:
    """Sequences come back one token short of seq_len, leaving room for the trainer's EOS."""
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
    text = " ".join(f"token{index}" for index in range(2000))
    dataset = Dataset.from_list([{"text": text}])

    packed = pack_documents(dataset, tokenizer, 64)

    lengths = [len(tokenizer(sequence, add_special_tokens=False).input_ids) for sequence in packed["text"]]
    assert len(packed) > len(dataset)
    assert max(lengths) == 63


class RecordingTokenizer:
    """A tokenizer whose chat template call records its arguments and renders a fixed text."""

    def apply_chat_template(self, messages: list[dict], tools: list[dict] | None, tokenize: bool) -> str:
        self.messages = messages
        self.tools = tools
        return "rendered"


def test_render_passes_the_whole_session_and_the_tools() -> None:
    tool_call = {"id": "call_1", "function": {"name": "bash", "arguments": {"command": "ls"}}}
    prompt = [{"role": "user", "content": "List the files"}]
    completion = [
        {"role": "assistant", "content": None, "tool_calls": [tool_call]},
        {"role": "tool", "tool_call_id": "call_1", "content": "a.py"},
        {"role": "assistant", "content": "One file"},
    ]
    tools = [{"type": "function", "function": {"name": "bash"}}]
    tokenizer = RecordingTokenizer()

    dataset = render_conversations_into_text_field(
        [{"prompt": prompt, "completion": completion, "tools": tools}], tokenizer, enable_thinking=False
    )

    assert dataset["text"] == ["rendered"]
    assert tokenizer.messages == prompt + completion
    assert tokenizer.tools == tools


def test_render_attaches_the_trace_when_thinking() -> None:
    row = {"prompt": [], "completion": [{"role": "assistant", "content": "Answer"}], "trace": "Reasoning"}
    tokenizer = RecordingTokenizer()

    render_conversations_into_text_field([row], tokenizer, enable_thinking=True)

    assert tokenizer.messages == [{"role": "assistant", "content": "Answer", "reasoning_content": "Reasoning"}]
    assert tokenizer.tools is None


def test_render_keeps_inline_reasoning_only_when_thinking() -> None:
    completion = [{"role": "assistant", "content": "Answer", "reasoning_content": "Reasoning"}]
    row = {"prompt": [], "completion": completion}
    tokenizer = RecordingTokenizer()

    render_conversations_into_text_field([row], tokenizer, enable_thinking=True)
    assert tokenizer.messages == completion

    render_conversations_into_text_field([row], tokenizer, enable_thinking=False)
    assert tokenizer.messages == [{"role": "assistant", "content": "Answer"}]
