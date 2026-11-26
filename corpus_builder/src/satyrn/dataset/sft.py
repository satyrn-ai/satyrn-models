"""Supervised Fine-Tuning (SFT) dataset generation."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, get_llm
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    Idea,
    append_dataset_line,
    append_progress,
    find_version_check,
    load_ideas,
    output_file_lock,
    pep_identifier,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_dataset_line
from satyrn.dataset.utils.sandbox import Sandbox, get_predecessor_python_version, remove_leftover_containers

logger = logging.getLogger(__name__)


def generate_code_block(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> dict:
    """Return a verified code block and its expected output."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Write the `code`
block described by this idea:

{idea.description}

Write a complete, realistic, self-contained script (~15-35 lines when natural) that exercises the new feature across realistic inputs or edge cases rather than a minimal toy snippet.
Avoid comments that just restate the code.
In `expected_output` state exactly what running the code outputs, whether to stdout or stderr.

{PYTHON_CODE_RULES}
    """
    schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "expected_output": {"type": "string"},
        },
        "required": ["code", "expected_output"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)

    max_attempts = 3
    for attempt in range(max_attempts):
        code_block = model.generate(prompt, context, thinking=True)
        rejection = find_version_check(code_block["code"])
        if rejection:
            prompt += f"\n\nYour previous code:\n{code_block['code']}\n\n{rejection}\n"
            continue

        verified, actual_output = verify_code_block(
            code_block["code"], code_block["expected_output"], sandbox, predecessor_sandbox
        )
        if verified:
            return code_block

        if actual_output.strip() != code_block["expected_output"].strip():
            judgement = judge_code_block(model, idea, code_block, actual_output)
            if not judgement["passed"]:
                # Allow the model to retry code/output generation
                # Intentionally leave actual_output out of the retry prompt, so model doesn't just copy it.
                prompt += f"""\n
Your previous code:
{code_block["code"]}

Predicted output:
{code_block["expected_output"]}

That prediction did not match the code's actual output.

{judgement["judgement"]}

Fix the code so it actually does what the idea describes, and predict its real output again.
        """
                logger.warning(
                    "Attempt %d/%d: code block did not verify. Prompting model to retry.", attempt + 1, max_attempts
                )
                continue

            logger.info("Judge accepted mismatched output: %s", judgement["judgement"])
            code_block["expected_output"] = actual_output
            verified, actual_output = verify_code_block(
                code_block["code"], code_block["expected_output"], sandbox, predecessor_sandbox
            )
            if verified:
                return code_block

        prompt += f"""\n
Your previous code:
{code_block["code"]}

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
    """Return a user prompt, assistant response, and reasoning trace for code_block."""
    prompt = f"""
Example:

Code:
```python
NOT_FOUND = sentinel("NOT_FOUND")

def find_first_positive(values):
    for value in values:
        if value > 0:
            return value
    return NOT_FOUND

result = find_first_positive([-1, -2])
if result is NOT_FOUND:
    print("not found")
```

Expected output:
not found

JSON response:
{{
  "prompt": "How can I use the new built-in sentinel in Python 3.15 to represent a 'not found' condition when returning from a function?",
  "explanation": "`sentinel(name, /, repr=None)` creates a unique placeholder object that you can return for a missing result instead of `None` or a magic number like `-1`. Because sentinels only equal themselves, compare them with an identity check (`result is NOT_FOUND`) rather than `==`.",
  "trace": "`sentinel()` was added in Python 3.15 as a built-in (PEP 661), so no import is needed. Using a unique sentinel object for 'not found' avoids overloading `None` (which can be a valid value) or magic numbers like `-1`, and sentinel objects are compared by identity with `is`.\\n\\nI need to define a module-level sentinel, return it from a search function when no item matches, and check the result with `is`.\\n\\n1. `NOT_FOUND = sentinel(\\"NOT_FOUND\\")` creates a new sentinel object named `NOT_FOUND` at module level.\\n2. Define `find_first_positive(values)` to iterate over `values` and return the first element greater than `0`.\\n3. Calling `find_first_positive([-1, -2])` starts the loop; neither `-1` nor `-2` is greater than `0`, so the loop completes without returning.\\n4. The function falls through to `return NOT_FOUND`, returning the sentinel object.\\n5. `result` is bound to that returned `NOT_FOUND` sentinel object.\\n6. Check `if result is NOT_FOUND:`, performing an identity check that evaluates to `True`.\\n7. `print(\\"not found\\")` writes `not found` to stdout."
}}

---

The attached document describes a change in Python version {idea.python_version}. A verified code
block demonstrates this idea:

{idea.description}

Code:
```python
{code_block["code"]}
```

Expected output:
{code_block["expected_output"]}

Write:
1. `prompt`: a natural user question that this code answers.
2. `explanation`: 1 short paragraph of human-facing prose (2-3 sentences, ~180-350 characters, never exceeding
   450 characters) that answers the user's question directly, stating the Python feature/API behavior and any
   key gotchas. Do not start with "Python", "In Python", or "With Python". Never narrate the example script
   line by line (never write "The snippet creates...", "The code prints...", "This script imports...", or
   "This example demonstrates..."). Do not include pre-version legacy workarounds unless the user prompt asks
   for them, and do not include code blocks or markdown fences.
3. `trace`: internal reasoning (`<think>` content) targeting 900-1,300 characters across 3 parts separated by
   blank lines (`\\n\\n`):
   - Part 1 (Python API exploration paragraph): pinpoint the exact feature/PEP, built-in or module location,
     signature, and behavioral constraints or pitfalls relevant to this task, mentioning the Python version
     naturally inside a sentence when relevant. Never start `trace` with "Python", "In Python", or "With
     Python", and never include unrelated API details, PEP history, or rejected alternatives.
   - Part 2 (one-sentence problem plan): state in one first-person sentence ("I need to...") what the snippet
     will build and verify.
   - Part 3 (numbered step-by-step walkthrough, no heading): numbered prose steps (`1.`, `2.`, ...) explaining
     what each step of the solution does and how execution flows from setup through to the final result.
   Use first-person ("I need to...", "Let me...") for Part 2, and direct code-and-runtime phrasing for Part 3.
   Never use third-person ("The user is asking..."), meta-commentary ("the attached document", "the idea",
   "training example"), or repeat "I <verb>" on every numbered line. Do not include markdown code blocks
   (```) or `<think>` tags, and stay strictly consistent with `prompt`, `explanation`, `code`, and
   `expected_output`.
    """
    schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "explanation": {"type": "string"},
            "trace": {"type": "string"},
        },
        "required": ["prompt", "explanation", "trace"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)
    result = model.generate(prompt, context)

    response = f"{result['explanation']}\n\n```python\n{code_block['code']}\n```"
    return {"prompt": result["prompt"], "response": response, "trace": result["trace"]}


def judge_conversation(model: Model, idea: Idea, code_block: dict, conversation: dict) -> None:
    """Raise ValueError if conversation is not a good SFT training example."""
    messages = [
        {"role": "user", "content": conversation["prompt"]},
        {"role": "assistant", "content": conversation["response"]},
    ]
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. The following
conversation and reasoning trace were generated to teach this idea as a fine-tuning example.

Idea:
{idea.description}

Code:
{code_block["code"]}

Actual output when the code runs:
{code_block["expected_output"]}

Reasoning trace:
{conversation["trace"]}

Conversation:
{json.dumps(messages, indent=2)}

Decide whether this conversation is a good training example for fine-tuning a model on Python
{idea.python_version}, and set `passed` to true only if all of these hold:

- The messages follow logically from each other: the assistant's response actually answers the
  user's message.
- The explanation before the code block is concise (1 paragraph) and does not narrate the script
  line by line or pad with unrequested legacy workarounds.
- The reasoning trace is consistent with the code and actual output, follows the 3-part structure
  (API exploration, one-sentence "I need to..." plan, numbered execution walkthrough), and contains
  no markdown code fences or `<think>` tags.
- The code is not contrived to work around sandbox limitations (e.g. avoiding real file I/O, network
  access, or subprocesses only because a sandbox can't run them, rather than because the idea calls
  for it).
- The example teaches idea correctly and reads like something a real user would ask.

Set `passed` to false if any of these is true:

- The messages are malformed or don't logically match each other.
- The explanation is bloated/multi-paragraph or narrates the test script line by line.
- The reasoning trace contradicts the code/output, uses third-person ("The user is asking..."), or
  includes code fences or `<think>` tags.
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
        "trace": conversation["trace"],
        "expected_output": code_block["expected_output"],
    }


@click.command("sft")
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
@click.option("--limit", type=click.IntRange(min=1), default=None, help="Generate only the first N ideas.")
def main(
    ideas_path: Path,
    output_path: Path,
    python_version: str,
    preview: bool,
    workers: int,
    limit: int | None,
) -> None:
    """Generate an SFT dataset for every loaded idea."""
    model = get_llm("deepseek", os.environ.get("LLM_MODEL_NAME", "deepseek-v4-flash"))
    sandbox = Sandbox(python_version)
    predecessor_sandbox = Sandbox(get_predecessor_python_version(python_version))

    prepare_output_file(output_path)
    ideas = load_ideas(ideas_path, output_path)[:limit]
    logger.info("Loaded %d ideas", len(ideas))

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(build_dataset_line, model, idea, sandbox, predecessor_sandbox): idea for idea in ideas
            }
            for future in tqdm(as_completed(futures), total=len(ideas), desc="Ideas"):
                idea = futures[future]
                dataset_line = future.result()
                append_progress(idea, dataset_line, output_path)
                if dataset_line is None:
                    continue
                append_dataset_line(dataset_line, output_path)
                if preview:
                    with output_file_lock:
                        print_dataset_line(dataset_line)
    finally:
        logger.info("Cleaning up sandbox containers...")
        removed_count = remove_leftover_containers()
        logger.info("Removed %d leftover sandbox containers", removed_count)
