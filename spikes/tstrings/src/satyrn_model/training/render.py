"""Deterministic assistant-only chat rendering for training handoffs."""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Literal

from satyrn_model.contracts import DatasetSnapshot, TaskRecord, semantic_content_id
from satyrn_model.training.split import (
    LineagedTask,
    SplitManifest,
    split_by_semantics_and_lineage,
)

PYTHON_CODE_SYSTEM_PROMPT = (
    "You are a Python 3.14 code generator. Output ONLY a single Python program "
    "as plain code — no explanation, no markdown fences, no comments about the "
    "code. The program must run on CPython 3.14 and define the variable `result`."
)


class RenderedContaminationError(RuntimeError):
    """Final rendered assistant code overlaps the held-out benchmark."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class RenderedTrainingRow:
    task_id: str
    semantic_id: str
    seed_ids: tuple[str, ...]
    prompt_family: str
    partition: Literal["train", "validation"]
    messages: tuple[ChatMessage, ...]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, kw_only=True)
class TrainingHandoff:
    dataset_fingerprint: str
    rendered_fingerprint: str
    benchmark_fingerprint: str
    format: Literal["chat"]
    loss_masking: Literal["assistant_only"]
    train_rows: int
    validation_rows: int
    split: SplitManifest
    output_dir: Path
    system_prompt_fingerprint: str | None


def render_training_handoff(
    rows: list[LineagedTask],
    *,
    benchmark: tuple[TaskRecord, ...],
    validation_fraction: float,
    split_seed: int,
    output_dir: Path,
    system_prompt: str | None = None,
) -> TrainingHandoff:
    """Split, gate, render, fingerprint, and persist one chat handoff."""
    _check_rendered_contamination(rows, benchmark)
    ordered_rows = sorted(rows, key=lambda item: item.task.id)
    split = split_by_semantics_and_lineage(
        ordered_rows,
        validation_fraction=validation_fraction,
        split_seed=split_seed,
    )
    validation_ids = set(split.validation_task_ids)
    rendered = [
        _render_row(
            row,
            partition="validation" if row.task.id in validation_ids else "train",
            system_prompt=system_prompt,
        )
        for row in ordered_rows
    ]
    train = [row for row in rendered if row.partition == "train"]
    validation = [row for row in rendered if row.partition == "validation"]
    train_text = _jsonl(train)
    validation_text = _jsonl(validation)
    rendered_fingerprint = hashlib.sha256(
        (train_text + validation_text).encode("utf-8")
    ).hexdigest()
    system_prompt_fingerprint = (
        hashlib.sha256(system_prompt.encode()).hexdigest() if system_prompt else None
    )
    dataset = DatasetSnapshot.from_tasks(tuple(row.task for row in ordered_rows))
    benchmark_fingerprint = hashlib.sha256(
        "".join(
            json.dumps(task.to_dict(), sort_keys=True, separators=(",", ":"))
            for task in sorted(benchmark, key=lambda task: task.id)
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "dataset_fingerprint": dataset.manifest.fingerprint,
        "rendered_fingerprint": rendered_fingerprint,
        "benchmark_fingerprint": benchmark_fingerprint,
        "format": "chat",
        "loss_masking": "assistant_only",
        "train_rows": len(train),
        "validation_rows": len(validation),
        "split_seed": split_seed,
        "validation_fraction": validation_fraction,
        "system_prompt": system_prompt,
        "system_prompt_fingerprint": system_prompt_fingerprint,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "train.jsonl").write_text(train_text, encoding="utf-8")
    (output_dir / "valid.jsonl").write_text(
        validation_text, encoding="utf-8"
    )
    (output_dir / "split-manifest.json").write_text(
        json.dumps(split.to_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return TrainingHandoff(
        dataset_fingerprint=dataset.manifest.fingerprint,
        rendered_fingerprint=rendered_fingerprint,
        benchmark_fingerprint=benchmark_fingerprint,
        format="chat",
        loss_masking="assistant_only",
        train_rows=len(train),
        validation_rows=len(validation),
        split=split,
        output_dir=output_dir,
        system_prompt_fingerprint=system_prompt_fingerprint,
    )


def _check_rendered_contamination(
    rows: list[LineagedTask], benchmark: tuple[TaskRecord, ...]
) -> None:
    benchmark_pairs = {(task.prompt, task.reference) for task in benchmark}
    benchmark_references = {task.reference for task in benchmark}
    for row in rows:
        task = row.task
        if (task.prompt, task.reference) in benchmark_pairs:
            raise RenderedContaminationError(
                f"task {task.id[:12]} exactly overlaps the benchmark"
            )
        if task.reference in benchmark_references:
            raise RenderedContaminationError(
                f"task {task.id[:12]} assistant code overlaps the benchmark"
            )


def _render_row(
    row: LineagedTask,
    *,
    partition: Literal["train", "validation"],
    system_prompt: str | None,
) -> RenderedTrainingRow:
    messages = [ChatMessage(role="user", content=row.task.prompt)]
    if system_prompt is not None:
        messages.insert(0, ChatMessage(role="system", content=system_prompt))
    messages.append(ChatMessage(role="assistant", content=row.task.reference))
    return RenderedTrainingRow(
        task_id=row.task.id,
        semantic_id=semantic_content_id(row.task),
        seed_ids=tuple(sorted(row.seed_ids)),
        prompt_family=row.prompt_family,
        partition=partition,
        messages=tuple(messages),
    )


def _jsonl(rows: list[RenderedTrainingRow]) -> str:
    return "".join(
        json.dumps(row.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
