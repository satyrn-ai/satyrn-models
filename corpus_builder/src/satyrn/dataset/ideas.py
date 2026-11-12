"""Generate ideas for SFT and RL dataset examples."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, SchemaValidationError, get_llm
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    USE_CASE_RULES,
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

# Perhaps we should use the phrase 'making it more robust' rather than 'making it more secure'?
USE_CASE_IDEAS_PROMPT = """
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for short practical Python programming problems that could benefit from the use of the described features.

- Each idea is a short description of a practical situation that can be solved with pure Python where the use
  of the described feature improves the code by simplifying it, making it more robust, making it more secure,
  making it more elegant or a combination of the aforementioned.
- Propose fewer ideas if the document only covers a small change.
- Do not repeat the same idea.
- Propose fewer ideas when the ideas start becoming too similar to previous ideas.
- DO NOT propose ideas for parts of the document that cannot be demonstrated in Python, such as
  C API changes, shell commands and CLI invocations, or build configuration.

{python_code_rules}
"""

IDEAS_PROMPTS: dict[IdeaKind, tuple[str, str]] = {
    "sft": (SFT_IDEAS_PROMPT, PYTHON_CODE_RULES),
    "rl": (RL_IDEAS_PROMPT, PYTHON_CODE_RULES),
    "use_case": (USE_CASE_IDEAS_PROMPT, USE_CASE_RULES),
}


def collect_input_docs(input_path: Path) -> list[Path]:
    """Return one input file or every RST document below an input directory."""
    return [input_path] if input_path.is_file() else sorted(input_path.rglob("*.rst"))


def generate_ideas(model: Model, doc_path: Path, python_version: str, kind: IdeaKind) -> list[Idea]:
    """Return distinct ideas of the given kind for features described in doc_path."""
    prompt_template, python_code_rules = IDEAS_PROMPTS[kind]
    prompt = prompt_template.format(python_version=python_version, python_code_rules=python_code_rules)
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
    type=click.Choice(list(IDEAS_PROMPTS), case_sensitive=False),
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
    """Generate ideas for SFT or RL dataset examples."""
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
