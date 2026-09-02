"""Supervised Fine-Tuning (SFT) dataset generation."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, get_llm
from satyrn.dataset.utils.concurrency import split_workers
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    Idea,
    append_dataset_line,
    collect_input_docs,
    generate_ideas,
    output_file_lock,
    pep_identifier,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_dataset_line, print_ideas
from satyrn.dataset.utils.sandbox import Sandbox, get_predecessor_python_version, remove_leftover_containers

logger = logging.getLogger(__name__)


def generate_code_block(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> dict:
    """Return a verified code block, its reasoning trace, and expected output."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Write the `code`
block described by this idea:

{idea.description}

In `trace` write the reasoning that leads to this code, in first person and present tense, as you
would think it through before writing it: what the task requires, which Python
{idea.python_version} feature applies and how it behaves, how the code uses it, and step by step
what each statement prints as it runs. Write as though you thought of the task yourself: do not
mention the attached document, the idea, training, datasets, or examples, and do not address the
reader.

In `expected_output` state exactly what running the code outputs, whether to stdout or stderr.

{PYTHON_CODE_RULES}
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
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)

    max_attempts = 3
    for attempt in range(max_attempts):
        code_block = model.generate(prompt, context, thinking=True)
        verified, actual_output = verify_code_block(
            code_block["code"], code_block["expected_output"], sandbox, predecessor_sandbox
        )
        if verified:
            return code_block

        if actual_output.strip() == code_block["expected_output"].strip():
            prompt += f"""\n
Your previous code:
{code_block["code"]}

Reasoning trace:
{code_block["trace"]}

Predicted output:
{code_block["expected_output"]}

The code produced equivalent output under both Python {sandbox.python_version} and Python
{predecessor_sandbox.python_version}, so it does not demonstrate behavior introduced in Python
{sandbox.python_version}. Fix the code to specifically demonstrate the new behavior.
            """
            logger.warning(
                "Attempt %d/%d: code block behaved equivalently under Python %s. Prompting model to retry.",
                attempt + 1,
                max_attempts,
                predecessor_sandbox.python_version,
            )
            continue

        judgement = judge_code_block(model, idea, code_block, actual_output)
        if judgement["passed"]:
            logger.info("Judge accepted mismatched output: %s", judgement["judgement"])
            code_block["expected_output"] = actual_output
            return code_block

        # Allow the model to retry code/output generation
        # Intentionally leave actual_output out of the retry prompt, so model doesn't just copy it.
        prompt += f"""\n
Your previous code:
{code_block["code"]}

Reasoning trace:
{code_block["trace"]}

Predicted output:
{code_block["expected_output"]}

That prediction did not match the code's actual output.

{judgement["judgement"]}

Fix the code so it actually does what the idea describes, and predict its real output again.
        """
        logger.warning("Attempt %d/%d: code block did not verify. Prompting model to retry.", attempt + 1, max_attempts)

    raise ValueError(f"Could not generate a verified code block for idea: {idea.description}")


def judge_code_block(model: Model, idea: Idea, result: dict, actual_output: str) -> dict:
    """Return a judge verdict on whether a code block that failed verification still teaches idea correctly."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. A code block was
written to demonstrate this idea, but its predicted output did not match what the code actually
produces.

Idea:
{idea.description}

Code:
{result["code"]}

Reasoning trace:
{result["trace"]}

Predicted output:
{result["expected_output"]}

Actual output:
{actual_output}

The code was required to follow these rules:
{PYTHON_CODE_RULES}

Decide whether the code still correctly demonstrates the idea, and set `passed` to true only if all
of these hold:

- The code is a correct, working implementation of the idea.
- The mismatch is incidental to the idea, such as a whitespace or formatting difference,
  not a mistake in something the idea is meant to teach.

Set `passed` to false if any of these is true:

- The code does not correctly implement the idea, or the mismatch reveals a real bug.
- The code's output is non-deterministic (e.g. it includes a timestamp, a random value, a memory
  address, or hash-randomized ordering), so the mismatch cannot be fixed by predicting a different
  fixed value.

In `judgement`, explain your decision. If `passed` is false, use it to hint how to fix the code on the
next attempt, e.g. by naming the non-deterministic source and how to remove it, or the part of the
idea the code fails to implement. Do not reveal the actual output value itself in `judgement`.

If `passed` is true, judgement should be brief information that the problem was whitespace, formatting, etc.
    """
    schema = {
        "type": "object",
        "properties": {
            "judgement": {"type": "string"},
            "passed": {"type": "boolean"},
        },
        "required": ["judgement", "passed"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)
    return model.generate(prompt, context)


def verify_code_block(
    code: str, expected_output: str, sandbox: Sandbox, predecessor_sandbox: Sandbox
) -> tuple[bool, str]:
    """Verify expected target output and reject equivalent predecessor behavior."""
    actual_output = sandbox.run(code)
    if actual_output.strip() != expected_output.strip():
        logger.warning(
            "Code block did not verify under Python %s.\nCode:\n%s\nExpected output:\n%s\nActual output:\n%s",
            sandbox.python_version,
            code,
            expected_output,
            actual_output,
        )
        return False, actual_output

    predecessor_output = predecessor_sandbox.run(code)
    if predecessor_output.strip() == actual_output.strip():
        logger.warning(
            "Code block behaved equivalently under Python %s and Python %s.\nCode:\n%s\nOutput:\n%s",
            sandbox.python_version,
            predecessor_sandbox.python_version,
            code,
            actual_output,
        )
        return False, actual_output

    return True, actual_output


def generate_conversation(model: Model, idea: Idea, code_block: dict) -> dict:
    """Return a user prompt and assistant response pair whose response includes code_block's verified code."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. A verified code
block demonstrates this idea:

{idea.description}

Code:
{code_block["code"]}

Reasoning trace:
{code_block["trace"]}

Write a natural user question that this code would answer, and an explanation an assistant would give
alongside the code in its response. Do not repeat or alter the code itself.

If this feature replaces or is commonly confused with an older idiom or workaround, name that older
approach in the explanation and state briefly why it no longer applies or is not the right choice here.
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
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)
    result = model.generate(prompt, context)

    response = f"{result['explanation']}\n\n```python\n{code_block['code']}\n```"
    return {"prompt": result["prompt"], "response": response}


def judge_conversation(model: Model, idea: Idea, code_block: dict, conversation: dict) -> None:
    """Raise ValueError if conversation is not a good SFT training example."""
    messages = [
        {"role": "user", "content": conversation["prompt"]},
        {"role": "assistant", "content": conversation["response"]},
    ]
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. The following
conversation was generated to teach this idea as a fine-tuning example.

Idea:
{idea.description}

Code:
{code_block["code"]}

Actual output when the code runs:
{code_block["expected_output"]}

Conversation:
{json.dumps(messages, indent=2)}

Decide whether this conversation is a good training example for fine-tuning a model on Python
{idea.python_version}, and set `passed` to true only if all of these hold:

- The messages follow logically from each other: the assistant's response actually answers the
  user's message.
- The code is not contrived to work around sandbox limitations (e.g. avoiding real file I/O, network
  access, or subprocesses only because a sandbox can't run them, rather than because the idea calls
  for it).
- The example teaches idea correctly and reads like something a real user would ask.

Set `passed` to false if any of these is true:

- The messages are malformed or don't logically match each other.
- The code was clearly written to dodge sandbox limitations instead of naturally demonstrating the
  idea.
- The example does not actually teach idea.

In `judgement`, explain your decision.
    """
    schema = {
        "type": "object",
        "properties": {
            "judgement": {"type": "string"},
            "passed": {"type": "boolean"},
        },
        "required": ["judgement", "passed"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)
    response = model.generate(prompt, context)

    if not response["passed"]:
        raise ValueError(f"Judge rejected conversation: {response['judgement']}")


def build_dataset_line(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> dict | None:
    """Return a verified dataset line for idea, or None if it was rejected."""
    try:
        code_block = generate_code_block(model, idea, sandbox, predecessor_sandbox)
        conversation = generate_conversation(model, idea, code_block)
        judge_conversation(model, idea, code_block, conversation)
    except ValueError as error:
        logger.warning("Skipping idea: %s", error)
        return None
    except Exception as error:
        logger.error("Skipping idea: %s", error)
        return None

    return {
        "prompt": [{"role": "user", "content": conversation["prompt"]}],
        "completion": [{"role": "assistant", "content": conversation["response"]}],
        "filename": idea.doc_path.name,
        "pep": pep_identifier(idea.doc_path),
        "python_version": idea.python_version,
        "idea": idea.description,
        "code": code_block["code"],
        "trace": code_block["trace"],
        "expected_output": code_block["expected_output"],
    }


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
    """Generate an SFT dataset for every doc file under input_path."""
    model = get_llm("deepseek", "deepseek-v4-flash")
    sandbox = Sandbox(python_version)
    predecessor_sandbox = Sandbox(get_predecessor_python_version(python_version))
    file_workers, idea_workers = split_workers(workers)

    prepare_output_file(output_path)
    input_docs = collect_input_docs(input_path)

    def process_doc(doc_path: Path) -> None:
        """Generate and write every dataset line for one doc file."""
        ideas = generate_ideas(model, doc_path, python_version)
        logger.info("Generated %d ideas for %s", len(ideas), doc_path.name)
        if preview:
            print_ideas(ideas)

        # Process each conversation idea for the current doc file
        with ThreadPoolExecutor(max_workers=idea_workers) as executor:
            futures = [executor.submit(build_dataset_line, model, idea, sandbox, predecessor_sandbox) for idea in ideas]
            for future in as_completed(futures):
                dataset_line = future.result()
                if dataset_line is None:
                    continue

                append_dataset_line(dataset_line, output_path)
                if preview:
                    with output_file_lock:
                        print_dataset_line(dataset_line)

    try:
        # Process each doc file
        with ThreadPoolExecutor(max_workers=file_workers) as executor:
            futures = [executor.submit(process_doc, doc_path) for doc_path in input_docs]
            for future in tqdm(as_completed(futures), total=len(input_docs), desc="Doc files"):
                future.result()
    finally:
        logger.info("Cleaning up sandbox containers...")
        removed_count = remove_leftover_containers()
        logger.info("Removed %d leftover sandbox containers", removed_count)
