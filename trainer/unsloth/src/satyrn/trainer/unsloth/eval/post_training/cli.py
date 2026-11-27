"""Entry point for the satyrn-model-eval CLI."""

import os
from typing import get_args

import click
import mlflow
from rich.console import Console
from rich.table import Table

from satyrn.trainer.unsloth.config import StageName
from satyrn.trainer.unsloth.eval.inspect_runner import log_eval_metrics, run_eval_suite
from satyrn.trainer.unsloth.eval.post_training.charts.tuning_run_chart import plot_tuning_run
from satyrn.trainer.unsloth.eval.post_training.checkpoint_order import next_checkpoint
from satyrn.trainer.unsloth.eval.post_training.tuning_run import (
    TuningRun,
    find_run_dir,
    load_run_data,
    load_scores,
)
from satyrn.trainer.unsloth.secrets import load_secrets


def percent(value: float | None) -> str:
    """Format a score as a percentage, blank when missing."""
    return "" if value is None else f"{value:.1%}"


def print_run_summary(run: TuningRun) -> None:
    """Print the stages of the run as a table."""
    peft = run.config.model.peft
    table = Table(
        title=f"[link={run.mlflow_url}]{run.config.run_name}[/link]\n"
        f"{run.config.model.name}, LoRA r {peft.r}, alpha {peft.lora_alpha}"
    )
    columns = (
        "Stage",
        "Learning rate",
        "Epochs",
        "Val loss / Reward",
        "Evaluated",
        "Best step",
        "HumanEval",
        "PythonEval",
        "Satyrn Score",
    )
    for column in columns:
        table.add_column(column)

    if run.pre_scores:
        table.add_row(
            "pre",
            *[""] * 5,
            percent(run.pre_scores.get("humaneval")),
            percent(run.pre_scores.get("python_eval")),
            percent(run.pre_scores.get("satyrn_score")),
        )

    for stage in run.stages:
        stage_config = getattr(run.config, stage.name)
        epochs = str(stage_config.num_train_epochs)
        if stage.checkpoints and stage.checkpoints[-1].state["epoch"] < stage_config.num_train_epochs:
            epochs = f"{stage.checkpoints[-1].state['epoch']:.1f}/{epochs}"

        metric = "reward" if stage.name == "rl" else "eval_loss"
        last_value = stage.checkpoints[-1].last_logged(metric) if stage.checkpoints else None

        scores = stage.satyrn_scores
        best_step = max(scores, key=lambda step: (scores[step], step), default=None)
        best = stage.find_checkpoint(best_step) if best_step is not None else None
        table.add_row(
            f"[link={stage.mlflow_url}]{stage.name}[/link]",
            f"{stage_config.learning_rate:g}",
            epochs,
            "" if last_value is None else f"{last_value:.4f}",
            f"{len(scores)}/{len(stage.checkpoints)}",
            "" if best_step is None else str(best_step),
            percent(best and best.scores["humaneval"]),
            percent(best and best.scores["python_eval"]),
            percent(best and best.scores["satyrn_score"]),
        )
    Console().print(table)


def update_chart(run: TuningRun) -> None:
    """Redraw the chart of the run and print where it is saved."""
    chart_path = run.run_dir / "tuning_run.png"
    plot_tuning_run(run, chart_path)
    click.echo(f"Chart updated: {chart_path}")


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

        load_scores(run)
        if not checkpoint.is_evaluated:
            raise click.ClickException(f"Evaluation of {stage.name} step {global_step} did not complete")
        log_eval_metrics(logs, step, mlflow_run_id)
        mlflow.log_metrics({"satyrn_score": checkpoint.scores["satyrn_score"]}, step=step, run_id=mlflow_run_id)
        click.echo(f"{stage.name} step {global_step}: Satyrn Score {percent(checkpoint.scores['satyrn_score'])}")
        update_chart(run)

        checkpoint = next_checkpoint(run)
    print_run_summary(run)


@click.command("satyrn-model-eval")
@click.argument("run_id", help="MLflow run id or run name")
def main(run_id: str) -> None:
    """Evaluate the checkpoints of the training run of the MLflow run RUN_ID."""
    run = load_run_data(find_run_dir(run_id))
    print_run_summary(run)
    evaluate_checkpoints(run)
    if run.has_scores:
        update_chart(run)
