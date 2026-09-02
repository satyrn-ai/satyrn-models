"""Shared building blocks for generated Python datasets.

Key exports:
    - Idea - A proposed example based on one source document.
    - generate_ideas() - Ask an LLM for distinct demonstrable ideas.
    - prepare_output_file() - Validate and prepare a JSONL output path.
    - append_dataset_line() - Safely append one JSON object to a JSONL file.
"""

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import click

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model

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


def pep_identifier(doc_path: Path) -> str | None:
    """Return a normalized PEP identifier when doc_path names a PEP document."""
    match = re.search(r"\bpep[-_ ]?(\d+)\b", doc_path.stem, re.IGNORECASE)
    return f"PEP {int(match.group(1))}" if match else None


def generate_ideas(model: Model, doc_path: Path, python_version: str) -> list[Idea]:
    """Return distinct Python example ideas for features described in doc_path."""
    prompt = f"""
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for short, self-contained code blocks that would demonstrate the described features.

- Each idea is a short description of what the example would show.
- Propose fewer ideas if the document only covers a small change.
- Do not repeat the same idea.
- DO NOT propose ideas for parts of the document that cannot be demonstrated in Python, such as
  C API changes, shell commands and CLI invocations, or build configuration.

{PYTHON_CODE_RULES}
    """
    schema = {
        "type": "object",
        "properties": {
            "ideas": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["ideas"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(doc_path.name, doc_path)
    context.set_json_schema(schema)
    response = model.generate(prompt, context, thinking=True)
    return [Idea(doc_path, description, python_version) for description in response["ideas"]]


def prepare_output_file(output_path: Path) -> None:
    """Validate output_path, create its parent, and optionally clear an existing file."""
    if output_path.suffix != ".jsonl":
        raise click.BadParameter("Output file must end with .jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and click.confirm(f"{output_path} already exists. Clear it?"):
        output_path.unlink()


def collect_input_docs(input_path: Path) -> list[Path]:
    """Return one input file or every RST document below an input directory."""
    return [input_path] if input_path.is_file() else sorted(input_path.rglob("*.rst"))


def append_dataset_line(dataset_line: dict, output_path: Path) -> None:
    """Append dataset_line to output_path as one JSON line."""
    with output_file_lock, output_path.open("a") as output_file:
        output_file.write(json.dumps(dataset_line) + "\n")
