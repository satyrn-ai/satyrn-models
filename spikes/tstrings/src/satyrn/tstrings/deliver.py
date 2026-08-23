"""Deliver frozen SFT rows in Michal's dataset schema (Roadmap M4, Phase 9)."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import get_llm
from satyrn.tstrings.types import load_source_specs

# Mirrors corpus_builder/src/satyrn/dataset/sft.py::SYSTEM_PROMPT
_SYSTEM_PROMPT = "You are an expert Python instructor writing teaching material for the newest Python release."

# Mirrors sft.py::generate_code_block's trace instruction (trace portion only),
# with a length bound so reasoning chains stay comparable to Michal's (~900 chars).
_TRACE_INSTRUCTION = (
    "Write the reasoning that leads to this code, in first person and present tense, "
    "as you would think it through before writing it: what the task requires, which "
    "Python 3.14 feature applies and how it behaves, how the code uses it, and step by "
    "step what each statement prints as it runs. Write as though you thought of the "
    "task yourself: do not mention the attached document, the idea, training, datasets, "
    "or examples, and do not address the reader. Keep it concise: at most 1200 characters."
)

# Mirrors sft.py::generate_conversation, with explicit anchoring to the idea so the
# question does not drift onto the mined code's incidental domain.
_CONVERSATION_INSTRUCTION = (
    "Write a natural user question that this code would answer, and an explanation an "
    "assistant would give alongside the code in its response. The question must match "
    "the 'Example idea' below; do not invent a different domain or topic for it. Do not "
    "repeat or alter the code itself. If this feature replaces or is commonly confused "
    "with an older idiom or workaround, name that older approach in the explanation and "
    "state briefly why it no longer applies or is not the right choice here."
)


class MockLLM:
    """Deterministic fake LLM keyed on context.expect_json (trace vs conversation)."""

    def generate(self, prompt, context, thinking=False, effort="medium"):
        if context.expect_json:
            return {
                "prompt": "What does this code do?",
                "explanation": "This builds a template string and prints its type.",
            }
        return "I consider the feature first, then construct the example step by step."


def _trace_prompt(row: dict) -> str:
    return (
        f"{_TRACE_INSTRUCTION}\n\n"
        f"Example idea: {row['idea']}\n\n"
        f"Example code:\n```python\n{row['code']}\n```\n\n"
        f"Expected output: {row['expected_output']}"
    )


def _conversation_prompt(row: dict) -> str:
    return (
        f"{_CONVERSATION_INSTRUCTION}\n\n"
        f"Example idea: {row['idea']}\n\n"
        f"Example code:\n```python\n{row['code']}\n```\n\n"
        f"Reasoning trace:\n{row['trace']}"
    )


def _context() -> Context:
    ctx = Context()
    ctx.system_prompt = _SYSTEM_PROMPT
    return ctx


def generate_trace(row: dict, llm) -> str:
    """Return a first-person reasoning trace and store it in the row."""
    text = llm.generate(_trace_prompt(row), _context(), thinking=True)
    row["trace"] = text
    return text


def generate_conversation(row: dict, llm) -> tuple[str, str]:
    """Return (question, explanation) for the row, mirroring sft.py::generate_conversation."""
    ctx = _context()
    ctx.set_json_schema(
        {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "explanation": {"type": "string"}},
            "required": ["prompt", "explanation"],
        }
    )
    result = llm.generate(_conversation_prompt(row), ctx, thinking=True)
    if isinstance(result, str):
        result = json.loads(result)
    return result["prompt"], result["explanation"]


def assemble_row(row: dict, question: str, explanation: str) -> dict:
    """Return the Michal-schema row (exactly 8 keys)."""
    return {
        "prompt": [{"role": "user", "content": question}],
        "completion": [
            {"role": "assistant", "content": f"{explanation}\n\n```python\n{row['code']}\n```"}
        ],
        "filename": row["filename"],
        "python_version": row["python_version"],
        "idea": row["idea"],
        "code": row["code"],
        "trace": row["trace"],
        "expected_output": row["expected_output"],
    }


def _deliver_row(row: dict, llm) -> tuple[str, dict]:
    """Generate trace + question/explanation for one row; return (semantic_id, row)."""
    generate_trace(row, llm)
    question, explanation = generate_conversation(row, llm)
    return row["semantic_id"], assemble_row(row, question, explanation)


def _load_checkpoint(checkpoint_path: Path) -> dict[str, dict]:
    """Return semantic_id -> delivered row for everything already delivered."""
    completed: dict[str, dict] = {}
    if not checkpoint_path.exists():
        return completed
    with checkpoint_path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            completed[entry["semantic_id"]] = entry["row"]
    return completed


def _append_checkpoint(checkpoint_path: Path, semantic_id: str, row: dict) -> None:
    with checkpoint_path.open("a") as fh:
        fh.write(json.dumps({"semantic_id": semantic_id, "row": row}) + "\n")
        fh.flush()


def run_delivery(
    rows: list[dict],
    llm,
    output_dir: Path,
    preview: bool = False,
    workers: int = 1,
    resume: bool = True,
) -> tuple[list[dict], bool]:
    """Generate prose around each row; return (ordered delivered rows, complete).

    Resumable: completed rows are checkpointed to output_dir/_checkpoint.jsonl keyed
    by semantic_id. On resume, already-completed rows are skipped and only the
    pending ones are regenerated. Failed rows are logged and left un-checkpointed so
    a later run retries them.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "_checkpoint.jsonl"
    completed = _load_checkpoint(checkpoint_path) if resume else {}

    pending = [row for row in rows if row["semantic_id"] not in completed]

    def _finish(semantic_id: str, row: dict) -> None:
        _append_checkpoint(checkpoint_path, semantic_id, row)
        completed[semantic_id] = row
        if preview:
            click.echo(json.dumps(row))

    if pending and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_deliver_row, row, llm): row for row in pending}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    semantic_id, delivered = future.result()
                except Exception as error:
                    click.echo(f"failed {row['semantic_id']}: {error}", err=True)
                    continue
                _finish(semantic_id, delivered)
    else:
        for row in pending:
            try:
                semantic_id, delivered = _deliver_row(row, llm)
            except Exception as error:
                click.echo(f"failed {row['semantic_id']}: {error}", err=True)
                continue
            _finish(semantic_id, delivered)

    ordered = [completed[row["semantic_id"]] for row in rows if row["semantic_id"] in completed]
    return ordered, len(ordered) == len(rows)


def write_manifest(
    rows: list[dict],
    train_ids: list[str],
    valid_ids: list[str],
    fingerprints: dict,
    sources: dict,
    provider: str,
    model: str,
    generated_at: str,
    path: Path,
    note: str | None = None,
) -> None:
    """Write the delivery manifest recording split, fingerprints, and provenance."""
    manifest = {
        "row_count": len(rows),
        "train_semantic_ids": train_ids,
        "valid_semantic_ids": valid_ids,
        "fingerprints": fingerprints,
        "sources": sources,
        "provider": provider,
        "model": model,
        "generated_at": generated_at,
    }
    if note:
        manifest["note"] = note
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def _sha256_bytes(data: bytes) -> str:
    """Return the hex sha256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _load_rows(path: Path) -> list[dict]:
    """Read JSONL rows from path."""
    with path.open("r") as fh:
        return [json.loads(line) for line in fh if line.strip()]


@click.command("deliver")
@click.option(
    "-i", "--input-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="corpus-sft",
    show_default=True,
    help="Directory holding train.jsonl and valid.jsonl.",
)
@click.option(
    "-o", "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="delivery",
    show_default=True,
    help="Directory to write the delivered dataset into.",
)
@click.option("--llm", default="deepseek", show_default=True, help="LLM provider for prose generation.")
@click.option("--model", default="deepseek-v4-flash", show_default=True, help="Model name for the LLM provider.")
@click.option("--mock-llm", is_flag=True, default=False, help="Use a deterministic fake LLM.")
@click.option("--preview", is_flag=True, default=False, help="Print each delivered row as it is written.")
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Rows to generate in parallel.",
)
@click.option("--fresh", is_flag=True, default=False, help="Ignore any checkpoint and start over.")
def main(
    input_dir: Path,
    output_dir: Path,
    llm: str,
    model: str,
    mock_llm: bool,
    preview: bool,
    workers: int,
    fresh: bool,
) -> None:
    """Deliver frozen SFT rows in Michal's dataset schema."""
    spike_root = Path(__file__).resolve().parents[3]
    input_dir = spike_root / input_dir
    output_dir = spike_root / output_dir

    rows: list[dict] = []
    train_ids: list[str] = []
    valid_ids: list[str] = []
    for name in ("train", "valid"):
        subset = _load_rows(input_dir / f"{name}.jsonl")
        rows.extend(subset)
        target = train_ids if name == "train" else valid_ids
        target.extend(row["semantic_id"] for row in subset)

    specs = load_source_specs(spike_root / "sources.toml")
    sources = {spec.id: {"repo": spec.repo, "commit": spec.commit} for spec in specs}

    llm_obj = MockLLM() if mock_llm else get_llm(llm, model)
    delivered, complete = run_delivery(
        rows, llm_obj, output_dir, preview, workers, resume=not fresh
    )

    with (output_dir / "sft.jsonl").open("w") as fh:
        for row in delivered:
            fh.write(json.dumps(row) + "\n")

    corpus_bytes = (input_dir / "train.jsonl").read_bytes() + (input_dir / "valid.jsonl").read_bytes()
    fingerprints = {
        "corpus": _sha256_bytes(corpus_bytes),
        "gated": _sha256_bytes((spike_root / "tasks" / "gated.jsonl").read_bytes()),
    }
    note = "prose is mock/deterministic pending a live-key delivery" if mock_llm else None
    if not complete:
        pending_note = f"incomplete: {len(rows) - len(delivered)} rows pending — re-run to resume"
        note = f"{note}; {pending_note}" if note else pending_note
    write_manifest(
        delivered,
        train_ids,
        valid_ids,
        fingerprints,
        sources,
        llm,
        model,
        datetime.now(timezone.utc).isoformat(),
        output_dir / "manifest.json",
        note,
    )
    click.echo(f"Delivered {len(delivered)}/{len(rows)} rows into {output_dir}")
