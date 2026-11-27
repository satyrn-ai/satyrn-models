from pathlib import Path
from types import SimpleNamespace

from satyrn.trainer.unsloth.eval.post_training.checkpoint_order import next_checkpoint
from satyrn.trainer.unsloth.eval.post_training.tuning_run import Checkpoint, Stage


def make_stage(name: str, scores: dict[int, float | None]) -> Stage:
    """Build a stage with a checkpoint per step; steps scored None are not evaluated."""
    checkpoints = [
        Checkpoint(Path(f"{name}-{step}"), {"global_step": step}, {} if score is None else {"satyrn_score": score})
        for step, score in scores.items()
    ]
    return Stage(name, "", checkpoints)


def test_search_order_visits_best_stage_first():
    cpt = make_stage("cpt", dict.fromkeys([5, 10, 15, 20, 25]))
    sft = make_stage("sft", dict.fromkeys([5, 10, 15, 20]))
    run = SimpleNamespace(stages=[cpt, sft])
    scores = {
        "cpt-5": 0.30,
        "cpt-10": 0.35,
        "cpt-15": 0.40,
        "cpt-20": 0.42,
        "cpt-25": 0.41,
        "sft-5": 0.38,
        "sft-10": 0.45,
        "sft-15": 0.50,
        "sft-20": 0.48,
    }

    order = []
    for _ in range(len(scores) + 1):
        checkpoint = next_checkpoint(run)
        if checkpoint is None:
            break
        checkpoint.scores["satyrn_score"] = scores[checkpoint.path.name]
        order.append(checkpoint.path.name)

    assert order == [
        "sft-20",
        "cpt-25",
        "sft-5",
        "cpt-5",
        "sft-15",
        "sft-10",
        "cpt-15",
        "cpt-20",
        "cpt-10",
    ]


def test_later_pair_wins_a_tie():
    cpt = make_stage("cpt", {5: 0.5, 10: None, 15: 0.5, 20: None, 25: 0.5})

    assert next_checkpoint(SimpleNamespace(stages=[cpt])).path.name == "cpt-20"


def test_later_stage_wins_a_tie():
    cpt = make_stage("cpt", {5: 0.5, 10: None, 15: None, 20: 0.5})
    sft = make_stage("sft", {5: 0.5, 10: None, 15: None, 20: 0.5})

    assert next_checkpoint(SimpleNamespace(stages=[cpt, sft])).path.name == "sft-15"


def test_half_evaluated_checkpoint_is_returned_again():
    cpt = make_stage("cpt", {5: 0.5, 10: 0.5, 15: None})
    cpt.checkpoints[-1].scores["python_eval"] = 0.5

    assert next_checkpoint(SimpleNamespace(stages=[cpt])).path.name == "cpt-15"


def test_no_checkpoints_to_evaluate():
    assert next_checkpoint(SimpleNamespace(stages=[])) is None
    assert next_checkpoint(SimpleNamespace(stages=[make_stage("cpt", {})])) is None
