"""inspect_ai task scoring generated solutions for version-specific Python features."""

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample, json_dataset
from inspect_ai.scorer import Score, Scorer, Target, accuracy, grouped, scorer, stderr
from inspect_ai.solver import TaskState, generate
from inspect_ai.util import ExecResult, sandbox

from satyrn.trainer.unsloth.rl.code_tester import (
    VERIFY_TIMEOUT,
    find_code,
    find_interpreter,
    get_predecessor_python_version,
    make_test_programs,
    pass_fraction,
)

DATASETS_DIR = Path(__file__).resolve().parents[7] / "datasets"
EVAL_SETS = [
    str(DATASETS_DIR / "python3.14/eval.jsonl"),
    str(DATASETS_DIR / "python3.15/eval.jsonl"),
]
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
    for version in versions:
        find_interpreter(version)

    return Task(
        dataset=dataset,
        solver=generate(),
        scorer=verify(),
        sandbox="local",
    )


@scorer(
    metrics=[
        accuracy(),
        stderr(),
        grouped(accuracy(), "python_version", all=False, name_template="py{group_name}"),
        grouped(accuracy(), "pep", all=False),
    ]
)
def verify() -> Scorer:
    """Score each sample as the fraction of its test cases that pass."""

    async def score(state: TaskState, target: Target) -> Score:
        answer = find_code(state.output.completion)
        value, explanation = await score_version_specific_code(
            answer, state.metadata["test_cases"], state.metadata["python_version"]
        )
        return Score(value=value, answer=answer, explanation=explanation)

    return score


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


async def run_test_programs(interpreter: str, programs: list[str]) -> list[ExecResult]:
    """Run each program on interpreter in the inspect sandbox and return the results in order."""
    results = []
    for program in programs:
        try:
            results.append(await sandbox().exec(cmd=[interpreter, "-"], input=program, timeout=VERIFY_TIMEOUT))
        except TimeoutError:
            results.append(ExecResult(False, 1, "", "Verification timed out."))
    return results


async def score_version_specific_code(answer: str, test_cases: list[dict], python_version: str) -> tuple[float, str]:
    """Return (test-pass fraction on python_version, explanation); (0.0, ...) if not version-specific."""
    programs = make_test_programs(answer, test_cases)
    predecessor = get_predecessor_python_version(python_version)

    predecessor_results = await run_test_programs(find_interpreter(predecessor), programs)
    predecessor_passing = sum(result.success for result in predecessor_results)
    if predecessor_passing:
        return 0.0, f"{predecessor_passing} test cases pass on Python {predecessor}; not version-specific."

    target_results = await run_test_programs(find_interpreter(python_version), programs)
    return pass_fraction(test_cases, target_results)
