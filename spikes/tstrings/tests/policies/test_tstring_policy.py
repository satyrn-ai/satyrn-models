"""SP5↔provider integration: real TStringPolicy against provider contracts.

Builds a real DatasetSnapshot from SP5 TaskIntents, round-trips through the
provider's ingest (against the trusted registry), and exercises verify_candidate
and qualify_task through the real TStringPolicy — not a stub.
"""

from __future__ import annotations

from satyrn_model.authoring.models import (
    ComposeTemplates,
    Construct,
    Introspect,
    PolicyIntent,
    RenderTemplate,
    TaskIntent,
)
from satyrn_model.authoring.task_builder import build_task
from satyrn_model.contracts import (
    DatasetSnapshot,
    dump_snapshot,
    load_snapshot,
)
from satyrn_model.execution.protocol import NullSandbox
from satyrn_model.execution.reference import materialize_reference
from satyrn_model.oracle.qualify import Qualified, qualify_task
from satyrn_model.oracle.verify import VerifyAccepted, verify_candidate
from satyrn_model.policies.registry import TrustedPolicyRegistry
from satyrn_model.policies.tstring import TStringPolicy

# ---------------------------------------------------------------------------
# Build a real dataset
# ---------------------------------------------------------------------------


def _snapshot() -> DatasetSnapshot:
    intents = [
        TaskIntent(
            id="introspect-strings",
            description="introspect the static string parts of a template",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset(),
            ),
        ),
        TaskIntent(
            id="render-template",
            description="render a template with str.join",
            properties=(RenderTemplate(),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset({"strings"}),
            ),
        ),
        TaskIntent(
            id="convert-r",
            description="apply a !r conversion with convert()",
            properties=(Construct(operation="convert"),),
            policy_intent=PolicyIntent(
                requires_template=False,
                templatelib_apis_used=frozenset({"convert"}),
            ),
        ),
        TaskIntent(
            id="compose-templates",
            description="concatenate two templates with +",
            properties=(ComposeTemplates(),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset(),
            ),
        ),
    ]
    return DatasetSnapshot.from_tasks([build_task(i) for i in intents])


# ---------------------------------------------------------------------------
# Round-trip through provider ingest
# ---------------------------------------------------------------------------


def test_dataset_round_trips_through_provider_ingest(tmp_path) -> None:
    policy = TStringPolicy()
    registry = TrustedPolicyRegistry()
    registry.register(policy)

    snapshot = _snapshot()
    text = dump_snapshot(snapshot)

    path = tmp_path / "snapshot.json"
    path.write_text(text)

    loaded = load_snapshot(path, registry=registry)
    assert loaded.manifest.task_count == 4

    # Verify byte-identical round-trip
    assert dump_snapshot(loaded) == text


# ---------------------------------------------------------------------------
# Real TStringPolicy: verify_candidate
# ---------------------------------------------------------------------------


_SANDBOX = NullSandbox()


def test_verify_introspect_passes_with_correct_candidate() -> None:
    policy = TStringPolicy()
    task = build_task(
        TaskIntent(
            id="test-intro",
            description="test",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True, templatelib_apis_used=frozenset()
            ),
        )
    )
    outcome = materialize_reference(task, sandbox=_SANDBOX, timeout=15)
    from satyrn_model.execution.protocol import Accepted

    assert isinstance(outcome, Accepted)

    result = verify_candidate(
        task,
        task.reference,
        ref_observations=outcome.observations,
        policy=policy,
        sandbox=_SANDBOX,
    )
    assert isinstance(result, VerifyAccepted)


def test_verify_rejects_fstring_with_policy_stage() -> None:
    policy = TStringPolicy()
    task = build_task(
        TaskIntent(
            id="test-intro",
            description="test",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True, templatelib_apis_used=frozenset()
            ),
        )
    )
    outcome = materialize_reference(task, sandbox=_SANDBOX, timeout=15)
    from satyrn_model.execution.protocol import Accepted

    assert isinstance(outcome, Accepted)

    # Candidate uses f-string instead of t-string
    fstring_candidate = task.reference.replace("t'", "f'").replace('t"', 'f"')
    result = verify_candidate(
        task,
        fstring_candidate,
        ref_observations=outcome.observations,
        policy=policy,
        sandbox=_SANDBOX,
    )
    from satyrn_model.oracle.verify import Rejection

    assert isinstance(result, Rejection) and result.stage == "policy"
    assert "f-string" in result.reason.lower()


def test_verify_rejects_dot_format_with_policy_stage() -> None:
    policy = TStringPolicy()
    task = build_task(
        TaskIntent(
            id="test-intro",
            description="test",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True, templatelib_apis_used=frozenset()
            ),
        )
    )
    outcome = materialize_reference(task, sandbox=_SANDBOX, timeout=15)
    from satyrn_model.execution.protocol import Accepted

    assert isinstance(outcome, Accepted)

    format_candidate = (
        'name = "World"\n'
        'template = "Hello {name}".format(name=name)\n'
        "result = template\n"
    )
    result = verify_candidate(
        task,
        format_candidate,
        ref_observations=outcome.observations,
        policy=policy,
        sandbox=_SANDBOX,
    )
    from satyrn_model.oracle.verify import Rejection

    assert isinstance(result, Rejection) and result.stage == "policy"


def test_convert_task_passes_without_template_check() -> None:
    """Convert()-only tasks don't require a t-string literal."""
    policy = TStringPolicy()
    task = build_task(
        TaskIntent(
            id="convert-only",
            description="convert test",
            properties=(Construct(operation="convert"),),
            policy_intent=PolicyIntent(
                requires_template=False,
                templatelib_apis_used=frozenset({"convert"}),
            ),
        )
    )
    outcome = materialize_reference(task, sandbox=_SANDBOX, timeout=15)
    from satyrn_model.execution.protocol import Accepted

    assert isinstance(outcome, Accepted)

    # A candidate without t-string should still pass for convert-only tasks
    result = verify_candidate(
        task,
        task.reference,
        ref_observations=outcome.observations,
        policy=policy,
        sandbox=_SANDBOX,
    )
    assert isinstance(result, VerifyAccepted)


# ---------------------------------------------------------------------------
# Real TStringPolicy: qualify_task
# ---------------------------------------------------------------------------


def test_qualify_task_with_real_policy() -> None:
    policy = TStringPolicy()
    task = build_task(
        TaskIntent(
            id="test-intro",
            description="test",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True, templatelib_apis_used=frozenset()
            ),
        )
    )
    result = qualify_task(task, policy=policy, sandbox=_SANDBOX)
    kind = type(result).__name__
    detail = getattr(result, "reason", "")
    assert isinstance(result, Qualified), f"got {kind}: {detail}"
