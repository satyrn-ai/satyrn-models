"""Smoke tests: the satyrn-unsloth CLI imports and its shipped configs validate."""

import sys
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir

from satyrn.trainer.unsloth.config import ExperimentConfig, validate_config
from satyrn.trainer.unsloth.run import CONFIG_DIR, main

EXPERIMENT_NAMES = sorted(path.stem for path in Path(CONFIG_DIR, "experiment").glob("*.yaml"))


def test_cli_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI prints its help and lists the config groups, starting no run."""
    monkeypatch.setattr(sys, "argv", ["satyrn-unsloth", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    help_output = capsys.readouterr().out
    assert "experiment: " in help_output
    assert "model: " in help_output


def test_config_dir_holds_the_shipped_configs() -> None:
    assert Path(CONFIG_DIR, "defaults.yaml").is_file()
    assert EXPERIMENT_NAMES


@pytest.mark.parametrize("experiment_name", EXPERIMENT_NAMES)
def test_experiment_config_validates(experiment_name: str) -> None:
    """Compose an experiment config and check it against the schema, without training."""
    with initialize_config_dir(config_dir=CONFIG_DIR):
        cfg = compose(config_name=f"experiment/{experiment_name}")

    config = validate_config(cfg)
    assert isinstance(config, ExperimentConfig)
    assert config.run_name
    assert config.model.name
