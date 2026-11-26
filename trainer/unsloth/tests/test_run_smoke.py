"""Smoke tests: the satyrn-unsloth CLI imports and its shipped configs validate."""

import sys
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir

from satyrn.trainer.unsloth.config import (
    ExperimentConfig,
    SftStageConfig,
    calculate_eval_steps,
    is_evaluated,
    validate_config,
)
from satyrn.trainer.unsloth.run import CONFIG_DIR, main

EXPERIMENT_NAMES = sorted(path.stem for path in Path(CONFIG_DIR, "experiment").glob("*.yaml"))
MODEL_NAMES = sorted(path.stem for path in Path(CONFIG_DIR, "model").glob("*.yaml"))


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
    assert MODEL_NAMES


@pytest.mark.parametrize("experiment_name", EXPERIMENT_NAMES)
def test_experiment_config_validates(experiment_name: str) -> None:
    """Compose an experiment config and check it against the schema, without training."""
    with initialize_config_dir(config_dir=CONFIG_DIR):
        cfg = compose(config_name=f"experiment/{experiment_name}")

    config = validate_config(cfg)
    assert isinstance(config, ExperimentConfig)
    assert config.run_name
    assert config.model.name


@pytest.mark.parametrize("model_name", MODEL_NAMES)
def test_model_config_validates(model_name: str) -> None:
    """Compose each model config against an experiment and check it against the schema."""
    with initialize_config_dir(config_dir=CONFIG_DIR):
        cfg = compose(config_name="experiment/py3.15", overrides=[f"model={model_name}"])

    config = validate_config(cfg)
    assert config.model.name
    assert config.model.peft.r > 0


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ([], {"pre": True, "cpt": False, "sft": True, "rl": True}),
        (["pre_model_eval=false"], {"pre": False, "cpt": False, "sft": True, "rl": True}),
        (["eval_stages=[cpt]"], {"pre": False, "cpt": True, "sft": False, "rl": False}),
        (["eval_stages=[]"], {"pre": False, "cpt": False, "sft": False, "rl": False}),
    ],
)
def test_is_evaluated(overrides: list[str], expected: dict[str, bool]) -> None:
    with initialize_config_dir(config_dir=CONFIG_DIR):
        cfg = compose(config_name="experiment/py3.15", overrides=overrides)

    config = validate_config(cfg)
    assert {stage: is_evaluated(config, stage) for stage in expected} == expected


def test_null_eval_steps_validates() -> None:
    """Both CPT and SFT accept eval_steps=null."""
    with initialize_config_dir(config_dir=CONFIG_DIR):
        cfg = compose(config_name="experiment/py3.15", overrides=["cpt.eval_steps=null", "sft.eval_steps=null"])

    config = validate_config(cfg)
    assert config.cpt.eval_steps is None
    assert config.sft.eval_steps is None


@pytest.mark.parametrize(
    ("train_row_count", "batch_size", "gradient_accumulation_steps", "num_train_epochs", "max_steps", "expected"),
    [
        (251, 8, 2, 3, -1, 5),
        (2844, 48, 1, 1, -1, 5),
        (274, 8, 1, 3, -1, 10),
        (4556, 24, 1, 1, -1, 15),
        (1412, 6, 1, 1, -1, 20),
        (5968, 5, 4, 1, -1, 25),
        (5968, 5, 4, 2, -1, 50),
        (5968, 5, 4, 2, 105, 10),
        (10, 8, 1, 1, -1, 5),
    ],
)
def test_calculate_eval_steps(
    train_row_count: int,
    batch_size: int,
    gradient_accumulation_steps: int,
    num_train_epochs: int,
    max_steps: int,
    expected: int,
) -> None:
    """calculate_eval_steps returns the smallest multiple of 5 giving at most 12 validation passes."""
    stage = SftStageConfig(
        seq_len=4096,
        batch_size=batch_size,
        eval_batch_size=1,
        eval_steps=None,
        gradient_accumulation_steps=gradient_accumulation_steps,
        num_train_epochs=num_train_epochs,
        learning_rate=1e-4,
    )

    assert calculate_eval_steps(train_row_count, stage, max_steps) == expected
