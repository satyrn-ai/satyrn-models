"""Reading JSONL training data."""

from pathlib import Path

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
