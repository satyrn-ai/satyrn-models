"""Contract ingest and round-trip tests for the versioned dataset snapshot.

Task 1 of the provider plan. These tests pin the public consumer contract:
the wire types a dataset producer may ship, the validation ingest performs
*before executing anything*, and the byte-identical round-trip of the one
canonical fixture. Reference execution (Task 2) and the trusted policy
registry (Task 3) are deliberately out of scope here; policy registration is
checked against an injectable test-double registry.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from satyrn_model.contracts import (
    DATASET_CONTRACT_VERSION,
    EXECUTION_CONTRACT_VERSION,
    CompleteProgram,
    ContractError,
    DatasetSnapshot,
    FeaturePolicy,
    GeneratedProvenance,
    HarvestedProvenance,
    NameEquals,
    PolicyRef,
    TaskRecord,
    content_id,
    dump_snapshot,
    ingest_snapshot,
    load_snapshot,
    semantic_content_id,
)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "contracts"
    / "v1"
    / "snapshot.json"
)


class _StubPolicy:
    """Minimal FeaturePolicy for ingest registration checks only.

    Reference analysis, candidate analysis, and degenerate generation are
    Task 2/3 concerns; ingest only checks identity.
    """

    policy_id = "tstring"
    version = 1

    def analyze_reference(
        self, task: TaskRecord
    ) -> object:  # pragma: no cover - Task 2/3
        raise NotImplementedError

    def analyze_candidate(
        self, task: TaskRecord, candidate: str
    ) -> object:  # pragma: no cover
        raise NotImplementedError

    def degenerate_candidates(self, task: TaskRecord) -> list[str]:  # pragma: no cover
        raise NotImplementedError


class _StubRegistry:
    """Test double for the trusted PolicyRegistry Protocol (Task 3 owns real)."""

    def __init__(self) -> None:
        self._policies: dict[str, set[int]] = {"tstring": {1}}

    def registered_policy_ids(self) -> frozenset[str]:
        return frozenset(self._policies)

    def known_versions(self, policy_id: str) -> frozenset[int]:
        return frozenset(self._policies.get(policy_id, set()))

    def resolve(self, ref: PolicyRef) -> FeaturePolicy:  # pragma: no cover - Task 2/3
        raise NotImplementedError


def _harvested_task() -> TaskRecord:
    return TaskRecord(
        prompt="return a template that greets a name",
        reference='def greet(name):\n    return t"Hello {name}"\n',
        checks=(NameEquals(name="greet"),),
        policy=PolicyRef(id="tstring", version=1, config={}),
        completion=CompleteProgram(),
        provenance=HarvestedProvenance(
            source_file="Lib/test/test_string/test_templatelib.py",
            upstream_ref="v3.14.5",
            interpreter_version="3.14.5",
        ),
    )


def _generated_task() -> TaskRecord:
    return TaskRecord(
        prompt="apply a conversion with convert()",
        reference=(
            "from string.templatelib import convert\n"
            'def r(value):\n    return convert(value, "r")\n'
        ),
        checks=(NameEquals(name="r"),),
        policy=PolicyRef(id="tstring", version=1, config={"require_feature": False}),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="seed-pattern-cross-product",
            generator_version="0.1.0",
            seed_id="seed-convert-basic",
        ),
    )


def _valid_snapshot() -> DatasetSnapshot:
    tasks = (_harvested_task(), _generated_task())
    return DatasetSnapshot.from_tasks(tasks)


def _valid_dict() -> dict:
    return json.loads(dump_snapshot(_valid_snapshot()))


def _ingest(data: object) -> DatasetSnapshot:
    return ingest_snapshot(data, registry=_StubRegistry())


# ---------------------------------------------------------------------------
# Contract version constants exist
# ---------------------------------------------------------------------------


def test_contract_version_constants_are_present() -> None:
    assert isinstance(DATASET_CONTRACT_VERSION, str) and DATASET_CONTRACT_VERSION
    assert isinstance(EXECUTION_CONTRACT_VERSION, str) and EXECUTION_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Canonical fixture round-trips byte-identically
# ---------------------------------------------------------------------------


def test_canonical_fixture_loads_and_round_trips_byte_identically() -> None:
    loaded = load_snapshot(FIXTURE, registry=_StubRegistry())
    assert dump_snapshot(loaded) == FIXTURE.read_text()


def test_canonical_fixture_covers_both_provenance_kinds_and_both_check_kinds() -> None:
    snapshot = load_snapshot(FIXTURE, registry=_StubRegistry())
    prov_kinds = {type(task.provenance).__name__ for task in snapshot.tasks}
    assert prov_kinds == {"HarvestedProvenance", "GeneratedProvenance"}
    check_kinds = {check.kind for task in snapshot.tasks for check in task.checks}
    assert "raises" in check_kinds, "fixture must exercise the Raises check kind"


# ---------------------------------------------------------------------------
# Malformed / structural rejections
# ---------------------------------------------------------------------------


def test_malformed_json_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    with pytest.raises(ContractError, match="malformed json"):
        load_snapshot(path, registry=_StubRegistry())


def test_top_level_must_be_object() -> None:
    with pytest.raises(ContractError, match="snapshot must be an object"):
        _ingest([{"id": "x"}])


def test_missing_manifest_rejected() -> None:
    data = _valid_dict()
    del data["manifest"]
    with pytest.raises(ContractError, match="manifest"):
        _ingest(data)


# ---------------------------------------------------------------------------
# Contract version
# ---------------------------------------------------------------------------


def test_unknown_contract_version_rejected() -> None:
    data = _valid_dict()
    data["manifest"]["contract_version"] = "99"
    with pytest.raises(ContractError, match="contract version"):
        _ingest(data)


# ---------------------------------------------------------------------------
# Task / manifest rejections
# ---------------------------------------------------------------------------


def test_duplicate_task_ids_rejected() -> None:
    data = _valid_dict()
    # Two tasks with identical content derive the same id (a real duplicate,
    # not a stale-id artifact), so the duplicate-id check is what fires.
    data["tasks"][1] = copy.deepcopy(data["tasks"][0])
    with pytest.raises(ContractError, match="duplicate task id"):
        _ingest(data)


def test_semantic_duplicates_with_distinct_provenance_are_rejected() -> None:
    first = _generated_task()
    second = TaskRecord(
        prompt=first.prompt,
        reference=first.reference,
        checks=first.checks,
        policy=first.policy,
        completion=first.completion,
        provenance=GeneratedProvenance(
            generator="seed-pattern-cross-product",
            generator_version="0.1.0",
            seed_id="seed-convert-other",
        ),
    )
    assert first.id != second.id
    assert semantic_content_id(first) == semantic_content_id(second)

    with pytest.raises(ContractError, match="duplicate semantic task content"):
        _ingest(DatasetSnapshot.from_tasks((first, second)).to_dict())


def test_task_id_content_mismatch_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["prompt"] = "a different prompt that changes content"
    # id left unchanged -> no longer matches derived content
    with pytest.raises(ContractError, match="id does not match content"):
        _ingest(data)


def test_manifest_task_count_mismatch_rejected() -> None:
    data = _valid_dict()
    data["manifest"]["task_count"] = 99
    with pytest.raises(ContractError, match="task_count"):
        _ingest(data)


def test_manifest_fingerprint_mismatch_rejected() -> None:
    data = _valid_dict()
    data["manifest"]["fingerprint"] = "0" * 64
    with pytest.raises(ContractError, match="fingerprint"):
        _ingest(data)


# ---------------------------------------------------------------------------
# Policy rejections
# ---------------------------------------------------------------------------


def test_unregistered_policy_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["policy"]["id"] = "no-such-policy"
    # Re-derive the id from the mutated content, as a real producer would,
    # so the unregistered-policy check is what fires (not a stale-id mismatch).
    data["tasks"][0]["id"] = ""
    with pytest.raises(ContractError, match="unregistered policy"):
        _ingest(data)


def test_policy_version_mismatch_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["policy"]["version"] = 99
    data["tasks"][0]["id"] = ""  # re-derive from mutated content
    with pytest.raises(ContractError, match="policy version mismatch"):
        _ingest(data)


# ---------------------------------------------------------------------------
# Completion mode
# ---------------------------------------------------------------------------


def test_unknown_completion_mode_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["completion"]["mode"] = "chat"
    with pytest.raises(ContractError, match="completion mode"):
        _ingest(data)


# ---------------------------------------------------------------------------
# CheckSpec: closed union, no trusted expected value
# ---------------------------------------------------------------------------


def test_check_with_caller_supplied_expected_value_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["checks"][0]["expected"] = "Hello World"
    with pytest.raises(ContractError, match="unexpected.*expected"):
        _ingest(data)


def test_check_with_unknown_kind_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["checks"][0]["kind"] = "equals_value"
    with pytest.raises(ContractError, match="check kind"):
        _ingest(data)


def test_check_with_arbitrary_source_expression_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["checks"][0] = {"kind": "eval", "expr": "open('/etc/passwd')"}
    with pytest.raises(ContractError, match="check kind"):
        _ingest(data)


def test_raises_check_with_disallowed_exception_rejected() -> None:
    data = copy.deepcopy(_valid_dict())
    data["tasks"][0]["checks"][0] = {"kind": "raises", "exception": "os.system"}
    with pytest.raises(ContractError, match="exception"):
        _ingest(data)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_unknown_provenance_kind_rejected() -> None:
    data = _valid_dict()
    data["tasks"][0]["provenance"]["kind"] = "imagined"
    with pytest.raises(ContractError, match="provenance kind"):
        _ingest(data)


def test_harvested_provenance_round_trips() -> None:
    original = _harvested_task()
    data = original.provenance
    snapshot = _ingest(_valid_dict())  # exercise full parse for the harvested task
    assert snapshot.tasks[0].provenance == data


def test_generated_provenance_round_trips() -> None:
    snapshot = _ingest(_valid_dict())
    assert isinstance(snapshot.tasks[1].provenance, GeneratedProvenance)
    assert snapshot.tasks[1].provenance.seed_id == "seed-convert-basic"


def test_harvested_provenance_rejects_fictional_generator_field() -> None:
    data = _valid_dict()
    data["tasks"][0]["provenance"]["generator"] = "sneaky"
    with pytest.raises(ContractError, match="unexpected"):
        _ingest(data)


# ---------------------------------------------------------------------------
# content_id is content-derived
# ---------------------------------------------------------------------------


def test_content_id_is_stable_and_content_derived() -> None:
    task = _harvested_task()
    again = TaskRecord(
        prompt=task.prompt,
        reference=task.reference,
        checks=task.checks,
        policy=task.policy,
        completion=task.completion,
        provenance=task.provenance,
    )
    assert content_id(again) == task.id
