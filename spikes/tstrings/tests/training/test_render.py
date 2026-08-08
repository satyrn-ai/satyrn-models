import json

import pytest

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    TaskRecord,
)
from satyrn_model.training import (
    PYTHON_CODE_SYSTEM_PROMPT,
    LineagedTask,
    RenderedContaminationError,
    render_training_handoff,
)


def _task(
    name: str, *, prompt: str | None = None, reference: str | None = None
) -> TaskRecord:
    return TaskRecord(
        prompt=prompt or f"task {name}",
        reference=reference or f"result = {name!r}\n",
        checks=(NameEquals(name="result"),),
        policy=PolicyRef(id="test", version=1, config={}),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="test", generator_version="1", seed_id=name
        ),
    )


def test_final_render_rejects_reference_overlap_with_different_prompt(tmp_path) -> None:
    reference = "result = 'held-out'\n"
    rows = [
        LineagedTask(
            task=_task("train", prompt="different prompt", reference=reference),
            seed_ids=("seed-a",),
        ),
        LineagedTask(task=_task("other"), seed_ids=("seed-b",)),
    ]
    benchmark = (_task("benchmark", reference=reference),)

    with pytest.raises(RenderedContaminationError, match="assistant code"):
        render_training_handoff(
            rows,
            benchmark=benchmark,
            validation_fraction=0.5,
            split_seed=7,
            output_dir=tmp_path,
        )


def test_chat_handoff_is_deterministic_and_masks_prompt_loss(tmp_path) -> None:
    rows = [
        LineagedTask(
            task=_task("a"),
            seed_ids=("shared",),
            prompt_family="binding-preserving",
        ),
        LineagedTask(task=_task("b"), seed_ids=("shared",)),
        LineagedTask(task=_task("c"), seed_ids=("c",)),
        LineagedTask(task=_task("d"), seed_ids=("d",)),
    ]
    benchmark = (_task("held-out"),)

    first = render_training_handoff(
        rows,
        benchmark=benchmark,
        validation_fraction=0.25,
        split_seed=11,
        output_dir=tmp_path / "first",
    )
    second = render_training_handoff(
        list(reversed(rows)),
        benchmark=benchmark,
        validation_fraction=0.25,
        split_seed=11,
        output_dir=tmp_path / "second",
    )

    assert first.rendered_fingerprint == second.rendered_fingerprint
    assert first.loss_masking == "assistant_only"
    partitions = {
        task_id: group.partition
        for group in first.split.groups
        for task_id in group.task_ids
    }
    assert partitions[rows[0].task.id] == partitions[rows[1].task.id]
    rendered = [
        json.loads(line)
        for path in (
            tmp_path / "first/train.jsonl",
            tmp_path / "first/valid.jsonl",
        )
        for line in path.read_text().splitlines()
    ]
    assert {row["messages"][0]["role"] for row in rendered} == {"user"}
    assert {row["messages"][1]["role"] for row in rendered} == {"assistant"}
    assert {row["task_id"] for row in rendered} == {row.task.id for row in rows}
    assert {
        row["prompt_family"] for row in rendered if row["task_id"] == rows[0].task.id
    } == {"binding-preserving"}
    group = next(
        group for group in first.split.groups if rows[0].task.id in group.task_ids
    )
    assert "binding-preserving" in group.prompt_families


def test_chat_handoff_can_match_deployment_system_prompt(tmp_path) -> None:
    handoff = render_training_handoff(
        [
            LineagedTask(task=_task("aligned"), seed_ids=("seed-a",)),
            LineagedTask(task=_task("other"), seed_ids=("seed-b",)),
        ],
        benchmark=(_task("held-out"),),
        validation_fraction=0.5,
        split_seed=11,
        output_dir=tmp_path,
        system_prompt=PYTHON_CODE_SYSTEM_PROMPT,
    )

    row = next(
        json.loads(line)
        for path in (tmp_path / "train.jsonl", tmp_path / "valid.jsonl")
        for line in path.read_text().splitlines()
        if "aligned" in line
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert [message["role"] for message in row["messages"]] == [
        "system",
        "user",
        "assistant",
    ]
    assert row["messages"][0]["content"] == PYTHON_CODE_SYSTEM_PROMPT
    assert handoff.system_prompt_fingerprint == manifest["system_prompt_fingerprint"]
