"""Shared building blocks for generated Python datasets.

Key exports:
    - Idea - A proposed example based on one source document.
    - prepare_output_file() - Validate and prepare a JSONL output path.
    - append_dataset_line() - Safely append one JSON object to a JSONL file.
"""

import json
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import click

IdeaKind = Literal["sft", "rl"]

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


@dataclass
class Idea:
    """A single Python example idea proposed for a documentation change."""

    doc_path: Path
    description: str
    python_version: str
    kind: IdeaKind


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


def append_dataset_line(dataset_line: dict, output_path: Path) -> None:
    """Append dataset_line to output_path as one JSON line."""
    with output_file_lock, output_path.open("a") as output_file:
        output_file.write(json.dumps(dataset_line) + "\n")


def read_jsonl_file(input_path: Path) -> Iterator[dict[str, Any]]:
    for line in input_path.open("r"):
        yield json.loads(line)


def load_ideas(input_path: Path) -> list[Idea]:
    ideas: list[Idea] = []
    for d in read_jsonl_file(input_path):
        # We have to convert the document path from a str to a Path
        d["doc_path"] = Path(d["doc_path"])
        ideas.append(Idea(**d))
    return ideas
