"""inspect_ai task scoring generated solutions for version-specific Python features."""

import re
import subprocess
from functools import lru_cache
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample, json_dataset
from inspect_ai.scorer import Score, Scorer, Target, accuracy, grouped, scorer, stderr
from inspect_ai.solver import TaskState, generate
from inspect_ai.util import ExecResult, sandbox

DATASETS_DIR = Path(__file__).resolve().parents[7] / "datasets"
EVAL_SETS = [
    str(DATASETS_DIR / "python3.14/eval.jsonl"),
    str(DATASETS_DIR / "python3.15/eval.jsonl"),
]
VERIFY_TIMEOUT = 30
NO_PEP = "no-pep"

INSTRUCTION = """
Write the function described below. Your response should only contain the code
for this function and any imports it needs.\n
"""


@task
def python_eval() -> Task:
    """Build the eval task over one or more problem JSONL files."""
    dataset = load_dataset(EVAL_SETS)
    versions = {sample.metadata["python_version"] for sample in dataset}
    versions |= {get_predecessor_python_version(version) for version in versions}
    interpreters = {version: find_interpreter(version) for version in versions}

    return Task(
        dataset=dataset,
        solver=generate(),
        scorer=verify(interpreters),
        sandbox="local",
    )


def load_dataset(dataset_paths: list[str]) -> MemoryDataset:
    """Read every JSONL file into one dataset."""
    samples = []
    for dataset_path in dataset_paths:
        for line_number, sample in enumerate(json_dataset(dataset_path, record_to_sample), start=1):
            sample.id = f"{sample.id}:{line_number}"
            samples.append(sample)
    return MemoryDataset(samples)


def record_to_sample(record: dict) -> Sample:
    """Turn one problem into a Sample."""
    metadata = record["metadata"]
    return Sample(
        id=f"{metadata['source_document']}:{metadata['entry_point']}",
        input=INSTRUCTION + record["prompt"],
        target=record["solution"],
        metadata={
            "test_cases": record["test_cases"],
            "entry_point": metadata["entry_point"],
            "python_version": metadata["python_version"],
            "pep": metadata["pep"] or NO_PEP,
        },
    )


def get_predecessor_python_version(python_version: str) -> str:
    """Return the Python feature release immediately before python_version."""
    major, minor, *_ = python_version.split(".")
    return f"{major}.{int(minor) - 1}"


@lru_cache
def find_interpreter(python_version: str) -> str:
    """Return the interpreter uv resolves for python_version."""
    result = subprocess.run(
        ["uv", "python", "find", python_version],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            f"No Python {python_version} interpreter: {result.stderr.strip()}\n"
            f"Install it with: uv python install {python_version}"
        )
    return result.stdout.strip()


async def failing_tests(interpreter: str, answer: str, test_cases: list[dict]) -> list[str]:
    """Return a failure line for each test case that does not pass under interpreter."""
    failures = []
    for test_case in test_cases:
        program = f"{answer.rstrip()}\n\n{test_case['test_code'].rstrip()}\n"
        try:
            result = await sandbox().exec(
                cmd=[interpreter, "-"],
                input=program,
                timeout=VERIFY_TIMEOUT,
            )
        except TimeoutError:
            result = ExecResult(False, 1, "", "Verification timed out.")
        if not result.success:
            failures.append(f"{test_case['name']}: {result.stderr.strip()}")
    return failures


@scorer(
    metrics=[
        accuracy(),
        stderr(),
        grouped(accuracy(), "python_version", all=False, name_template="py{group_name}"),
        grouped(accuracy(), "pep", all=False),
    ]
)
def verify(interpreters: dict[str, str]) -> Scorer:
    """Score each sample as the fraction of its test cases that pass."""

    async def score(state: TaskState, target: Target) -> Score:
        answer = find_code(state.output.completion)
        version = state.metadata["python_version"]
        predecessor = get_predecessor_python_version(version)
        test_cases = state.metadata["test_cases"]

        predecessor_failures = await failing_tests(interpreters[predecessor], answer, test_cases)
        predecessor_passing = len(test_cases) - len(predecessor_failures)
        if predecessor_passing:
            return Score(
                value=0.0,
                answer=answer,
                explanation=f"{predecessor_passing} test cases pass on Python {predecessor}; not version-specific.",
            )

        failures = await failing_tests(interpreters[version], answer, test_cases)
        return Score(
            value=(len(test_cases) - len(failures)) / len(test_cases),
            answer=answer,
            explanation="\n".join(failures) or "All test cases passed.",
        )

    return score


def find_code(completion: str) -> str:
    """Return the first fenced code block, or the whole completion when unfenced."""
    match = re.search(r"```(?:python)?\n(.*?)```", completion, re.DOTALL)
    return match.group(1) if match else completion
