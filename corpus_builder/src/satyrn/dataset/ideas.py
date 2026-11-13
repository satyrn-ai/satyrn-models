"""Generate ideas for dataset examples."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import get_args

import click
from tqdm import tqdm

from satyrn.dataset.agentic_sft import MIN_INITIAL_FILE_LENGTH
from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, SchemaValidationError, get_llm
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    Idea,
    IdeaKind,
    append_dataset_line,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_ideas

logger = logging.getLogger(__name__)

SFT_IDEAS_PROMPT = """
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for short, self-contained code blocks that would demonstrate the described features.

- Each idea is a short description of what the example would show.
- Propose fewer ideas if the document only covers a small change.
- Do not repeat the same idea.
- DO NOT propose ideas for parts of the document that cannot be demonstrated in Python, such as
  C API changes, shell commands and CLI invocations, or build configuration.

{python_code_rules}
"""

RL_IDEAS_PROMPT = """
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for short programming tasks in which the solver must use the described features to produce a result.

- Each idea is one sentence describing, in words, the behavior the solver must produce: no function
  signature, code, dictionary keys, or attribute and method names.
- Each idea requires the solver to create or use the feature itself. Do not propose tasks that only
  read fields of an object handed to the solver.
- Ideas that differ only by input case are one idea; propose one idea per distinct skill.
- Propose fewer ideas if the document only covers a small change.
- Do not repeat the same idea.
- DO NOT propose ideas for parts of the document that cannot be exercised in Python code, such as
  C API changes, shell commands and CLI invocations, or build configuration.

{python_code_rules}
"""

AGENTIC_SFT_IDEAS_PROMPT = """
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for coding tasks in which an agent edits, refactors or creates a single Python file so that it
uses the described features.

- Each idea describes the starting point: the file before the change, written without the described
  features, or no file if the task creates a new one. Name the function or behaviour the file
  provides. The file is a realistic module of at least {min_initial_file_length} lines, and the change
  touches only part of it.
- Each idea describes the end state: the file after the change, using the described features.
- The end state is importable code with defined behaviour: functions or classes, with no demo calls
  or asserts.
- Do not specify imports, private helper names or implementation choices.
- Define the behaviour precisely enough for unit tests to assert on its return values or exceptions.
  Every described behaviour can be triggered through the public interface with valid inputs. If the
  behaviour depends on an exact output format, state that format.
- Each idea says why a user would want the change. A change that only rewrites the syntax, with no
  benefit to the user, is not a task.
- The end state uses only the standard library.
- At least half of the ideas edit or refactor an existing file, so the solver has to read the
  existing code. The rest create a new file. A refactor does not change the file's behaviour.
- Each task needs non-trivial logic.
- Each idea is one task with one outcome. Do not offer alternatives within an idea.
- Propose one idea per distinct skill.
- Propose fewer ideas if the document only covers a small change.

{python_code_rules}
"""


def collect_input_docs(input_path: Path) -> list[Path]:
    """Return one input file or every RST document below an input directory."""
    return [input_path] if input_path.is_file() else sorted(input_path.rglob("*.rst"))


def generate_ideas(model: Model, doc_path: Path, python_version: str, kind: IdeaKind) -> list[Idea]:
    """Return distinct ideas of the given kind for features described in doc_path."""
    prompt_template = {"sft": SFT_IDEAS_PROMPT, "rl": RL_IDEAS_PROMPT, "agentic-sft": AGENTIC_SFT_IDEAS_PROMPT}[kind]
    prompt = prompt_template.format(
        python_version=python_version,
        python_code_rules=PYTHON_CODE_RULES,
        min_initial_file_length=MIN_INITIAL_FILE_LENGTH,
    )
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
    return [Idea(doc_path, description, python_version, kind) for description in response["ideas"]]


@click.command("ideas")
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory of source material to draw from, or a single doc file.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write the generated ideas to.",
)
@click.option("--python-version", required=True, help='Python version the ideas address, e.g. "3.15".')
@click.option(
    "--kind",
    type=click.Choice(get_args(IdeaKind), case_sensitive=False),
    required=True,
    help="Kind of ideas to generate.",
)
@click.option("--preview", is_flag=True, default=False, help="Print each idea after it is saved.")
@click.option("--workers", type=click.IntRange(min=1), default=1, help="Number of documents to process in parallel.")
def main(
    input_path: Path,
    output_path: Path,
    python_version: str,
    kind: str,
    preview: bool,
    workers: int,
) -> None:
    """Generate ideas for dataset examples."""
    model = get_llm("deepseek", os.environ.get("LLM_MODEL_NAME", "deepseek-v4-flash"))

    prepare_output_file(output_path)
    input_docs = collect_input_docs(input_path)

    def process_doc(doc_path: Path) -> None:
        """Generate and write the ideas for one source document."""
        try:
            ideas = generate_ideas(model, doc_path, python_version, kind)
        except SchemaValidationError:
            # After repeated attempts, we did not get a response that satisfied the schema requirements
            logger.warning("Failed to generate schema compliant output for %s", doc_path.name)
        else:
            logger.info("Generated %d ideas for %s", len(ideas), doc_path.name)
            for idea in ideas:
                idea_dict = asdict(idea)
                idea_dict["doc_path"] = str(doc_path.absolute())
                append_dataset_line(idea_dict, output_path)
            if preview:
                print_ideas(ideas)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_doc, doc_path) for doc_path in input_docs]
        for future in tqdm(as_completed(futures), total=len(input_docs), desc="Doc files"):
            future.result()
