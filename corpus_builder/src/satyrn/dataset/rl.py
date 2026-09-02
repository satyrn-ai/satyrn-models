"""Generate testable Python evaluation and Reinforcement Learning datasets."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self

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

PASS_MARKER = "__SATYRN_TEST_PASSED__"
MIN_TEST_CASES = 5
MAX_TEST_CASES = 12


@dataclass(frozen=True)
class TestCase:
    """One independently executable test case for a generated problem."""

    name: str
    input: str
    expected_output: str
    test_code: str

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        """Construct a test case from the model's JSON-compatible response."""
        return cls(
            name=value["name"],
            input=value["input"],
            expected_output=value["expected_output"],
            test_code=value["test_code"],
        )


@dataclass(frozen=True)
class Problem:
    """A generated programming problem and its reference solution."""

    prompt: str
    entry_point: str
    solution: str
    test_cases: list[TestCase]

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        """Construct a typed problem from the model's JSON-compatible response."""
        return cls(
            prompt=value["prompt"],
            entry_point=value["entry_point"],
            solution=value["solution"],
            test_cases=[TestCase.from_dict(test_case) for test_case in value["test_cases"]],
        )

    def to_dict(self) -> dict:
        """Return the problem in its JSON-compatible dataset representation."""
        return asdict(self)

    @classmethod
    def get_schema(cls) -> dict:
        """Reuturn LLM response compatible schema."""
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "entry_point": {"type": "string"},
                "solution": {"type": "string"},
                "test_cases": {
                    "type": "array",
                    "minItems": MIN_TEST_CASES,
                    "maxItems": MAX_TEST_CASES,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "input": {"type": "string"},
                            "expected_output": {"type": "string"},
                            "test_code": {"type": "string"},
                        },
                        "required": ["name", "input", "expected_output", "test_code"],
                    },
                },
            },
            "required": ["prompt", "entry_point", "solution", "test_cases"],
        }


@dataclass(frozen=True)
class TestResult:
    """The result of running one independently scored test case."""

    name: str
    passed: bool
    output: str


@dataclass(frozen=True)
class EvaluationResult:
    """Per-test results and their fractional aggregate score."""

    score: float
    tests: list[TestResult]


@dataclass(frozen=True)
class VerificationResult:
    """Target and predecessor results for a generated reference solution."""

    passed: bool
    target: EvaluationResult
    predecessor: EvaluationResult | None
    reason: str


def evaluate_solution(solution: str, test_cases: list[TestCase], sandbox: Sandbox) -> EvaluationResult:
    """Run each test independently and return passed/total as a score from 0 to 1."""
    if not test_cases:
        raise ValueError("At least one test case is required")

    results = []
    for test_case in test_cases:
        program = f"{solution.rstrip()}\n\n{test_case.test_code.rstrip()}\n\nprint({PASS_MARKER!r})\n"
        output = sandbox.run(program)
        marker_is_last_line = output.rstrip().splitlines()[-1:] == [PASS_MARKER]
        results.append(TestResult(test_case.name, marker_is_last_line, output))

    passed_count = sum(result.passed for result in results)
    return EvaluationResult(passed_count / len(results), results)


def verify_problem(
    solution: str,
    test_cases: list[TestCase],
    sandbox: Sandbox,
    predecessor_sandbox: Sandbox,
) -> VerificationResult:
    """Require all target tests to pass and reject a suite that also passes on the predecessor."""
    target = evaluate_solution(solution, test_cases, sandbox)
    if target.score != 1.0:
        return VerificationResult(False, target, None, "reference solution failed target-version tests")

    predecessor = evaluate_solution(solution, test_cases, predecessor_sandbox)
    if predecessor.score == 1.0:
        return VerificationResult(False, target, predecessor, "suite also passed on the predecessor version")

    return VerificationResult(True, target, predecessor, "verified")


def _validate_problem_structure(problem: Problem) -> None:
    """Reject vacuous, duplicated, or disconnected generated tests."""
    test_cases = problem.test_cases
    if not MIN_TEST_CASES <= len(test_cases) <= MAX_TEST_CASES:
        raise ValueError(f"Expected {MIN_TEST_CASES}-{MAX_TEST_CASES} test cases")
    if problem.entry_point not in problem.prompt:
        raise ValueError("The prompt does not name the entry point")

    names = [test_case.name.strip() for test_case in test_cases]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Test case names must be non-empty and unique")
    for test_case in test_cases:
        if not test_case.input.strip() or not test_case.expected_output.strip():
            raise ValueError("Every test needs a documented input and expected output")
        if "assert" not in test_case.test_code:
            raise ValueError(f"Test {test_case.name!r} does not contain an assertion")
        if problem.entry_point not in test_case.test_code:
            raise ValueError(f"Test {test_case.name!r} does not call the entry point")


def judge_problem(model: Model, idea: Idea, problem: Problem) -> dict:
    """Return an LLM verdict on the task's fidelity, coverage, and test quality."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Review this
generated programming task and its already-executed reference solution:

Idea:
{idea.description}

Task:
{json.dumps(problem.to_dict(), indent=2)}

Set `passed` to true only if all of these hold:

- The task accurately and substantially tests the documented Python {idea.python_version} API or behavior.
- The prompt is self-contained and includes a clear callable signature and return contract.
- The solution is a natural implementation, not code contrived to satisfy the visible tests.
- Every test's documented input and expected output agree with its assertion code.
- The tests are independent, non-vacuous, deterministic, and collectively cover normal behavior,
  boundaries, empty or unusual inputs where applicable, errors where applicable, and interactions
  between important options.
- Each test checks one useful behavior so passed-tests / total-tests is a meaningful partial score.

In `judgement`, explain any concrete weakness. Do not pass a task whose tests merely repeat the same
case or whose assertions could pass without exercising the entry point.
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


def generate_problem(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> Problem:
    """Return a reference-solved problem with a verified, independently scored test suite."""
    prompt = f"""
The attached document describes a change in Python version {idea.python_version}. Create a small
programming task for this idea:

{idea.description}

The task is for evaluation and reinforcement learning, not a tutorial. It should thoroughly test
understanding of the new Python API rather than algorithmic difficulty.

- In `prompt`, describe the problem, include the exact signature of one callable entry point, and
  specify its return value. Do not reveal the solution.
- In `entry_point`, give only the callable's name.
- In `solution`, provide a complete reference implementation defining that callable.
- Provide between {MIN_TEST_CASES} and {MAX_TEST_CASES} independent test cases covering ordinary
  behavior and every meaningful edge case in this task.
- Each test case must have a unique descriptive `name`, a human-readable Python `input`, its Python
  `expected_output`, and executable `test_code` containing an assertion that calls the entry point.
- A test must not depend on another test, repeat the solution, inspect source code, or use a vacuous
  assertion. Keep setup inside that test's `test_code`.
- The solution and tests must be deterministic, use only the Python standard library, perform no
  network access, and finish quickly.
- The task must depend on behavior introduced in Python {idea.python_version}; the complete reference
  solution and test suite must not pass unchanged on the preceding Python feature release.

{PYTHON_CODE_RULES}
    """
    context = Context()
    context.system_prompt = SYSTEM_PROMPT
    context.add(idea.doc_path.name, idea.doc_path)
    context.set_json_schema(Problem.get_schema())

    max_attempts = 3
    for attempt in range(max_attempts):
        generated_problem = model.generate(prompt, context, thinking=True)
        if not isinstance(generated_problem, dict):
            raise TypeError("Problem-writing model did not return a JSON object")
        problem = Problem.from_dict(generated_problem)
        try:
            _validate_problem_structure(problem)
        except ValueError as error:
            verification_feedback = str(error)
        else:
            verification = verify_problem(problem.solution, problem.test_cases, sandbox, predecessor_sandbox)
            if verification.passed:
                judgement = judge_problem(model, idea, problem)
                if judgement["passed"]:
                    return problem
                verification_feedback = judgement["judgement"]
            elif verification.predecessor is not None and verification.predecessor.score == 1.0:
                verification_feedback = (
                    f"The complete suite also passed on Python {predecessor_sandbox.python_version}; "
                    f"make the task specifically exercise Python {sandbox.python_version} behavior."
                )
            else:
                failed_names = [result.name for result in verification.target.tests if not result.passed]
                verification_feedback = f"The reference solution failed target tests: {failed_names}."

        prompt += f"""\n
Your previous task was rejected for this reason:
{verification_feedback}

Generate a corrected complete task and test suite.
        """
        logger.warning(
            "Attempt %d/%d: generated task did not verify: %s", attempt + 1, max_attempts, verification_feedback
        )

    raise ValueError(f"Could not generate a verified task for idea: {idea.description}")


def build_dataset_line(model: Model, idea: Idea, sandbox: Sandbox, predecessor_sandbox: Sandbox) -> dict | None:
    """Return one verified evaluation/RL row for idea, or None when generation fails."""
    try:
        problem = generate_problem(model, idea, sandbox, predecessor_sandbox)
    except Exception as error:
        logger.error("Skipping idea: %s", error)
        return None

    serialized_problem = problem.to_dict()
    return {
        "prompt": problem.prompt,
        "test_cases": serialized_problem["test_cases"],
        "solution": problem.solution,
        "metadata": {
            "source_document": idea.doc_path.name,
            "pep": pep_identifier(idea.doc_path),
            "python_version": idea.python_version,
            "idea": idea.description,
            "entry_point": problem.entry_point,
            "test_count": len(problem.test_cases),
        },
    }


@click.command("rl")
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
    """Generate a testable evaluation and Reinforcement Learning dataset."""
    model = get_llm("deepseek", "deepseek-v4-flash")
    sandbox = Sandbox(python_version)
    predecessor_sandbox = Sandbox(get_predecessor_python_version(python_version))
    file_workers, idea_workers = split_workers(workers)

    prepare_output_file(output_path)
    input_docs = collect_input_docs(input_path)

    def process_doc(doc_path: Path) -> None:
        """Generate and write every testable task for one source document."""
        ideas = generate_ideas(model, doc_path, python_version)
        logger.info("Generated %d ideas for %s", len(ideas), doc_path.name)
        if preview:
            print_ideas(ideas)

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
        with ThreadPoolExecutor(max_workers=file_workers) as executor:
            futures = [executor.submit(process_doc, doc_path) for doc_path in input_docs]
            for future in tqdm(as_completed(futures), total=len(input_docs), desc="Doc files"):
                future.result()
    finally:
        logger.info("Cleaning up sandbox containers...")
        removed_count = remove_leftover_containers()
        logger.info("Removed %d leftover sandbox containers", removed_count)
