"""SP5 Task 6: live adversarial policy tests (real TStringPolicy + oracle).

Focused command: ``uv run python -m pytest tests/authoring/test_policy.py -q``.

These pin the plan's adversarial cases: f-string fallback, candidate-derived
expected values, vacuity, AnnAssign vacuity, construct/convert requirements,
``requires_template=False``, and the format-spec pair
(``t"{v:{w}}"`` valid, nested f-string in a format-spec expression invalid).
All run live against the provider's materialize/verify/qualify pipeline.
"""

from __future__ import annotations

from satyrn_model.authoring.models import (
    Construct,
    Introspect,
    PolicyIntent,
    TaskIntent,
)
from satyrn_model.authoring.task_builder import build_task
from satyrn_model.contracts import TaskRecord
from satyrn_model.execution.protocol import (
    Accepted,
    NullSandbox,
)
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.qualify import VacuityUntested, qualify_task
from satyrn_model.oracle.verify import Rejection, VerifyAccepted, verify_candidate
from satyrn_model.policies.tstring import TStringPolicy

_SANDBOX = NullSandbox()


def _introspect_task() -> TaskRecord:
    return build_task(
        TaskIntent(
            id="adv-intro",
            description="introspect the static string parts of a template",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset({"strings"}),
            ),
        )
    )


def _materialize(task: TaskRecord) -> Accepted:
    out = materialize_reference(task, sandbox=_SANDBOX, timeout=15)
    assert isinstance(out, Accepted), f"materialization failed: {out}"
    return out


# ---------------------------------------------------------------------------
# Format-spec adversarial pair
# ---------------------------------------------------------------------------


def test_format_spec_valid_template_accepted() -> None:
    """``t"{v:{w}}"`` (interpolation inside a format spec) is a valid t-string."""
    policy = TStringPolicy()
    task = _introspect_task()
    policy.analyze_reference(task)
    assert policy.analyze_candidate(task, 'value = t"{v:{w}}"\n').passed


def test_format_spec_nested_fstring_rejected() -> None:
    """A genuine nested f-string inside a format-spec expression is invalid."""
    policy = TStringPolicy()
    task = _introspect_task()
    policy.analyze_reference(task)
    result = policy.analyze_candidate(task, "value = t\"{v:{f'{w}'}}\"\n")
    assert not result.passed
    assert "f-string" in result.reason


# ---------------------------------------------------------------------------
# Degenerate derivation: from the task, never from a candidate or value
# ---------------------------------------------------------------------------


def test_degenerate_derived_from_task_not_expected_value() -> None:
    """Degenerates are the rendered task plus a wrong-output override; they
    never contain the reference's actual expected value."""
    policy = TStringPolicy()
    task = _introspect_task()
    policy.analyze_reference(task)

    degenerates = policy.degenerate_candidates(task)
    assert len(degenerates) == 1
    deg = degenerates[0]
    assert deg.startswith(task.reference)
    assert "result = 'wrong-output'" in deg

    # The overridden value must differ from the materialized reference result,
    # otherwise the degenerate would pass semantic check vacuously.
    out = _materialize(task)
    ref_result = next(
        o.repr for o in out.observations if getattr(o, "name", None) == "result"
    )
    assert ref_result != "'wrong-output'"


# ---------------------------------------------------------------------------
# Vacuity
# ---------------------------------------------------------------------------


def test_annassign_degenerate_rejected_at_semantic_check() -> None:
    """An AnnAssign degenerate (``result: str = ...``) still fails at semantic
    check — the annotation does not make the check vacuous."""
    task = _introspect_task()
    out = _materialize(task)
    annassign = task.reference + "\nresult: str = 'wrong-output'\n"
    result = verify_candidate(
        task,
        annassign,
        ref_observations=out.observations,
        policy=TStringPolicy(),
        sandbox=_SANDBOX,
    )
    assert isinstance(result, Rejection)
    assert result.stage == "semantic_check"


def test_vacuity_untested_when_degenerate_passes() -> None:
    """A degenerate that passes semantic check makes the task vacuity-untested."""

    class SelfDegeneratePolicy(TStringPolicy):
        """Test-only: degenerate is the reference itself, which must pass."""

        def degenerate_candidates(self, task: TaskRecord) -> list[str]:
            return [task.reference]

    task = _introspect_task()
    result = qualify_task(task, policy=SelfDegeneratePolicy(), sandbox=_SANDBOX)
    assert isinstance(result, VacuityUntested)


# ---------------------------------------------------------------------------
# Construct/convert requirements and requires_template=False
# ---------------------------------------------------------------------------


def test_convert_only_requires_no_template() -> None:
    """A convert()-only task (requires_template=False) passes candidates that
    contain no t-string literal at all."""
    task = build_task(
        TaskIntent(
            id="adv-convert",
            description="apply a !r conversion with convert()",
            properties=(Construct(operation="convert"),),
            policy_intent=PolicyIntent(
                requires_template=False,
                templatelib_apis_used=frozenset({"convert"}),
            ),
        )
    )
    policy = TStringPolicy()
    out = _materialize(task)
    # A no-template candidate must be accepted for this task.
    assert policy.analyze_candidate(task, "result = 1\n").passed
    result = verify_candidate(
        task,
        task.reference,
        ref_observations=out.observations,
        policy=policy,
        sandbox=_SANDBOX,
    )
    assert isinstance(result, VerifyAccepted)


# ---------------------------------------------------------------------------
# f-string fallback (live end-to-end)
# ---------------------------------------------------------------------------


def test_fstring_fallback_rejected_end_to_end() -> None:
    """An f-string fallback candidate is rejected at the policy stage, live."""
    task = _introspect_task()
    out = _materialize(task)
    fstring = task.reference.replace('t"', 'f"').replace("t'", "f'")
    result = verify_candidate(
        task,
        fstring,
        ref_observations=out.observations,
        policy=TStringPolicy(),
        sandbox=_SANDBOX,
    )
    assert isinstance(result, Rejection)
    assert result.stage == "policy"
