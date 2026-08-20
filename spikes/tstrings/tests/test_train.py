"""Tests for the LoRA training command."""

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from satyrn.tstrings.train import main

_CONVERGED_ROW = json.dumps(
    {
        "prompt": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
        ],
        "completion": [{"role": "assistant", "content": "a"}],
    }
)


def test_train_command_invokes_mlx_lm_lora(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The train command delegates to mlx_lm.lora.main with the right args."""
    captured: dict[str, object] = {}

    def fake_main() -> None:
        captured["argv"] = sys.argv[:]

    monkeypatch.setattr("mlx_lm.lora.main", fake_main)
    train_data = tmp_path / "train.jsonl"
    train_data.write_text(_CONVERGED_ROW + "\n")

    result = CliRunner().invoke(
        main,
        ["-i", str(train_data), "-o", str(tmp_path / "adapters"), "--seed", "3", "--iters", "150"],
    )
    assert result.exit_code == 0, result.output
    argv = captured["argv"]
    assert argv[0] == "mlx_lm.lora"
    assert "--model" in argv and "jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit" in argv
    assert "--train" in argv and str(tmp_path / "adapters" / "train.mlxlm.jsonl") in argv
    assert "--seed" in argv and "3" in argv
    assert "--iters" in argv and "150" in argv
    assert str(tmp_path / "adapters" / "seed3" / "adapters.safetensors") in argv


def test_train_command_restores_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """sys.argv is restored after the command runs."""
    monkeypatch.setattr("mlx_lm.lora.main", lambda: None)
    train_data = tmp_path / "train.jsonl"
    train_data.write_text(_CONVERGED_ROW + "\n")
    before = sys.argv[:]
    result = CliRunner().invoke(main, ["-i", str(train_data), "--seed", "1"])
    assert result.exit_code == 0
    assert sys.argv == before


def test_to_mlxlm_messages_converts_rows(tmp_path: Path) -> None:
    """Converged rows convert to mlx-lm's messages chat format."""
    from satyrn.tstrings.train import to_mlxlm_messages

    src = tmp_path / "train.jsonl"
    src.write_text(
        json.dumps(
            {
                "prompt": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "q"},
                ],
                "completion": [{"role": "assistant", "content": "a"}],
            }
        )
        + "\n"
    )
    out = to_mlxlm_messages(src, tmp_path / "out")
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert rows == [
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ]
        }
    ]
