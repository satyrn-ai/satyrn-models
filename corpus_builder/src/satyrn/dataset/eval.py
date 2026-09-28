"""Generate testable Python evaluation datasets."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.models import get_llm
from satyrn.dataset.rl import BuilderTools, build_dataset_line, generate_task_ideas
from satyrn.dataset.utils.concurrency import split_workers
from satyrn.dataset.utils.generation import (
    append_dataset_line,
    collect_input_docs,
    output_file_lock,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_dataset_line, print_ideas
from satyrn.dataset.utils.sandbox import remove_leftover_containers

logger = logging.getLogger(__name__)

EVAL_PROMPT_RULES = """\
- `prompt` names the feature but must not show its syntax or API: no example literals, call forms,
  keywords, attribute or method names, or import paths.
- `prompt` describes what the entry point returns or does, not how to construct it: it must not say
  which constructs or API elements to use.
- `prompt` states the return type and what it means, but not the concrete values the tests assert.
- `prompt` does not explain how the feature works, what it accepts or rejects, or how older Python
  versions behave.
"""


@click.command("eval")
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
    help="JSONL file to write the generated dataset to.",
)
@click.option("--python-version", required=True, help='Python version the dataset addresses, e.g. "3.15".')
@click.option("--preview", is_flag=True, default=False, help="Print each dataset line after it is saved.")
@click.option("--workers", type=click.IntRange(min=1), default=1, help="Number of lines to generate in parallel.")
def main(input_path: Path, output_path: Path, python_version: str, preview: bool, workers: int) -> None:
    """Generate a testable evaluation dataset."""
    model = get_llm("deepseek", "deepseek-v4-flash")
    tools = BuilderTools(model, python_version)
    file_workers, idea_workers = split_workers(workers)

    prepare_output_file(output_path)
    input_docs = collect_input_docs(input_path)

    def process_doc(doc_path: Path) -> None:
        """Generate and write every testable task for one source document."""
        ideas = generate_task_ideas(model, doc_path, python_version)
        logger.info("Generated %d ideas for %s", len(ideas), doc_path.name)
        if preview:
            print_ideas(ideas)

        with ThreadPoolExecutor(max_workers=idea_workers) as executor:
            futures = [
                executor.submit(build_dataset_line, tools, idea, generator_instructions=EVAL_PROMPT_RULES)
                for idea in ideas
            ]
            for future in as_completed(futures):
                dataset_line = future.result()
                if dataset_line is None:
                    continue
                append_dataset_line(dataset_line, output_path)
                if preview:
                    with output_file_lock:
                        print_dataset_line(dataset_line)

    try:
        with ThreadPoolExecutor(max_workers=file_workers) as executor:
            futures = [executor.submit(process_doc, doc_path) for doc_path in input_docs]
            for future in tqdm(as_completed(futures), total=len(input_docs), desc="Doc files"):
                future.result()
    finally:
        logger.info("Cleaning up sandbox containers...")
        removed_count = remove_leftover_containers()
        logger.info("Removed %d leftover sandbox containers", removed_count)
