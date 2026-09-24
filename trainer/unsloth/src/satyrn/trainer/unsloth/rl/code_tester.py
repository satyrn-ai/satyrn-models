"""Run generated solutions against version-specific test cases."""

import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache

VERIFY_TIMEOUT = 30


@dataclass(frozen=True)
class TestCase:
    name: str
    test_code: str


def find_code(completion: str) -> str:
    """Return the first fenced code block, or the whole completion when unfenced."""
    match = re.search(r"```(?:python)?\n(.*?)```", completion, re.DOTALL)
    return match.group(1) if match else completion


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


def make_test_programs(answer_code: str, test_cases: list[TestCase]) -> list[str]:
    """Return one runnable program per test case: answer followed by its test code."""
    return [f"{answer_code.rstrip()}\n\n{test_case.test_code.rstrip()}\n" for test_case in test_cases]


def score_test_results(
    test_cases: list[TestCase], target_version_results: list, predecessor_results: list
) -> tuple[float, str]:
    """Return (share of tests passing only on the target version, explanation of the others).

    Results need .returncode and .stderr (subprocess.CompletedProcess or inspect ExecResult).
    """
    passed_only_on_target_version = 0
    explanations = []
    for test_case, target_version, predecessor in zip(
        test_cases, target_version_results, predecessor_results, strict=True
    ):
        passed_on_target_version = target_version.returncode == 0
        passed_on_predecessor = predecessor.returncode == 0
        if passed_on_target_version and not passed_on_predecessor:
            passed_only_on_target_version += 1
        elif passed_on_target_version:
            explanations.append(f"{test_case.name}: also passes on the predecessor version")
        else:
            explanations.append(f"{test_case.name}: {target_version.stderr.strip()}")
    return passed_only_on_target_version / len(test_cases), "\n".join(explanations) or "All test cases passed."


def run_test_programs(interpreter: str, programs: list[str]) -> list[subprocess.CompletedProcess]:
    """Run each program on interpreter with subprocess and return the results in order."""
    results = []
    for program in programs:
        try:
            results.append(
                subprocess.run(
                    [interpreter, "-"],
                    input=program,
                    capture_output=True,
                    text=True,
                    timeout=VERIFY_TIMEOUT,
                )
            )
        except subprocess.TimeoutExpired:
            results.append(subprocess.CompletedProcess([interpreter, "-"], 1, "", "Verification timed out."))
    return results


def score_version_specific_code(answer: str, test_cases: list[TestCase], python_version: str) -> float:
    """Return the share of tests that pass on python_version but not on its predecessor."""
    programs = make_test_programs(answer, test_cases)
    predecessor = get_predecessor_python_version(python_version)

    predecessor_results = run_test_programs(find_interpreter(predecessor), programs)
    target_version_results = run_test_programs(find_interpreter(python_version), programs)
    score, _ = score_test_results(test_cases, target_version_results, predecessor_results)
    return score
