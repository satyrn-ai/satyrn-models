"""Chart of the scores and validation loss of a tuning run."""

from pathlib import Path

import pandas
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from satyrn.trainer.unsloth.eval.post_training.charts.theme import (
    BACKGROUND,
    BAND_TINTS,
    GRID,
    LOSS_GRAY,
    MUTED,
    PALETTE,
    TEXT,
    add_logo,
    style_axes,
)
from satyrn.trainer.unsloth.eval.post_training.tuning_run import TuningRun


def plot_tuning_run(run: TuningRun, path: Path) -> None:
    """Save a chart of the run's scores and validation loss by checkpoint to path."""
    # One row per model: the untrained one, then the checkpoints of each stage
    rows = [{"stage": "pre", **run.pre_scores}] if run.pre_scores else []
    for stage in run.stages:
        for checkpoint in stage.checkpoints:
            rows.append({"stage": stage.name, **checkpoint.scores, "val_loss": checkpoint.last_logged("eval_loss")})
    score_columns = ["humaneval", "python_eval", "satyrn_score"]
    models = pandas.DataFrame(rows, columns=["stage", *score_columns, "val_loss"])

    figure = Figure(figsize=(12, 6), facecolor=BACKGROUND)
    score_axis = figure.add_subplot()
    loss_axis = score_axis.twinx()
    style_axes(score_axis, loss_axis)
    score_axis.set_facecolor(BACKGROUND)

    for index, (stage_name, stage_models) in enumerate(models.groupby("stage", sort=False)):
        first, last = stage_models.index.min(), stage_models.index.max()
        score_axis.axvspan(first - 0.5, last + 0.5, color=BAND_TINTS[index % 2], zorder=0)
        if index:
            score_axis.axvline(first - 0.5, color=GRID, linewidth=1, zorder=1)
        score_axis.text(
            (first + last) / 2,
            0.965,
            stage_name.upper(),
            color=MUTED,
            fontsize=11,
            fontweight="bold",
            ha="center",
            va="top",
            transform=score_axis.get_xaxis_transform(),
        )

        # One segment per stage, so the loss does not connect across stages
        losses = stage_models["val_loss"].dropna()
        if not losses.empty:
            label = None if loss_axis.lines else "Validation loss"
            loss_axis.plot(losses.index, losses, color=LOSS_GRAY, linewidth=1.6, linestyle="--", label=label, zorder=2)

    column_labels = {"humaneval": "HumanEval", "python_eval": "PythonEval", "satyrn_score": "Satyrn Score"}
    for index, column in enumerate(score_columns):
        scores = models[column].dropna()
        score_axis.plot(
            scores.index,
            scores,
            color=PALETTE[index],
            linewidth=2,
            marker="o",
            markersize=4,
            label=column_labels[column],
            zorder=3,
        )

    # Rail along the bottom: evaluated checkpoints bright, pending ones faint
    is_evaluated = models["satyrn_score"].notna()
    for evaluated, color in ((True, MUTED), (False, GRID)):
        xs = models.index[is_evaluated == evaluated]
        score_axis.scatter(
            xs, [0.025] * len(xs), marker="|", s=60, color=color, transform=score_axis.get_xaxis_transform(), zorder=2
        )

    score_axis.set_ylim(0, 1)
    score_axis.set_xlim(-0.5, len(models) - 0.5)
    score_axis.set_xticks([])
    score_axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    score_axis.grid(axis="y", color=GRID, linewidth=0.8)
    score_axis.set_axisbelow(True)

    score_axis.set_title(run.config.run_name, color=TEXT, loc="left", pad=24, fontsize=14)
    score_axis.set_ylabel("Score", color=TEXT, labelpad=16)
    loss_axis.set_ylabel("Validation loss", color=LOSS_GRAY, labelpad=20)
    loss_axis.tick_params(axis="y", colors=LOSS_GRAY)
    loss_axis.set_visible(bool(loss_axis.lines))

    score_handles, score_labels = score_axis.get_legend_handles_labels()
    loss_handles, loss_labels = loss_axis.get_legend_handles_labels()
    handles = score_handles + loss_handles
    score_axis.legend(
        handles,
        score_labels + loss_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=max(len(handles), 1),
        labelcolor="linecolor",
        borderpad=1.0,
        handletextpad=0.6,
        columnspacing=2.0,
        facecolor=BACKGROUND,
        framealpha=0.75,
        edgecolor=GRID,
    )

    figure.tight_layout(pad=3)
    add_logo(figure)
    temporary_path = path.with_suffix(".tmp.png")
    figure.savefig(temporary_path, dpi=150, facecolor=BACKGROUND)
    temporary_path.replace(path)
