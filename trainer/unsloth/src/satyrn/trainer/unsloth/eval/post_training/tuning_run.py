"""Finished training runs, read from their results/ directory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import click
from inspect_ai.log import read_eval_log
from omegaconf import OmegaConf

from satyrn.trainer.unsloth.config import ExperimentConfig, StageName, validate_config
from satyrn.trainer.unsloth.eval.score import satyrn_models_score

MLFLOW_RUN_LINE = re.compile(r"🏃 View run (\S+) at: (\S+)")


@dataclass
class Checkpoint:
    path: Path
    state: dict[str, Any]
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def is_evaluated(self) -> bool:
        """Return whether the checkpoint has a satyrn_score."""
        return "satyrn_score" in self.scores

    def last_logged(self, key: str) -> float | None:
        """Return the last value of key in the training log."""
        values = [entry[key] for entry in self.state["log_history"] if key in entry]
        return values[-1] if values else None


@dataclass
class Stage:
    name: StageName
    mlflow_url: str
    checkpoints: list[Checkpoint]

    @property
    def satyrn_scores(self) -> dict[int, float]:
        """Return the satyrn_score of each evaluated checkpoint by its global step."""
        return {
            checkpoint.state["global_step"]: checkpoint.scores["satyrn_score"]
            for checkpoint in self.checkpoints
            if checkpoint.is_evaluated
        }

    @property
    def best_score(self) -> float:
        """Return the highest satyrn_score of the stage."""
        return max(self.satyrn_scores.values())

    def find_checkpoint(self, global_step: int | None) -> Checkpoint | None:
        """Return the stage's checkpoint saved at global_step, or its last one when global_step is None."""
        if global_step is None:
            return self.checkpoints[-1] if self.checkpoints else None
        return next(
            (checkpoint for checkpoint in self.checkpoints if checkpoint.state["global_step"] == global_step), None
        )


@dataclass
class TuningRun:
    run_dir: Path
    config: ExperimentConfig
    mlflow_url: str
    stages: list[Stage]
    pre_scores: dict[str, float] = field(default_factory=dict)

    @property
    def has_scores(self) -> bool:
        """Return whether the untrained model or any checkpoint has been evaluated."""
        return bool(self.pre_scores) or any(
            checkpoint.is_evaluated for stage in self.stages for checkpoint in stage.checkpoints
        )


def mlflow_run_urls(run_dir: Path) -> dict[str, str]:
    """Return the MLflow run URLs in run.log by run name."""
    return dict(MLFLOW_RUN_LINE.findall((run_dir / "run.log").read_text()))


def find_run_dir(run_id: str) -> Path:
    """Return the run directory of the MLflow run matching run_id."""
    for run_log in sorted(Path("results").glob("*/run.log"), reverse=True):
        run_dir = run_log.parent
        for name, url in mlflow_run_urls(run_dir).items():
            if name == run_id or url.rsplit("/", 1)[1].startswith(run_id):
                return run_dir
    raise click.ClickException(f"No run directory for MLflow run {run_id}")


def load_checkpoint(path: Path) -> Checkpoint:
    return Checkpoint(path, json.loads((path / "trainer_state.json").read_text()))


def load_scores(run: TuningRun) -> None:
    """Fill the scores of the model from the eval logs of the run."""
    stages_by_name = {stage.name: stage for stage in run.stages}

    for log_path in sorted((run.run_dir / "evals").glob("*.eval")):
        log = read_eval_log(str(log_path), header_only=True)
        if log.status != "success":
            continue

        metadata = log.eval.metadata or {}
        stage_name = metadata.get("stage")
        stage = stages_by_name.get(stage_name)
        checkpoint = stage.find_checkpoint(metadata.get("global_step")) if stage else None

        # Add untrained model scores from the "pre" stage
        if stage_name == "pre":
            scores = run.pre_scores
        elif checkpoint:
            scores = checkpoint.scores
        else:
            continue

        scores[log.eval.task_display_name] = log.results.scores[0].metrics["accuracy"].value
        if {"humaneval", "python_eval"} <= scores.keys():
            scores["satyrn_score"] = satyrn_models_score(scores["python_eval"], scores["humaneval"])


def load_run_data(run_dir: Path) -> TuningRun:
    """Load a training run from its run directory."""
    config = validate_config(OmegaConf.load(run_dir / ".hydra" / "config.yaml"))
    urls = mlflow_run_urls(run_dir)
    stages = []
    for run_name, url in urls.items():
        stage_name = run_name.split("-")[0]
        if run_name != config.run_name and stage_name in get_args(StageName):
            checkpoint_paths = (run_dir / "checkpoints" / stage_name).glob("checkpoint-*")
            checkpoints = [load_checkpoint(path) for path in checkpoint_paths]
            checkpoints.sort(key=lambda checkpoint: checkpoint.state["global_step"])
            stages.append(Stage(stage_name, url, checkpoints))
    run = TuningRun(run_dir, config, urls[config.run_name], stages)
    load_scores(run)
    return run
