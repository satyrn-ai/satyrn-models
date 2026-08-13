"""Supervised Fine-Tuning (SFT) dataset generation."""

import json
import logging
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, get_llm
from satyrn.dataset.utils.preview import print_dataset_line
from satyrn.dataset.utils.sandbox import run_in_sandbox

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are an expert Python instructor writing teaching material for the newest Python release."


def generate_ideas(model: Model, doc_path: Path, python_version: str) -> list[str]:
    """Return code-block ideas an LLM proposes for the features described in doc_path."""
    prompt = f"""
The attached document describes a change in Python version {python_version}. Describe between 0 and 50
ideas for short, self-contained code blocks that would demonstrate the described features.

- Each idea is a one-sentence description of what the code block would show.
- Propose fewer ideas if the document only covers a small change.
- Do not repeat the same idea.
- The idea's code must run non-interactively to completion without requiring a real terminal.
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
    response = model.generate(prompt, context)
    return response["ideas"]


def generate_code_block(model: Model, doc_path: Path, idea: str, python_version: str) -> dict:
    """Return a verified code block, its reasoning trace, and expected output."""
    prompt = f"""
The attached document describes a change in Python version {python_version}. Write the `code` block
described by this idea:

{idea}

In `trace` write why why this will make a good training example followed by a step-by-step trace of
what the code does when it runs.

In `expected_output` state exactly what running the code outputs, whether to stdout or stderr.

- The code must be Python source, not a shell command or CLI invocation.
- Use Python API calls (e.g. call a module's functions directly instead of `python -m module ...`).
- The code must run non-interactively to completion without requiring a real terminal.
        """
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "trace": {"type": "string"},
            "expected_output": {"type": "string"},
        },
        "required": ["code", "trace", "expected_output"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(doc_path.name, doc_path)
    context.set_json_schema(schema)

    prompt = prompt
    max_attempts = 3
    for attempt in range(max_attempts):
        result = model.generate(prompt, context)
        if verify_code_block(result["code"], result["expected_output"], python_version):
            return result

        # Allow the model to retry code/output generation
        # Intentionally leave actual_output out of the retry prompt, so model doesn't just copy it.
        prompt = (
            prompt
            + "\n\n"
            + f"""
Your previous code:
{result["code"]}

Reasoning trace:
{result["trace"]}

Predicted output:
{result["expected_output"]}

That prediction did not match the code's actual output. Fix the code so it actually does what the
idea describes, and predict its real output again.
"""
        )
        logger.warning(
            "Attempt %d/%d: code block did not verify. Prompting model to try again.", attempt + 1, max_attempts
        )

        # Literature suggests adding LLM-as-a-judge filtering to improve SFT performance. Ref: 2504.04030 (Sec. 4.1)

    raise ValueError(f"Could not generate a verified code block for idea: {idea}")


def generate_conversation(model: Model, doc_path: Path, idea: str, code_block: dict, python_version: str) -> dict:
    """Return a user prompt and assistant response pair whose response includes code_block's verified code."""
    prompt = f"""
The attached document describes a change in Python version {python_version}. A verified code block
demonstrates this idea:

{idea}

Code:
{code_block["code"]}

Reasoning trace:
{code_block["trace"]}

Write a natural user question that this code would answer, and an explanation an assistant would give
alongside the code in its response. Do not repeat or alter the code itself.
"""
    schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": ["prompt", "explanation"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(doc_path.name, doc_path)
    context.set_json_schema(schema)
    result = model.generate(prompt, context)

    response = f"{result['explanation']}\n\n```python\n{code_block['code']}\n```"
    return {"prompt": result["prompt"], "response": response}


def verify_code_block(code: str, expected_output: str, python_version: str) -> bool:
    """Run code under python_version. Return True if its output matches expected_output."""
    actual_output = run_in_sandbox(python_version, code)
    if actual_output.strip() == expected_output.strip():
        return True
    logger.warning(
        "Code block did not verify under Python %s.\nCode:\n%s\nExpected output:\n%s\nActual output:\n%s",
        python_version,
        code,
        expected_output,
        actual_output,
    )
    return False


@click.command("sft")
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
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Directory to write the generated JSONL into.",
)
@click.option("--python-version", required=True, help='Python version the dataset addresses, e.g. "3.15".')
@click.option("--preview", is_flag=True, default=False, help="Print each dataset line after it is saved.")
def main(input_path: Path, output_dir: Path, python_version: str, preview: bool) -> None:
    """Generate an SFT dataset for every doc file under input_path."""
    model = get_llm("deepseek", "deepseek-v4-flash", thinking=False)

    # Prepare output file
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "sft.jsonl"
    if output_path.exists() and click.confirm(f"{output_path} already exists. Clear it?"):
        output_path.unlink()

    # Collect input docs
    input_docs = [input_path] if input_path.is_file() else sorted(input_path.rglob("*.rst"))

    with output_path.open("a") as fh:
        # Process each doc file
        progress_bar = tqdm(input_docs, desc="Doc files")
        for doc_path in progress_bar:
            progress_bar.set_postfix(file=doc_path.name)

            ideas = generate_ideas(model, doc_path, python_version)

            # Process each conversation idea for the current doc file
            for idea in tqdm(ideas, desc="File entries", leave=False):
                try:
                    code_block = generate_code_block(model, doc_path, idea, python_version)
                    conversation = generate_conversation(model, doc_path, idea, code_block, python_version)
                except ValueError as error:
                    logger.warning("Skipping idea: %s", error)
                    continue

                dataset_line = {
                    "messages": [
                        {"role": "user", "content": conversation["prompt"]},
                        {"role": "assistant", "content": conversation["response"]},
                    ],
                    "filename": doc_path.name,
                    "python_version": python_version,
                    "idea": idea,
                    "code": code_block["code"],
                    "trace": code_block["trace"],
                    "expected_output": code_block["expected_output"],
                }

                fh.write(json.dumps(dataset_line) + "\n")
                fh.flush()
                if preview:
                    print_dataset_line(dataset_line)
