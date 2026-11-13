"""Agentic multi-turn Supervised Fine-Tuning (SFT) dataset generation."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import click
from tqdm import tqdm

from satyrn.dataset.llm.context import Context
from satyrn.dataset.llm.models import Model, get_llm
from satyrn.dataset.pi_harness.harness import File, PiHarness, build_pi_image
from satyrn.dataset.utils.generation import (
    PYTHON_CODE_RULES,
    SYSTEM_PROMPT,
    Idea,
    append_dataset_line,
    load_ideas,
    output_file_lock,
    pep_identifier,
    prepare_output_file,
)
from satyrn.dataset.utils.preview import print_dataset_line
from satyrn.dataset.utils.sandbox import Sandbox, get_predecessor_python_version, remove_leftover_containers

logger = logging.getLogger(__name__)

PASS_MARKER = "__SATYRN_TEST_PASSED__"
MIN_INITIAL_FILE_LENGTH = 20


@dataclass(frozen=True)
class Task:
    """A coding task on one file: the agent's prompt, the initial file, its solution and tests for the solution."""

    prompt: str
    initial: File | None
    solution: File
    tests: str


def run_tests(code: str, tests: str, sandbox: Sandbox) -> tuple[bool, str]:
    """Run tests appended to code in sandbox. Return whether they passed and the output."""
    output = sandbox.run(f"{code.rstrip()}\n\n{tests.rstrip()}\n\nprint({PASS_MARKER!r})\n")
    return output.rstrip().splitlines()[-1:] == [PASS_MARKER], output


def verify_code(code: str, tests: str, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> str | None:
    """Return why the tests do not pass on code in sandbox and fail in predecessor_sandbox, or None."""
    passed, output = run_tests(code, tests, sandbox)
    if not passed:
        return f"The tests failed under Python {sandbox.python_version}:\n{output}"

    passed, _ = run_tests(code, tests, predecessor_sandbox)
    if passed:
        return (
            f"The tests also passed under Python {predecessor_sandbox.python_version}, "
            f"so the code does not depend on Python {sandbox.python_version}."
        )
    return None


def generate_task(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> Task:
    """Return a verified task for idea, generated from its source document."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Create a task for
a coding assistant working in a workspace with at most one Python file, as described by this idea:

{idea.description}

- In `file_name`, give the name of the Python file.
- In `initial`, give the file's content before the task, or an empty string if the task creates it.
  It is a realistic module of at least {MIN_INITIAL_FILE_LENGTH} lines, and its other code relates to
  the module's purpose.
- In `solution`, give the file's complete content once the task is done.
- In `tests`, write plain `assert` statements that pass when appended to `solution` and fail on the
  preceding Python feature release. They check return values or raised exceptions.
- The tests use only names the `prompt` mentions and standard library modules they import themselves.
  They never import the file under test. Each behaviour they check can be triggered through the public
  interface, and building a test input does not itself raise the exception being checked.
- The tests are deterministic, use only the standard library and finish quickly.
- In `prompt`, write the request a user sends to the assistant. Name the file and the signatures of
  the functions to change or create, and follow the rules for `prompt` below.

Rules for `prompt`:

When writing `prompt`, you are the user of the coding assistant. You want the assistant to turn
`initial` into `solution`, or to create `solution` when `initial` is empty, but you do not tell it
how to do that or how to test it.

- `prompt` sounds natural, like something a user would ask for: a short instruction, a question or a
  problem report. In its own words, it says what the user wants, why, and the behaviour the tests
  check, without listing rules like a specification.
- The user may know nothing about the new Python features. The assistant also receives the attached
  document and has to work them out from it.
- `prompt` does not repeat code that the assistant can read in `initial`.
- The user does not describe implementation steps and does not mention tests, which do not exist for
  the user.

{PYTHON_CODE_RULES}
    """
    schema = {
        "type": "object",
        "properties": {
            "file_name": {"type": "string"},
            "initial": {"type": "string"},
            "prompt": {"type": "string"},
            "solution": {"type": "string"},
            "tests": {"type": "string"},
        },
        "required": ["file_name", "initial", "prompt", "solution", "tests"],
    }
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(schema)

    max_attempts = 3
    for attempt in range(max_attempts):
        response = model.generate(prompt, context, thinking=True)
        initial = File(response["file_name"], response["initial"]) if response["initial"] else None
        solution = File(response["file_name"], response["solution"])
        task = Task(response["prompt"], initial, solution, response["tests"])
        rejection = verify_code(solution.content, task.tests, sandbox, predecessor_sandbox)
        if rejection is None:
            logger.debug(
                "Attempt %d/%d: task verified on Python %s, fails on %s: %s",
                attempt + 1,
                max_attempts,
                sandbox.python_version,
                predecessor_sandbox.python_version,
                idea.description,
            )
            return task

        prompt += f"""\n
Your previous task:
{json.dumps(response, indent=2)}

It was rejected. {rejection}

Fix the task and give it again.
        """
        logger.warning("Attempt %d/%d: task did not verify. %s", attempt + 1, max_attempts, rejection)

    raise ValueError(f"Could not generate a verified task for idea: {idea.description}")


def run_agent(agent_model: str, idea: Idea, task: Task) -> tuple[dict, str | None]:
    """Prime Pi with idea's source document and run task. Return the session payload and the agent's file."""
    workspace = [task.initial] if task.initial else []
    pi = PiHarness(agent_model, workspace)
    try:
        priming_prompt = (
            "Here is a new Python feature. Read it; you will use it in the next problem. Reply only 'ready'."
        )
        priming_message = f"{priming_prompt}\n\n{idea.doc_path.read_text()}"
        pi.agent_run(priming_message)
        logger.debug("Running agent on %s", task.solution.name)
        pi.agent_run(task.prompt)
        logger.debug("Agent finished on %s", task.solution.name)
        payload = json.loads(pi.render_session())
        agent_file = pi.workspace_dir / task.solution.name
        agent_code = agent_file.read_text() if agent_file.exists() else None
        return payload, agent_code
    finally:
        pi.stop()


def extract_session(messages: list[dict], task_prompt: str) -> tuple[list[dict], list[dict]]:
    """Return the system and task messages, and the agent's turns with parsed tool-call arguments."""
    task_index = next(
        index
        for index, message in enumerate(messages)
        if message["role"] == "user" and message["content"][0]["text"] == task_prompt
    )
    task_message = {"role": "user", "content": task_prompt}
    agent_turns = messages[task_index + 1 : -1]
    for message in agent_turns:
        for tool_call in message.get("tool_calls") or []:
            tool_call["function"]["arguments"] = json.loads(tool_call["function"]["arguments"])
    return [messages[0], task_message], agent_turns


def build_dataset_line(
    model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox, agent_model: str
) -> dict | None:
    """Return a dataset line for idea, or None if it was rejected."""
    try:
        task = generate_task(model, idea, sandbox, predecessor_sandbox)

        payload, agent_code = run_agent(agent_model, idea, task)
        if agent_code is None:
            raise ValueError(f"The agent did not write {task.solution.name}")

        rejection = verify_code(agent_code, task.tests, sandbox, predecessor_sandbox)
        if rejection is not None:
            raise ValueError(f"The agent's {task.solution.name} did not verify. {rejection}")

        if os.environ["DEEPSEEK_API_KEY"] in json.dumps(payload):
            raise ValueError("The agent session contains the API key")

        prompt, completion = extract_session(payload["messages"], task.prompt)

    except Exception as error:
        logger.warning("Skipping idea: %s", error)
        return None

    return {
        "prompt": prompt,
        "completion": completion,
        "tools": payload["tools"],
        "filename": idea.doc_path.name,
        "pep": pep_identifier(idea.doc_path),
        "python_version": idea.python_version,
        "idea": idea.description,
        "task_file": task.solution.name,
        "initial": task.initial.content if task.initial else "",
        "solution": task.solution.content,
        "agent_solution": agent_code,
        "tests": task.tests,
    }


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
@click.option("--agent-model", default="deepseek/deepseek-flash", show_default=True, help="Pi model of the agent.")
@click.option("--preview", is_flag=True, default=False, help="Print each dataset line after it is saved.")
@click.option("--workers", type=click.IntRange(min=1), default=1, help="Number of lines to generate in parallel.")
def main(
    ideas_path: Path,
    output_path: Path,
    python_version: str,
    agent_model: str,
    preview: bool,
    workers: int,
) -> None:
    """Generate an agentic multi-turn SFT dataset for every loaded idea."""
    model = get_llm("deepseek", os.environ.get("LLM_MODEL_NAME", "deepseek-v4-flash"))
    sandbox = Sandbox(python_version)
    predecessor_sandbox = Sandbox(get_predecessor_python_version(python_version))
    build_pi_image()

    prepare_output_file(output_path)
    ideas = load_ideas(ideas_path, "agentic-sft")
    logger.info("Loaded %d ideas", len(ideas))

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(build_dataset_line, model, idea, sandbox, predecessor_sandbox, agent_model)
                for idea in ideas
            ]
            for future in tqdm(as_completed(futures), total=len(ideas), desc="Ideas"):
                dataset_line = future.result()
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
