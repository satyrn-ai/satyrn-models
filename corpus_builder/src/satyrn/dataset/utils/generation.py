"""Shared building blocks for generated Python datasets.

Key exports:
    - Idea - A proposed example based on one source document.
    - prepare_output_file() - Validate and prepare a JSONL output path.
    - append_dataset_line() - Safely append one JSON object to a JSONL file.
"""

import hashlib
import json
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NamedTuple

import click

IdeaKind = Literal["sft", "rl", "agentic-sft"]

SYSTEM_PROMPT = "You are an expert Python instructor writing teaching material for the newest Python release."

PYTHON_CODE_RULES = """
- The code must be Python source, not a shell command or CLI invocation.
- Use Python API calls (e.g. call a module's functions directly instead of `python -m module ...`).
- The code must run non-interactively to completion without requiring a real terminal.
- The code must terminate within a few seconds; no infinite loops or blocking waits.
- Only write Python code. Skip anything that cannot be expressed as a Python code example,
  such as C API changes, shell commands and CLI invocations, build configuration, etc.
"""

output_file_lock = threading.Lock()


class IdeaId(NamedTuple):
    """The hash and the line number of an idea."""

    hash: str
    line: int


@dataclass
class Idea:
    """A single Python example idea proposed for a documentation change."""

    doc_path: Path
    description: str
    python_version: str
    kind: IdeaKind
    id: IdeaId = field(default=IdeaId("", 0), compare=False)


def idea_hash(idea: Idea) -> str:
    """Return a short hash of the idea."""
    key = f"{idea.doc_path}|{idea.python_version}|{idea.description}"
    return hashlib.sha256(key.encode()).hexdigest()[:10]


def pep_identifier(doc_path: Path) -> str | None:
    """Return a normalized PEP identifier when doc_path names a PEP document."""
    match = re.search(r"\bpep[-_ ]?(\d+)\b", doc_path.stem, re.IGNORECASE)
    return f"PEP {int(match.group(1))}" if match else None


def prepare_output_file(output_path: Path) -> None:
    """Validate output_path, create its parent, and optionally clear an existing file."""
    if output_path.suffix != ".jsonl":
        raise click.BadParameter("Output file must end with .jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and click.confirm(f"{output_path} already exists. Clear it?"):
        output_path.unlink()
        output_path.with_suffix(".progress.jsonl").unlink(missing_ok=True)


def append_dataset_line(dataset_line: dict, output_path: Path) -> None:
    """Append dataset_line to output_path as one JSON line."""
    with output_file_lock, output_path.open("a") as output_file:
        output_file.write(json.dumps(dataset_line) + "\n")


def read_jsonl_file(input_path: Path) -> Iterator[dict[str, Any]]:
    for line in input_path.open("r"):
        yield json.loads(line)


def read_progress(output_path: Path, retry_failed: bool) -> set[str]:
    """Return the hashes of the ideas already logged for output_path."""
    progress_path = output_path.with_suffix(".progress.jsonl")
    if not progress_path.exists():
        return set()
    return {
        entry["idea"] for entry in read_jsonl_file(progress_path) if not (retry_failed and entry["status"] == "failed")
    }


def append_progress(idea: Idea, dataset_line: dict | None, output_path: Path) -> None:
    """Log whether idea produced a dataset line."""
    status = "failed" if dataset_line is None else "done"
    progress_entry = {"idea": idea.id.hash, "line": idea.id.line, "status": status}
    with output_path.with_suffix(".progress.jsonl").open("a") as progress_file:
        progress_file.write(json.dumps(progress_entry) + "\n")


def load_ideas(
    input_path: Path, output_path: Path, kind: IdeaKind | None = None, retry_failed: bool = False
) -> list[Idea]:
    logged = read_progress(output_path, retry_failed)
    ideas: list[Idea] = []
    for line, d in enumerate(read_jsonl_file(input_path), start=1):
        if kind is not None and d.get("kind", kind) != kind:
            continue
        d["doc_path"] = Path(d["doc_path"])
        idea = Idea(**d)
        idea.id = IdeaId(idea_hash(idea), line)
        if idea.id.hash in logged:
            continue
        ideas.append(idea)
    return ideas
