"""Candidate oracle: verify_candidate and qualify_task tests.

Uses a minimal test FeaturePolicy that rejects candidates containing
'f-string' (old-form check) and supplies degenerate candidates for anti-
vacuity. All NameEquals checks target concrete values (strings), not function
objects, because repr() of functions includes the memory address and differs
across subprocess runs.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    Raises,
    TaskRecord,
)
from satyrn_model.contracts.policy import PolicyResult
from satyrn_model.execution.protocol import (
    Accepted,
    InfrastructureFailure,
    NullSandbox,
    Rejection,
)
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.qualify import (
    Qualified,
    VacuityUntested,
    qualify_task,
)
from satyrn_model.oracle.verify import VerifyAccepted, verify_candidate
from satyrn_model.policies.registry import TrustedPolicyRegistry

# ---------------------------------------------------------------------------
# Test policy
# ---------------------------------------------------------------------------


class _TestPolicy:
    """Stub policy: rejects 'f-string', supplies degenerates that differ."""

    policy_id = "tstring"
    version = 1

    def analyze_reference(self, task: TaskRecord) -> None:
        pass

    def analyze_candidate(self, task: TaskRecord, candidate: str) -> PolicyResult:
        if 'f"' in candidate or "f'" in candidate:
            return PolicyResult(passed=False, reason="old-form f-string detected")
        return PolicyResult(passed=True)

    def degenerate_candidates(self, task: TaskRecord) -> list[str]:
        if "greet" in task.reference:
            return ['def greet(name):\n    return "wrong"\nresult = greet("")\n']
        if "convert" in task.reference:
            return ["result = 0\n"]
        return ["result = 999\n"]


class _LeakyPolicy:
    """Policy whose degenerate passes semantic check (vacuity exposure)."""

    policy_id = "tstring"
    version = 1

    def analyze_reference(self, task: TaskRecord) -> None:
        pass

    def analyze_candidate(self, task: TaskRecord, candidate: str) -> PolicyResult:
        return PolicyResult(passed=True)

    def degenerate_candidates(self, task: TaskRecord) -> list[str]:
        return [task.reference]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sandbox() -> NullSandbox:
    return NullSandbox()


def _task(*, reference: str, checks: tuple = ()) -> TaskRecord:
    if not checks:
        checks = (NameEquals(name="result"),)
    return TaskRecord(
        prompt="test",
        reference=reference,
        checks=checks,
        policy=PolicyRef(id="tstring", version=1, config={}),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="test", generator_version="0", seed_id="test"
        ),
    )


def _materialize(task: TaskRecord) -> Accepted:
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Accepted), (
        f"unexpected {type(outcome).__name__}: {getattr(outcome, 'reason', '')}"
    )
    return outcome


# ---------------------------------------------------------------------------
# verify_candidate: successful
# ---------------------------------------------------------------------------


def test_candidate_identical_to_reference_passes() -> None:
    task = _task(
        reference='def greet(name):\n    return "Hello"\nresult = greet("World")\n',
    )
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        task.reference,
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, VerifyAccepted)


def test_convert_only_task_passes_without_universal_template_check() -> None:
    task = _task(
        reference=dedent("""\
        from string.templatelib import convert
        def r(value):
            return convert(value, "r")
        result = r("hello")
        """),
    )
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        task.reference,
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, VerifyAccepted)


def test_raises_check_passes_when_same_exception() -> None:
    task = _task(
        reference="d = {}\nd['missing']\n",
        checks=(Raises(exception="KeyError"),),
    )
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        task.reference,
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, VerifyAccepted)


# ---------------------------------------------------------------------------
# verify_candidate: staged rejections
# ---------------------------------------------------------------------------


def test_syntax_error_candidate_parse_stage() -> None:
    task = _task(reference="result = 1\n")
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        "def bad(:\n    pass\n",
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, Rejection) and outcome.stage == "candidate_parse"


def test_planted_fstring_reaches_policy_stage() -> None:
    task = _task(reference='result = "Hello"\n')
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        'result = f"Hello"\n',
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, Rejection) and outcome.stage == "policy"


def test_wrong_output_reaches_semantic_check_stage() -> None:
    task = _task(reference='result = "Hello"\n')
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        'result = "Goodbye"\n',
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, Rejection) and outcome.stage == "semantic_check"


def test_import_error_retains_candidate_execute_stage() -> None:
    task = _task(reference="result = 1\n")
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        "import no_such_module_xyzzy\n",
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, Rejection) and outcome.stage == "candidate_execute"


def test_timeout_retains_own_stage() -> None:
    task = _task(reference="result = 1\n")
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        "while True:\n    pass\n",
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
        timeout=2,
    )
    assert isinstance(outcome, InfrastructureFailure) and outcome.stage == "timeout"


def test_raises_wrong_exception_semantic_check() -> None:
    task = _task(
        reference="int('not-a-number')\n",
        checks=(Raises(exception="ValueError"),),
    )
    ref = _materialize(task)
    outcome = verify_candidate(
        task,
        "d = {}\nd['missing']\n",
        ref_observations=ref.observations,
        policy=_TestPolicy(),
        sandbox=_sandbox(),
    )
    assert isinstance(outcome, Rejection) and outcome.stage == "semantic_check"


# ---------------------------------------------------------------------------
# qualify_task
# ---------------------------------------------------------------------------


def test_task_qualifies_when_self_check_passes_and_degenerates_fail() -> None:
    task = _task(
        reference='def greet(name):\n    return "Hello"\nresult = greet("World")\n',
    )
    outcome = qualify_task(task, policy=_TestPolicy(), sandbox=_sandbox())
    assert isinstance(outcome, Qualified)


def test_reference_not_passing_self_check_fails_qualification() -> None:
    task = _task(
        reference='def greet(name):\n    return "Hello"\nresult = greet("World")\n',
        checks=(NameEquals(name="missing_name"),),
    )
    outcome = qualify_task(task, policy=_TestPolicy(), sandbox=_sandbox())
    assert not isinstance(outcome, Qualified)


def test_degenerate_passing_semantic_check_exposes_vacuity() -> None:
    task = _task(reference='result = "Hello"\n')
    outcome = qualify_task(task, policy=_LeakyPolicy(), sandbox=_sandbox())
    assert isinstance(outcome, VacuityUntested)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_policy() -> None:
    reg = TrustedPolicyRegistry()
    reg.register(_TestPolicy())
    resolved = reg.resolve(PolicyRef(id="tstring", version=1, config={}))
    assert resolved.policy_id == "tstring"
    assert resolved.version == 1


def test_registry_rejects_unregistered() -> None:
    from satyrn_model.contracts import ContractError

    reg = TrustedPolicyRegistry()
    with pytest.raises(ContractError, match="not registered"):
        reg.resolve(PolicyRef(id="unknown", version=1, config={}))
