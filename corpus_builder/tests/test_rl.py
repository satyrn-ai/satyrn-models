"""Tests for evaluation/RL dataset scoring and verification."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from satyrn.dataset.rl import (
    PASS_MARKER,
    Problem,
    build_dataset_line,
    evaluate_solution,
    verify_problem,
)
from satyrn.dataset.rl import TestCase as RLTestCase
from satyrn.dataset.utils.generation import Idea, pep_identifier


@dataclass
class StubSandbox:
    """Return outputs in order while recording submitted programs."""

    python_version: str
    outputs: list[str]

    def __post_init__(self) -> None:
        self.programs: list[str] = []

    def run(self, code: str) -> str:
        self.programs.append(code)
        return self.outputs[len(self.programs) - 1]


TEST_CASES = [
    RLTestCase(name="zero", input="0", expected_output="0", test_code="assert solve(0) == 0"),
    RLTestCase(name="one", input="1", expected_output="2", test_code="assert solve(1) == 2"),
]


def test_problem_round_trips_through_json_compatible_dict() -> None:
    problem = Problem(
        prompt="Implement solve(value: int) -> int.",
        entry_point="solve",
        solution="def solve(value): return value * 2",
        test_cases=TEST_CASES,
    )

    assert Problem.from_dict(problem.to_dict()) == problem


def test_evaluate_solution_returns_fraction_of_independent_tests() -> None:
    sandbox = StubSandbox("3.15", [f"warning\nstray output\n{PASS_MARKER}\n", "AssertionError\n"])

    result = evaluate_solution("def solve(value): return value * 2", TEST_CASES, sandbox)

    assert result.score == 0.5
    assert [test.passed for test in result.tests] == [True, False]
    assert len(sandbox.programs) == 2
    assert all("def solve" in program for program in sandbox.programs)


def test_evaluate_solution_requires_marker_to_be_last_line() -> None:
    sandbox = StubSandbox("3.15", [f"{PASS_MARKER}\nerror after marker\n", PASS_MARKER])

    result = evaluate_solution("def solve(value): return value * 2", TEST_CASES, sandbox)

    assert result.score == 0.5
    assert [test.passed for test in result.tests] == [False, True]


def test_evaluate_solution_requires_tests() -> None:
    with pytest.raises(ValueError, match="At least one test case"):
        evaluate_solution("def solve(): pass", [], StubSandbox("3.15", []))


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("PEP815.rst", "PEP 815"), ("pep-0750.txt", "PEP 750"), ("whatsnew.rst", None)],
)
def test_pep_identifier(filename: str, expected: str | None) -> None:
    assert pep_identifier(Path(filename)) == expected


def test_build_dataset_line_includes_problem_and_source_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = Problem(
        prompt="Implement solve(value: int) -> int.",
        entry_point="solve",
        solution="def solve(value): return value * 2",
        test_cases=TEST_CASES,
    )
    monkeypatch.setattr("satyrn.dataset.rl.generate_problem", lambda *args: problem)
    idea = Idea(Path("PEP815.rst"), "Use the new API", "3.15")

    row = build_dataset_line(object(), idea, object(), object())

    assert row == {
        "prompt": problem.prompt,
        "test_cases": problem.to_dict()["test_cases"],
        "solution": problem.solution,
        "metadata": {
            "source_document": "PEP815.rst",
            "pep": "PEP 815",
            "python_version": "3.15",
            "idea": "Use the new API",
            "entry_point": "solve",
            "test_count": 2,
        },
    }


def test_verify_problem_stops_after_a_target_failure() -> None:
    target = StubSandbox("3.15", [PASS_MARKER, "failed"])
    predecessor = StubSandbox("3.14", [PASS_MARKER, PASS_MARKER])

    result = verify_problem("def solve(value): return value * 2", TEST_CASES, target, predecessor)

    assert result.passed is False
    assert result.target.score == 0.5
    assert result.predecessor is None
    assert predecessor.programs == []


def test_verify_problem_rejects_suite_that_passes_on_predecessor() -> None:
    target = StubSandbox("3.15", [PASS_MARKER, PASS_MARKER])
    predecessor = StubSandbox("3.14", [PASS_MARKER, PASS_MARKER])

    result = verify_problem("def solve(value): return value * 2", TEST_CASES, target, predecessor)

    assert result.passed is False
    assert result.predecessor is not None
    assert result.predecessor.score == 1.0


def test_verify_problem_accepts_target_only_suite() -> None:
    target = StubSandbox("3.15", [PASS_MARKER, PASS_MARKER])
    predecessor = StubSandbox("3.14", ["SyntaxError", "SyntaxError"])

    result = verify_problem("def solve(value): return value * 2", TEST_CASES, target, predecessor)

    assert result.passed is True
    assert result.target.score == 1.0
    assert result.predecessor is not None
    assert result.predecessor.score == 0.0
