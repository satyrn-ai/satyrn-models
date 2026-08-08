"""SP5 Task 8: build pipeline, reports, and contamination halts publication.

Focused command: ``uv run python -m pytest tests/authoring/test_build.py -q``.

Covers the plan's four named tests — ``test_contamination_halts_publication``,
``test_drop_has_full_content``, ``test_no_cache_is_byte_reproducible``,
``test_interrupted_write_is_atomic`` — plus a snapshot-ingest happy path.
"""

import json
import unittest.mock as mock

import pytest

from satyrn_model.authoring.build import (
    BuildInfrastructureError,
    BuildResult,
    ContaminationError,
    atomic_write_text,
    build_pipeline,
)
from satyrn_model.authoring.generate import apply_pattern
from satyrn_model.authoring.models import Seed
from satyrn_model.authoring.patterns.approvals import (
    ApprovalError,
    PatternApproval,
)
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import pattern_input_fingerprint
from satyrn_model.contracts import load_snapshot
from satyrn_model.execution.protocol import NullSandbox
from satyrn_model.policies.registry import TrustedPolicyRegistry
from satyrn_model.policies.tstring import TStringPolicy

_SANDBOX = NullSandbox()


def _seed(sid: str, literal: str) -> Seed:
    return Seed(
        id=sid,
        literal=literal,
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=(f"occ-{sid}",),
        kind="authored",
    )


def _approval(pattern) -> PatternApproval:
    return PatternApproval(
        pattern_id=pattern.id,
        pattern_input_fingerprint=pattern_input_fingerprint(pattern),
        approved_at="2026-08-02T00:00:00+00:00",
    )


def _setup():
    """One approved introspect pattern + one generated exercise."""
    intro = CATALOG[0]  # intro-strings
    approvals = [_approval(intro)]
    rows = [apply_pattern(intro, (_seed("seed-a", 't"Hello {name}"'),))]
    return intro, approvals, rows


# ---------------------------------------------------------------------------
# Named: contamination halts publication
# ---------------------------------------------------------------------------


def test_contamination_halts_publication(tmp_path) -> None:
    """A row matching a benchmark task (prompt+reference) raises before any
    artifact is written; a clean benchmark builds fine."""
    intro, approvals, rows = _setup()
    clean_out = tmp_path / "clean"
    result = build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=clean_out,
    )
    task = result.snapshot.tasks[0]

    contaminated_out = tmp_path / "contaminated"
    with pytest.raises(ContaminationError, match="benchmark"):
        build_pipeline(
            source_rows=[],
            generated=rows,
            patterns=[intro],
            approvals=approvals,
            benchmark=[(task.prompt, task.reference)],
            sandbox=_SANDBOX,
            out_dir=contaminated_out,
        )
    # Publication halted: no corpus artifact for the contaminated build.
    assert not (contaminated_out / "corpus/tstrings.jsonl").exists()


# ---------------------------------------------------------------------------
# Named: drops carry full row content
# ---------------------------------------------------------------------------


def test_drop_has_full_content(tmp_path) -> None:
    """An exact duplicate is dropped with full row content, not an id alone."""
    intro, approvals, rows = _setup()
    result = build_pipeline(
        source_rows=[],
        generated=[rows[0], rows[0]],  # exact duplicate
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=tmp_path / "out",
    )
    assert len(result.dropped) == 1
    assert result.dropped[0].stage == "dedup"

    records = [
        json.loads(line)
        for line in (tmp_path / "out/reports/dropped.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["stage"] == "dedup"
    # Full content: the row's prompt and reference are present, not an id.
    assert "Hello" in json.dumps(records[0]["content"])


def test_build_persists_real_pilot_candidate_metadata(tmp_path) -> None:
    """Sampling strata survive qualification and are written beside lineage."""
    intro, approvals, rows = _setup()
    out = tmp_path / "out"

    result = build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=out,
    )

    assert len(result.sample_rows) == 1
    candidate = result.sample_rows[0]
    assert candidate.row_id == result.snapshot.tasks[0].id
    assert candidate.source_kind == "authored"
    assert candidate.role == "author"
    assert candidate.domain == "text"
    assert candidate.property == "introspect"
    assert candidate.pattern_id == intro.id
    assert candidate.seed_id == "seed-a"
    persisted = json.loads(
        (out / "reports/pilot-candidates.jsonl").read_text(encoding="utf-8")
    )
    assert persisted["row_id"] == candidate.row_id


def test_semantic_duplicate_retains_each_seed_in_lineage(tmp_path) -> None:
    """Different seed provenance for one learning task yields one row and
    lineage links for both original seeds."""
    pattern = next(item for item in CATALOG if item.id == "construct-convert")
    approvals = [_approval(pattern)]
    rows = [
        apply_pattern(pattern, (_seed("seed-a", 't"Hello {name}"'),)),
        apply_pattern(pattern, (_seed("seed-b", 't"Hello {name}"'),)),
    ]
    result = build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[pattern],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=tmp_path / "out",
    )
    assert result.snapshot.manifest.task_count == 1
    assert [drop.stage for drop in result.dropped] == ["dedup"]
    assert {entry["seed_ids"][0] for entry in result.lineage} == {
        "seed-a",
        "seed-b",
    }
    assert {entry["row_id"] for entry in result.lineage} == {
        result.snapshot.tasks[0].id
    }


def test_stale_approval_halts_build(tmp_path) -> None:
    """A generated row whose pattern approval is stale halts the build
    before any row is rendered or written (design: halt on stale audit)."""
    intro, approvals, rows = _setup()
    # Stale the approval: same pattern id, different fingerprint.
    stale = PatternApproval(
        pattern_id=intro.id,
        pattern_input_fingerprint="deadbeef" * 8,
        approved_at="2026-08-02T00:00:00+00:00",
    )
    out = tmp_path / "stale-out"
    with pytest.raises(ApprovalError, match="stale"):
        build_pipeline(
            source_rows=[],
            generated=rows,
            patterns=[intro],
            approvals=[stale],
            benchmark=[],
            sandbox=_SANDBOX,
            out_dir=out,
        )
    # Halted: nothing written.
    assert not (out / "corpus/tstrings.jsonl").exists()


def test_qualification_drop_records_full_content(tmp_path) -> None:
    """A row rejected at qualification is recorded with full content.

    Current renderers only produce self-qualifying references, so the
    non-dedup drop path is driven by a mocked qualification rejection —
    the drop-recording behavior is what is under test."""
    intro, approvals, rows = _setup()
    from satyrn_model.oracle.verify import Rejection

    def _reject(*args, **kwargs):
        return Rejection(stage="policy", reason="old-form f-string detected")

    out = tmp_path / "reject-out"
    with mock.patch("satyrn_model.authoring.build.qualify_task", side_effect=_reject):
        result = build_pipeline(
            source_rows=[],
            generated=rows,
            patterns=[intro],
            approvals=approvals,
            benchmark=[],
            sandbox=_SANDBOX,
            out_dir=out,
        )
    assert result.snapshot.manifest.task_count == 0
    assert len(result.dropped) == 1
    assert result.dropped[0].stage == "policy"
    assert "Hello" in json.dumps(result.dropped[0].content)


def test_infrastructure_failure_halts_without_artifacts(tmp_path) -> None:
    """Sandbox and subprocess failures cannot publish an empty corpus."""
    from satyrn_model.execution.protocol import InfrastructureFailure

    intro, approvals, rows = _setup()
    out = tmp_path / "infrastructure-failure"
    failure = InfrastructureFailure(stage="sandbox", reason="profile unavailable")

    with (
        mock.patch("satyrn_model.authoring.build.qualify_task", return_value=failure),
        pytest.raises(BuildInfrastructureError, match="profile unavailable"),
    ):
        build_pipeline(
            source_rows=[],
            generated=rows,
            patterns=[intro],
            approvals=approvals,
            benchmark=[],
            sandbox=_SANDBOX,
            out_dir=out,
        )

    assert not (out / "corpus/tstrings.jsonl").exists()


# ---------------------------------------------------------------------------
# Named: byte-reproducible build
# ---------------------------------------------------------------------------


def test_no_cache_is_byte_reproducible(tmp_path) -> None:
    """Two builds over identical inputs produce byte-identical artifacts."""
    intro, approvals, rows = _setup()
    out1, out2 = tmp_path / "a", tmp_path / "b"
    build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=out1,
    )
    build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=out2,
    )
    assert (out1 / "corpus/tstrings.jsonl").read_bytes() == (
        out2 / "corpus/tstrings.jsonl"
    ).read_bytes()
    assert (out1 / "reports/build.md").read_bytes() == (
        out2 / "reports/build.md"
    ).read_bytes()


# ---------------------------------------------------------------------------
# Named: interrupted writes are atomic
# ---------------------------------------------------------------------------


def test_interrupted_write_is_atomic(tmp_path) -> None:
    """A failed replace leaves the prior artifact intact and no tmp file."""
    target = tmp_path / "x.json"
    target.write_text("old", encoding="utf-8")
    with mock.patch(
        "satyrn_model.authoring.build.os.replace",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(OSError):
            atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------------------------------
# Happy path: qualified rows become an ingestible snapshot
# ---------------------------------------------------------------------------


def test_build_snapshot_ingests_with_registry(tmp_path) -> None:
    """The built corpus round-trips through provider ingest."""
    intro, approvals, rows = _setup()
    result = build_pipeline(
        source_rows=[],
        generated=rows,
        patterns=[intro],
        approvals=approvals,
        benchmark=[],
        sandbox=_SANDBOX,
        out_dir=tmp_path / "out",
    )
    assert isinstance(result, BuildResult)
    assert result.snapshot.manifest.task_count == 1

    registry = TrustedPolicyRegistry()
    registry.register(TStringPolicy())
    snapshot = load_snapshot(tmp_path / "out/corpus/tstrings.jsonl", registry=registry)
    assert snapshot.manifest.task_count == 1
    assert snapshot.manifest.fingerprint == result.snapshot.manifest.fingerprint

    # Lineage bundle links the row to its seed and occurrence.
    lineage = [
        json.loads(line)
        for line in (tmp_path / "out/reports/lineage.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(lineage) == 1
    assert lineage[0]["kind"] == "generated"
    assert lineage[0]["seed_ids"] == ["seed-a"]
    assert lineage[0]["occurrence_ids"] == ["occ-seed-a"]
