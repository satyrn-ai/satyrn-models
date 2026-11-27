"""Entry point for the satyrn-model-eval CLI."""

import os
from typing import get_args

import click
import mlflow
from rich.console import Console
from rich.table import Table

from satyrn.trainer.unsloth.config import StageName
from satyrn.trainer.unsloth.eval.inspect_runner import log_eval_metrics, run_eval_suite
from satyrn.trainer.unsloth.eval.post_training.checkpoint_order import next_checkpoint
from satyrn.trainer.unsloth.eval.post_training.tuning_run import (
    TuningRun,
    find_run_dir,
    load_run_data,
    load_scores,
)
from satyrn.trainer.unsloth.secrets import load_secrets


def print_run_summary(run: TuningRun) -> None:
    """Print the stages of the run as a table."""
    peft = run.config.model.peft
    table = Table(
        title=f"[link={run.mlflow_url}]{run.config.run_name}[/link]\n"
        f"{run.config.model.name}, LoRA r {peft.r}, alpha {peft.lora_alpha}"
    )
    for column in ("Stage", "Learning rate", "Epochs", "Val loss / Reward", "Checkpoints"):
        table.add_column(column)

    for stage in run.stages:
        stage_config = getattr(run.config, stage.name)
        metric = "reward" if stage.name == "rl" else "eval_loss"
        last_value = stage.checkpoints[-1].last_logged(metric) if stage.checkpoints else None
        epochs = str(stage_config.num_train_epochs)
        if stage.checkpoints and stage.checkpoints[-1].state["epoch"] < stage_config.num_train_epochs:
            epochs = f"{stage.checkpoints[-1].state['epoch']:.1f}/{epochs}"
        table.add_row(
            f"[link={stage.mlflow_url}]{stage.name}[/link]",
            f"{stage_config.learning_rate:g}",
            epochs,
            "" if last_value is None else f"{last_value:.4f}",
            str(len(stage.checkpoints)),
        )
    Console().print(table)


def evaluate_checkpoints(run: TuningRun) -> None:
    """Evaluate the checkpoints of the run in the order of next_checkpoint until the search is done."""
    checkpoint = next_checkpoint(run)
    if checkpoint is None:
        return

    # Unsloth must be imported before transformers, which inspect_ai's HF provider imports
    from unsloth import FastVisionModel

    load_secrets()
    os.environ["INSPECT_LOG_DIR"] = str(run.run_dir / "evals")
    mlflow.set_tracking_uri(run.config.mlflow.tracking_uri)

    model, processor = FastVisionModel.from_pretrained(
        model_name=str(checkpoint.path),
        max_seq_length=run.config.max_seq_length,
        dtype=None,
        load_in_4bit=run.config.load_in_4bit,
    )
    model.generation_config.use_cache = True
    tokenizer = getattr(processor, "tokenizer", processor)

    while checkpoint is not None:
        stage = next(stage for stage in run.stages if checkpoint in stage.checkpoints)
        global_step = checkpoint.state["global_step"]
        is_last = checkpoint is stage.checkpoints[-1]
        if is_last:
            metadata = {"stage": stage.name}
            mlflow_run_url, step = run.mlflow_url, get_args(StageName).index(stage.name)
        else:
            metadata = {"stage": stage.name, "global_step": global_step}
            mlflow_run_url, step = stage.mlflow_url, global_step
        mlflow_run_id = mlflow_run_url.rsplit("/", 1)[1]

        model.load_adapter(str(checkpoint.path), adapter_name="checkpoint")
        model.set_adapter("checkpoint")
        logs = run_eval_suite(model, tokenizer, metadata)
        model.set_adapter("default")
        model.delete_adapter("checkpoint")

        load_scores(run.run_dir, run.stages)
        if not checkpoint.is_evaluated:
            raise click.ClickException(f"Evaluation of {stage.name} step {global_step} did not complete")
        log_eval_metrics(logs, step, mlflow_run_id)
        mlflow.log_metrics({"satyrn_score": checkpoint.scores["satyrn_score"]}, step=step, run_id=mlflow_run_id)
        click.echo(f"{stage.name} step {global_step}: satyrn_score {checkpoint.scores['satyrn_score']:.4f}")

        checkpoint = next_checkpoint(run)


@click.command("satyrn-model-eval")
@click.argument("run_id")
def main(run_id: str) -> None:
    """Evaluate the checkpoints of the training run of the MLflow run RUN_ID."""
    run = load_run_data(find_run_dir(run_id))
    print_run_summary(run)
    evaluate_checkpoints(run)
