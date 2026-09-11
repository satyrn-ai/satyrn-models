"""Tests for the Michał-format transformer."""

import json
from pathlib import Path

from click.testing import CliRunner

from satyrn.tstrings.transform import main, to_michal_sft

_ROW = {
    "prompt": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "Q"}],
    "completion": [{"role": "assistant", "content": "```python\nx = 1\n```"}],
    "filename": "Lib/test/x.py",
    "python_version": "3.14",
    "idea": "Q",
    "code": "x = 1",
    "trace": "I think...",
    "expected_output": "1",
    "_line": 7,
    "semantic_id": "abc",
}


def test_to_michal_sft_default_shape() -> None:
    """A converged row maps to Michał's shape without the system prompt."""
    out = to_michal_sft([_ROW])
    row = out[0]
    assert row["prompt"] == [{"role": "user", "content": "Q"}]
    assert row["completion"] == [{"role": "assistant", "content": "```python\nx = 1\n```"}]
    assert row["filename"] == "Lib/test/x.py" and row["python_version"] == "3.14"
    assert row["idea"] == "Q" and row["code"] == "x = 1"
    assert row["trace"] == "I think..." and row["expected_output"] == "1"
    assert "_line" not in row and "semantic_id" not in row


def test_to_michal_sft_with_system_prompt() -> None:
    """The system-prompt flag prepends the system entry."""
    out = to_michal_sft([_ROW], system_prompt="SYS")
    assert out[0]["prompt"][0] == {"role": "system", "content": "SYS"}


def test_to_michal_cli_reads_dir(tmp_path: Path) -> None:
    """The CLI reads a corpus-sft dir and writes one row per line."""
    corpus = tmp_path / "corpus-sft"
    corpus.mkdir()
    (corpus / "train.jsonl").write_text(json.dumps(_ROW) + "\n")
    (corpus / "valid.jsonl").write_text(json.dumps({**_ROW, "idea": "Q2"}) + "\n")
    out = tmp_path / "out.jsonl"
    result = CliRunner().invoke(main, ["-i", str(corpus), "-o", str(out)])
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["idea"] == "Q" and rows[1]["idea"] == "Q2"
