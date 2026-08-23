"""Deliver frozen SFT rows in Michal's dataset schema (Roadmap M4, Phase 9)."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import click

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import get_llm
from satyrn.tstrings.types import load_source_specs

# Mirrors corpus_builder/src/satyrn/dataset/sft.py::SYSTEM_PROMPT
_SYSTEM_PROMPT = "You are an expert Python instructor writing teaching material for the newest Python release."

# Mirrors sft.py::generate_code_block's trace instruction (trace portion only).
_TRACE_INSTRUCTION = (
    "Write the reasoning that leads to this code, in first person and present tense, "
    "as you would think it through before writing it: what the task requires, which "
    "Python 3.14 feature applies and how it behaves, how the code uses it, and step by "
    "step what each statement prints as it runs. Write as though you thought of the "
    "task yourself: do not mention the attached document, the idea, training, datasets, "
    "or examples, and do not address the reader."
)

# Mirrors sft.py::generate_conversation.
_CONVERSATION_INSTRUCTION = (
    "Write a natural user question that this code would answer, and an explanation an "
    "assistant would give alongside the code in its response. Do not repeat or alter "
    "the code itself. If this feature replaces or is commonly confused with an older "
    "idiom or workaround, name that older approach in the explanation and state briefly "
    "why it no longer applies or is not the right choice here."
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


def _context(source_text: str | None, source_title: str) -> Context:
    ctx = Context()
    ctx.system_prompt = _SYSTEM_PROMPT
    if source_text is not None:
        ctx.add(source_title, source_text)
    return ctx


def generate_trace(row: dict, llm, source_text: str | None, source_title: str) -> str:
    """Return a first-person reasoning trace and store it in the row."""
    ctx = _context(source_text, source_title)
    text = llm.generate(_trace_prompt(row), ctx, thinking=True)
    row["trace"] = text
    return text


def generate_conversation(
    row: dict, llm, source_text: str | None, source_title: str
) -> tuple[str, str]:
    """Return (question, explanation) for the row, mirroring sft.py::generate_conversation."""
    ctx = _context(source_text, source_title)
    ctx.set_json_schema(
        {
            "type": "object",
            "properties": {"prompt": {"type": "string"}, "explanation": {"type": "string"}},
            "required": ["prompt", "explanation"],
        }
    )
    result = llm.generate(_conversation_prompt(row), ctx, thinking=True)
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


def _load_source_ids(gated_path: Path) -> dict[str, str]:
    """Return semantic_id -> source_id for every gated task."""
    mapping: dict[str, str] = {}
    with gated_path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            mapping[entry["semantic_id"]] = entry["provenance"]["source_id"]
    return mapping


def _deliver_row(row: dict, source_ids: dict[str, str], checkouts_dir: Path, llm) -> dict:
    """Generate trace + question/explanation for one row and assemble it."""
    source_id = source_ids[row["semantic_id"]]
    source_path = checkouts_dir / source_id / row["filename"]
    if not source_path.is_file():
        raise click.ClickException(f"source file missing: {source_path}")
    source_text = source_path.read_text()
    generate_trace(row, llm, source_text, row["filename"])
    question, explanation = generate_conversation(row, llm, source_text, row["filename"])
    return assemble_row(row, question, explanation)


def run_delivery(
    rows: list[dict],
    source_ids: dict[str, str],
    checkouts_dir: Path,
    llm,
    preview: bool = False,
    workers: int = 1,
) -> list[dict]:
    """Generate prose around each row and return Michal-schema rows."""
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            delivered = list(
                executor.map(lambda row: _deliver_row(row, source_ids, checkouts_dir, llm), rows)
            )
    else:
        delivered = [_deliver_row(row, source_ids, checkouts_dir, llm) for row in rows]
    if preview:
        for row in delivered:
            click.echo(json.dumps(row))
    return delivered


def write_manifest(
    rows: list[dict],
    train_ids: list[str],
    valid_ids: list[str],
    fingerprints: dict,
    sources: dict,
    provider: str,
    model: str,
    mock: bool,
    generated_at: str,
    path: Path,
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
    if mock:
        manifest["note"] = "prose is mock/deterministic pending a live-key delivery"
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
@click.option(
    "--checkouts-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".cache/sources",
    show_default=True,
    help="Parent dir of per-source checkouts.",
)
def main(
    input_dir: Path,
    output_dir: Path,
    llm: str,
    model: str,
    mock_llm: bool,
    preview: bool,
    workers: int,
    checkouts_dir: Path,
) -> None:
    """Deliver frozen SFT rows in Michal's dataset schema."""
    spike_root = Path(__file__).resolve().parents[3]
    input_dir = spike_root / input_dir
    output_dir = spike_root / output_dir
    checkouts_dir = spike_root / checkouts_dir

    rows: list[dict] = []
    train_ids: list[str] = []
    valid_ids: list[str] = []
    for name in ("train", "valid"):
        subset = _load_rows(input_dir / f"{name}.jsonl")
        rows.extend(subset)
        target = train_ids if name == "train" else valid_ids
        target.extend(row["semantic_id"] for row in subset)

    source_ids = _load_source_ids(spike_root / "tasks" / "gated.jsonl")
    specs = load_source_specs(spike_root / "sources.toml")
    sources = {spec.id: {"repo": spec.repo, "commit": spec.commit} for spec in specs}

    llm_obj = MockLLM() if mock_llm else get_llm(llm, model)
    delivered = run_delivery(rows, source_ids, checkouts_dir, llm_obj, preview, workers)

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "sft.jsonl").open("w") as fh:
        for row in delivered:
            fh.write(json.dumps(row) + "\n")

    corpus_bytes = (input_dir / "train.jsonl").read_bytes() + (input_dir / "valid.jsonl").read_bytes()
    fingerprints = {
        "corpus": _sha256_bytes(corpus_bytes),
        "gated": _sha256_bytes((spike_root / "tasks" / "gated.jsonl").read_bytes()),
    }
    write_manifest(
        delivered,
        train_ids,
        valid_ids,
        fingerprints,
        sources,
        llm,
        model,
        mock_llm,
        datetime.now(timezone.utc).isoformat(),
        output_dir / "manifest.json",
    )
    click.echo(f"Delivered {len(delivered)} rows into {output_dir}")
