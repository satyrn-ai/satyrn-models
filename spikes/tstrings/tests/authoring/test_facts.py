"""SP5 Task 6: provider facts — determinism, decision persistence, sandbox refusal.

Focused command: ``uv run python -m pytest tests/authoring/test_facts.py -q``.

``facts.py`` materializes a rendered task twice through the provider, rejects
differing observations (non-determinism), persists decisions keyed by intent
content hash + environment fingerprint, and refuses third-party-derived
material when no real OS sandbox profile is available (fail-closed).
"""

from __future__ import annotations

import dataclasses
import unittest.mock as mock

from satyrn_model.authoring.facts import (
    Deterministic,
    FactRecord,
    NonDeterministic,
    decide,
    environment_fingerprint,
    materialize_twice,
    read_facts,
    sandbox_refusal,
    write_facts,
)
from satyrn_model.authoring.models import (
    Introspect,
    PolicyIntent,
    TaskIntent,
)
from satyrn_model.authoring.task_builder import build_task
from satyrn_model.contracts.provenance import HarvestedProvenance
from satyrn_model.execution.protocol import (
    Accepted,
    NameValue,
    NullSandbox,
)


def _introspect_task():
    return build_task(
        TaskIntent(
            id="facts-intro",
            description="introspect the static string parts of a template",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset({"strings"}),
            ),
        )
    )


def test_materialize_twice_observations_match() -> None:
    """A deterministic task materializes identically on both runs."""
    outcome = materialize_twice(_introspect_task(), sandbox=NullSandbox(), timeout=15)
    assert isinstance(outcome, Deterministic)
    assert outcome.observations  # non-empty observation set
    assert outcome.interpreter_version.startswith("3.14")


def test_differing_observations_rejected() -> None:
    """Two runs with different observations are flagged non-deterministic."""
    acc1 = Accepted(
        observations=(NameValue(name="result", repr="('Hello ',)"),),
        interpreter_version="3.14.5",
        sandbox_backend="null",
        sandbox_profile_version="0",
    )
    acc2 = Accepted(
        observations=(NameValue(name="result", repr="('Hello',)"),),
        interpreter_version="3.14.5",
        sandbox_backend="null",
        sandbox_profile_version="0",
    )
    with mock.patch(
        "satyrn_model.authoring.facts.materialize_reference",
        side_effect=[acc1, acc2],
    ):
        outcome = materialize_twice(_introspect_task(), sandbox=NullSandbox())
    assert isinstance(outcome, NonDeterministic)
    assert outcome.first == acc1.observations
    assert outcome.second == acc2.observations


def test_fact_record_round_trip_keyed_by_content_and_fingerprint(tmp_path) -> None:
    """FactRecords persist as JSONL and key stably on intent + environment."""
    outcome = materialize_twice(_introspect_task(), sandbox=NullSandbox(), timeout=15)
    assert isinstance(outcome, Deterministic)

    fingerprint = environment_fingerprint()
    rec1 = FactRecord.from_outcome(_introspect_task(), outcome, fingerprint=fingerprint)
    rec2 = FactRecord.from_outcome(_introspect_task(), outcome, fingerprint=fingerprint)

    # Same intent + fingerprint -> same key, regardless of instance.
    assert rec1.key == rec2.key
    assert rec1.deterministic is True
    assert rec1.refusal is None

    path = tmp_path / "facts.jsonl"
    write_facts([rec1], path)
    assert read_facts(path) == [rec1]


def test_third_party_harvest_refused_without_os_profile() -> None:
    """Fail-closed: third-party harvest needs a real OS profile; CPython and
    generated provenance do not."""
    task = _introspect_task()

    third_party = dataclasses.replace(
        task,
        provenance=HarvestedProvenance(
            source_file="vendor-repo/tests/test_x.py",
            upstream_ref="abc123",
            interpreter_version="3.14.5",
        ),
    )
    assert sandbox_refusal(third_party.provenance, NullSandbox()) is not None

    trusted = dataclasses.replace(
        task,
        provenance=HarvestedProvenance(
            source_file="Lib/test/test_string/test_templatelib.py",
            upstream_ref="v3.14.5",
            interpreter_version="3.14.5",
        ),
    )
    assert sandbox_refusal(trusted.provenance, NullSandbox()) is None

    # Generated provenance has no harvest sandbox requirement.
    assert sandbox_refusal(task.provenance, NullSandbox()) is None


def test_decide_records_refusal_for_third_party() -> None:
    """decide() fails closed: third-party harvest without an OS profile is
    recorded as a refusal and never materialized."""
    third_party = dataclasses.replace(
        _introspect_task(),
        provenance=HarvestedProvenance(
            source_file="vendor-repo/tests/test_x.py",
            upstream_ref="abc123",
            interpreter_version="3.14.5",
        ),
    )
    rec = decide(third_party, sandbox=NullSandbox())
    assert isinstance(rec, FactRecord)
    assert rec.refusal is not None
    assert "sandbox" in rec.refusal
