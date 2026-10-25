"""Generate testable Python evaluation and Reinforcement Learning datasets."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.models import SchemaValidationError, get_llm
from satyrn.dataset.utils.generation import (
    append_dataset_line,
    collect_input_docs,
    generate_ideas,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_ideas

logger = logging.getLogger(__name__)

PASS_MARKER = "__SATYRN_TEST_PASSED__"


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
    help="JSONL file to write the generated dataset to.",
)
@click.option("--python-version", required=True, help='Python version the dataset addresses, e.g. "3.15".')
@click.option("--preview", is_flag=True, default=False, help="Print each idea after it is saved.")
@click.option("--workers", type=click.IntRange(min=1), default=1, help="Number of lines to generate in parallel.")
def main(
    input_path: Path,
    output_path: Path,
    python_version: str,
    preview: bool,
    workers: int,
) -> None:
    """Generate a testable evaluation and Reinforcement Learning dataset."""
    model = get_llm("deepseek", os.environ.get("LLM_MODEL_NAME", "deepseek-v4-flash"))

    prepare_output_file(output_path)
    input_docs = collect_input_docs(input_path)

    def process_doc(doc_path: Path) -> None:
        """Generate and write every testable task for one source document."""
        try:
            ideas = generate_ideas(model, doc_path, python_version)
        except SchemaValidationError:
            # After repeated attempts, we did not get a response that satisfied the schema requirements
            logger.warning(f"Failed to generate schema compliant output for {doc_path.name}")
        else:
            logger.info(f"Generated {len(ideas)} ideas for {doc_path.name}")
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
