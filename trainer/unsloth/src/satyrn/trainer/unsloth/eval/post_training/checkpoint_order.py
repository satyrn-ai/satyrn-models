"""Order in which a training run's checkpoints are evaluated."""

from itertools import pairwise
from operator import attrgetter

from satyrn.trainer.unsloth.eval.post_training.tuning_run import Checkpoint, Stage, TuningRun


def middle_checkpoint(stage: Stage) -> Checkpoint | None:
    """Return the middle checkpoint of the evaluated pair with the best total score and checkpoints between."""
    scores = stage.satyrn_scores
    steps = [checkpoint.state["global_step"] for checkpoint in stage.checkpoints]
    evaluated = [index for index, step in enumerate(steps) if step in scores]
    gaps = [(left, right) for left, right in pairwise(evaluated) if right - left > 1]
    best = max(gaps, key=lambda gap: (scores[steps[gap[0]]] + scores[steps[gap[1]]], gap), default=None)
    return stage.checkpoints[(best[0] + best[1] + 1) // 2] if best else None


def next_checkpoint(run: TuningRun) -> Checkpoint | None:
    """Return the next checkpoint to evaluate, or None when the search is done."""
    stages = [stage for stage in run.stages if stage.checkpoints]
    last_checkpoints = [stage.checkpoints[-1] for stage in reversed(stages)]
    first_checkpoints = [stage.checkpoints[0] for stage in reversed(stages)]
    unevaluated = [checkpoint for checkpoint in last_checkpoints + first_checkpoints if not checkpoint.is_evaluated]
    if unevaluated:
        return unevaluated[0]
    best_first = sorted(stages, key=attrgetter("best_score"))[::-1]
    return next(filter(None, map(middle_checkpoint, best_first)), None)
