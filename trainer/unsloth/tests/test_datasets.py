"""Reading JSONL training data."""

from pathlib import Path

from datasets import Dataset
from transformers import AutoTokenizer

from satyrn.trainer.unsloth.dataset_packing import pack_documents
from satyrn.trainer.unsloth.run import load_dataset


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
