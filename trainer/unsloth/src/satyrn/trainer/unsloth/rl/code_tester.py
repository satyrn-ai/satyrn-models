"""Run generated solutions against version-specific test cases."""

import re
import subprocess
from functools import lru_cache

VERIFY_TIMEOUT = 30


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


def make_test_programs(answer_code: str, test_cases: list[dict]) -> list[str]:
    """Return one runnable program per test case: answer followed by its test code."""
    return [f"{answer_code.rstrip()}\n\n{test_case['test_code'].rstrip()}\n" for test_case in test_cases]


def pass_fraction(test_cases: list[dict], results: list) -> tuple[float, str]:
    """Return (fraction of results that exited 0, failure lines joined or success message).

    Each result needs .returncode and .stderr (subprocess.CompletedProcess or inspect ExecResult).
    """
    failures = [
        f"{test_case['name']}: {result.stderr.strip()}"
        for test_case, result in zip(test_cases, results, strict=True)
        if result.returncode != 0
    ]
    fraction = (len(test_cases) - len(failures)) / len(test_cases)
    return fraction, "\n".join(failures) or "All test cases passed."


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


def score_version_specific_code(answer: str, test_cases: list[dict], python_version: str) -> float:
    """Return the test-pass fraction on python_version, or 0.0 when the code is not version-specific."""
    programs = make_test_programs(answer, test_cases)
    predecessor = get_predecessor_python_version(python_version)

    predecessor_results = run_test_programs(find_interpreter(predecessor), programs)
    if any(result.returncode == 0 for result in predecessor_results):
        return 0.0

    target_results = run_test_programs(find_interpreter(python_version), programs)
    fraction, _ = pass_fraction(test_cases, target_results)
    return fraction
