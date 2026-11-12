"""Agentic multi-turn Supervised Fine-Tuning (SFT) dataset generation."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, get_llm
from satyrn.dataset.pi_harness.harness import File
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    Idea,
    append_dataset_line,
    load_ideas,
    output_file_lock,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_dataset_line

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    """A coding task on one file: the agent's prompt, the file before and after, and tests for after."""

    prompt: str
    before: File | None
    after: File
    tests: str


def generate_task(model: Model, idea: Idea) -> Task:
    """Return a task for idea, generated from its source document."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Create a task for
a coding assistant working in a workspace with at most one Python file, as described by this idea:

{idea.description}

- In `file_name`, give the name of the Python file.
- In `before`, give the file's content before the task, or an empty string if the task creates it.
- In `after`, give the file's complete content once the task is done.
- In `tests`, write plain `assert` statements that pass when appended to `after` and fail on the
  preceding Python feature release. They check return values or raised exceptions.
- The tests are deterministic, use only the standard library and finish quickly.
- In `prompt`, write the request a user sends to the assistant. Name the file and the signatures of
  the functions to change or create, and follow the rules for `prompt` below.

Rules for `prompt`:

When writing `prompt`, you are the user of the coding assistant. You want the assistant to turn
`before` into `after`, or to create `after` when `before` is empty, but you do not tell it how to do
that or how to test it.

- `prompt` sounds natural, like something a user would ask for.
- The user may know nothing about the new Python features. The assistant also receives the attached
  document and has to work them out from it.
- The user does not describe implementation steps and does not mention tests, which do not exist for
  the user.

{PYTHON_CODE_RULES}
    """
    schema = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string"},
            "before": {"type": "string"},
            "prompt": {"type": "string"},
            "after": {"type": "string"},
            "tests": {"type": "string"},
        },
        "required": ["file_name", "before", "prompt", "after", "tests"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)
    response = model.generate(prompt, context, thinking=True)

    before = File(response["file_name"], response["before"]) if response["before"] else None
    return Task(response["prompt"], before, File(response["file_name"], response["after"]), response["tests"])


def build_dataset_line(model: Model, idea: Idea) -> dict | None:
    """Return a dataset line for idea, or None if it was rejected."""
    try:
        task = generate_task(model, idea)
    except Exception as error:
        logger.error("Skipping idea: %s", error)
        return None

    return {"idea": idea.description, "task": asdict(task)}


@click.command("agentic-sft")
@click.option(
    "-i",
    "--ideas-path",
    "ideas_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the JSONL file from which the ideas should be loaded.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write the generated dataset to.",
)
@click.option("--python-version", required=True, help='Python version the dataset addresses, e.g. "3.15".')
@click.option("--preview", is_flag=True, default=False, help="Print each dataset line after it is saved.")
@click.option("--workers", type=click.IntRange(min=1), default=1, help="Number of lines to generate in parallel.")
def main(
    ideas_path: Path,
    output_path: Path,
    python_version: str,
    preview: bool,
    workers: int,
) -> None:
    """Generate an agentic multi-turn SFT dataset for every loaded idea."""
    model = get_llm("deepseek", os.environ.get("LLM_MODEL_NAME", "deepseek-v4-flash"))

    prepare_output_file(output_path)
    ideas = load_ideas(ideas_path, "agentic-sft")
    logger.info("Loaded %d ideas", len(ideas))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(build_dataset_line, model, idea) for idea in ideas]
        for future in tqdm(as_completed(futures), total=len(ideas), desc="Ideas"):
            dataset_line = future.result()
            if dataset_line is None:
                continue
            append_dataset_line(dataset_line, output_path)
            if preview:
                with output_file_lock:
                    print_dataset_line(dataset_line)
