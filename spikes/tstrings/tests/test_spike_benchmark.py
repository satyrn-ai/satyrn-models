"""Regression tests for the pre-training PEP 750 benchmark."""

from spike.build_benchmark import build_confirmatory, build_development
from spike.eval_model import serialize_observations
from spike.run_eval import summarize_by_benchmark_metadata

from satyrn_model.execution.protocol import Accepted, NullSandbox
from satyrn_model.execution.reference import materialize_reference


def test_confirmatory_benchmark_is_role_balanced_and_explicit() -> None:
    """Every scored task has bindings, and the agreed 70/30 mix is retained."""
    tasks, manifest = build_confirmatory()

    assert len(tasks) == 100
    assert sum(entry["role"] == "consumer" for entry in manifest) == 70
    assert sum(entry["role"] == "author" for entry in manifest) == 30
    assert {entry["review_status"] for entry in manifest} == {"needs_human_review"}
    assert all("Copy these input bindings exactly" in task.prompt for task in tasks)
    assert all("given two strings" not in task.prompt for task in tasks)


def test_benchmark_references_materialize_before_human_review() -> None:
    """The generator never emits an unexecutable reference program."""
    development, _ = build_development()
    confirmatory, _ = build_confirmatory()
    sandbox = NullSandbox()

    outcomes = [
        materialize_reference(task, sandbox=sandbox, timeout=15)
        for task in [*development, *confirmatory]
    ]

    assert all(isinstance(outcome, Accepted) for outcome in outcomes)


def test_reference_observations_are_retained_in_a_json_safe_form() -> None:
    """Evaluation artifacts retain the expected value, not only source code."""
    tasks, _ = build_confirmatory()
    outcome = materialize_reference(tasks[0], sandbox=NullSandbox(), timeout=15)

    assert isinstance(outcome, Accepted)
    assert serialize_observations(outcome.observations) == [
        {
            "kind": "name_value",
            "name": "result",
            "repr": "('prefix-confirmatory-0: ', '')",
        }
    ]


def test_evaluation_breakdowns_are_derived_from_frozen_metadata() -> None:
    results = [
        {"id": "a", "passed": True, "stage": None},
        {"id": "b", "passed": False, "stage": "policy"},
        {"id": "c", "passed": False, "stage": "semantic_check"},
    ]
    manifest = [
        {"task_id": "a", "role": "consumer", "operation": "strings", "family": "intro"},
        {"task_id": "b", "role": "consumer", "operation": "strings", "family": "intro"},
        {
            "task_id": "c",
            "role": "author",
            "operation": "author_values",
            "family": "author",
        },
    ]

    breakdowns = summarize_by_benchmark_metadata(results, manifest)

    assert breakdowns["role"]["consumer"] == {
        "total": 2,
        "passed": 1,
        "failure_stages": {"policy": 1},
    }
    assert breakdowns["operation"]["author_values"]["failure_stages"] == {
        "semantic_check": 1
    }
