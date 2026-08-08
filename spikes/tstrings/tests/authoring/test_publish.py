"""SP5 Task 10: publish nested 500 ⊂ 2k ⊂ 5k snapshots.

Focused command: ``uv run python -m pytest tests/authoring/test_publish.py -q``.

Covers the plan's four named tests — ``test_snapshot_ids_are_nested``,
``test_manifest_has_all_strata``, ``test_snapshot_lineage_is_self_contained``,
``test_publish_requires_calibrated_provider_result`` — plus a
snapshot-ingests-into-provider happy path.
"""

import pytest

from satyrn_model.authoring.publish import (
    PublishedSnapshot,
    PublishRow,
    publish_nested,
)
from satyrn_model.authoring.sampling import (
    CalibrationError,
    CalibrationRecord,
    SampleRow,
    SamplingPlan,
)
from satyrn_model.contracts import load_snapshot
from satyrn_model.execution.protocol import NullSandbox
from satyrn_model.policies.registry import TrustedPolicyRegistry
from satyrn_model.policies.tstring import TStringPolicy

_SANDBOX = NullSandbox()


def _plan() -> SamplingPlan:
    return SamplingPlan(
        target_rows=24,
        nested_order=["source_kind", "property", "seed"],
        strata={
            "source_kind": {"extracted": 0.40, "authored": 0.60},
            "property": {
                "introspect": 0.30,
                "render_template": 0.25,
                "construct": 0.20,
                "compose_templates": 0.15,
                "negative": 0.10,
            },
        },
    )


def _calibration(profile_version: int = 1) -> CalibrationRecord:
    band = [0.0, 0.8]
    return CalibrationRecord(
        profile_version=profile_version,
        target_rows=20,
        derived_at="2026-08-02T00:00:00+00:00",
        diversity={"distinct_skeletons": 20},
        composition_tolerance={
            "introspect": band,
            "render_template": band,
            "construct": band,
            "compose_templates": band,
            "negative": band,
        },
        review_budget=0.10,
    )


def _publish_row(task, *, property, source_kind, seed_id, source=None) -> PublishRow:
    links = {
        "pattern_id": task.policy.id,
        "seed_ids": [seed_id],
        "occurrence_ids": [f"occ-{seed_id}"],
    }
    if source:
        links.update(source)
    sample = SampleRow(
        row_id=task.id,
        source_kind=source_kind,
        property=property,
        pattern_id="intro-strings",
        seed_id=seed_id,
        skeleton="",
        prompt=task.prompt,
    )
    return PublishRow(task=task, sample=sample, links=links)


def _pool():
    """20 qualifying rows spanning all five properties.

    introspect x7, render x6, construct x1 (convert refs are seed-independent,
    so one is the honest maximum), transform x4, negative x2.
    """
    from satyrn_model.authoring.generate import apply_pattern
    from satyrn_model.authoring.models import Seed
    from satyrn_model.authoring.patterns.catalog import CATALOG
    from satyrn_model.authoring.task_builder import (
        build_task,
        generated_intent,
    )

    def seed(sid: str, literal: str, value: str) -> Seed:
        return Seed(
            id=sid,
            literal=literal,
            free_names=("name",),
            bindings=(("name", f'"{value}"'),),
            occurrence_ids=(f"occ-{sid}",),
            kind="authored",
        )

    def build(pattern_id: str, seeds: tuple, literal_hint: str):
        pattern = next(p for p in CATALOG if p.id == pattern_id)
        exercise = apply_pattern(pattern, seeds)
        return build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    rows: list[PublishRow] = []
    source = {
        "source_id": "cpython-v3.14.5",
        "path": "Lib/test/test_string/test_templatelib.py",
        "license": "PSF-2.0",
    }

    for i in range(7):  # introspect
        task = build(
            "intro-strings",
            (seed(f"s-i{i}", f't"Hi{i} {{name}}"', f"Hi{i}"),),
            "intro",
        )
        rows.append(
            _publish_row(
                task,
                property="introspect",
                source_kind="extracted" if i % 2 else "authored",
                seed_id=f"s-i{i}",
                source=source if i % 2 else None,
            )
        )
    for i in range(6):  # render
        task = build(
            "render-template",
            (seed(f"s-r{i}", f't"Hi{i} {{name}}"', f"Hi{i}"),),
            "render",
        )
        rows.append(
            _publish_row(
                task,
                property="render_template",
                source_kind="authored" if i % 2 else "extracted",
                seed_id=f"s-r{i}",
                source=source if i % 2 == 0 else None,
            )
        )
    # construct: one convert row (convert references are seed-independent)
    task = build(
        "construct-convert", (seed("s-c0", 't"Hi {name}"', "Hi"),), "construct"
    )
    rows.append(
        _publish_row(task, property="construct", source_kind="authored", seed_id="s-c0")
    )
    for i in range(4):  # composition (arity 2)
        task = build(
            "compose-templates",
            (
                seed(f"s-t{i}a", f't"Hi{i} {{name}}"', f"Hi{i}"),
                seed(f"s-t{i}b", 't"World"', "World"),
            ),
            "compose_templates",
        )
        rows.append(
            _publish_row(
                task,
                property="compose_templates",
                source_kind="extracted" if i % 2 else "authored",
                seed_id=f"s-t{i}a",
                source=source if i % 2 else None,
            )
        )
    for i in range(2):  # negative
        task = build(
            "negative-fstring",
            (seed(f"s-n{i}", f't"Hi{i} {{name}}"', f"Hi{i}"),),
            "negative",
        )
        rows.append(
            _publish_row(
                task, property="negative", source_kind="authored", seed_id=f"s-n{i}"
            )
        )

    return rows


_MISSING = object()


def _publish(rows, *, calibration=_MISSING, sizes=(24, 16, 8), out_dir, benchmark=()):
    if calibration is _MISSING:
        calibration = _calibration()
    return publish_nested(
        rows,
        sizes=sizes,
        plan=_plan(),
        profile_version=1,
        calibration=calibration,
        benchmark=list(benchmark),
        sandbox=_SANDBOX,
        out_dir=out_dir,
    )


# ---------------------------------------------------------------------------
# Named: snapshot ids are nested
# ---------------------------------------------------------------------------


def test_snapshot_ids_are_nested(tmp_path) -> None:
    """Row ids of the smaller snapshot are a subset of the larger ones."""
    published = _publish(_pool(), out_dir=tmp_path / "pub")
    assert len(published) == 3

    id_sets = [
        {task.id for task in snap.snapshot.tasks}
        for snap in published  # descending: 24, 16, 8
    ]
    assert id_sets[2].issubset(id_sets[1])
    assert id_sets[1].issubset(id_sets[0])
    # Content-derived ids are stable across publishes.
    republished = _publish(_pool(), out_dir=tmp_path / "pub2")
    assert id_sets[0] == {task.id for task in republished[0].snapshot.tasks}


# ---------------------------------------------------------------------------
# Named: manifest declares all strata
# ---------------------------------------------------------------------------


def test_manifest_has_all_strata(tmp_path) -> None:
    """The manifest records every mandatory stratum with counts."""
    published = _publish(_pool(), out_dir=tmp_path / "pub")
    manifest = published[0].manifest

    assert set(manifest["strata"]["property"]) == {
        "introspect",
        "render_template",
        "construct",
        "compose_templates",
        "negative",
    }
    assert set(manifest["strata"]["source_kind"]) == {"extracted", "authored"}
    assert set(manifest["strata"]["role"]) == {"consumer"}
    assert set(manifest["strata"]["domain"]) == {"text"}
    assert manifest["exact_duplicates"] == 0
    assert "benchmark_fingerprint" in manifest
    assert "diversity" in manifest
    assert manifest["profile_version"] == 1


# ---------------------------------------------------------------------------
# Named: lineage is self-contained
# ---------------------------------------------------------------------------


def test_snapshot_lineage_is_self_contained(tmp_path) -> None:
    """Lineage entries carry row ids and inline immutable refs/licenses — no
    path back into a mutable checkout."""
    published = _publish(_pool(), out_dir=tmp_path / "pub")
    for snap in published:
        for entry in snap.lineage:
            assert entry["row_id"]
        # At least one extracted row carries its source ref + license inline.
        sourced = [e for e in published[0].lineage if e.get("license")]
        assert sourced
        assert all(e["path"] for e in sourced)
        assert all(e["source_id"] for e in sourced)

    # NOTICE aggregates attribution from the inline inventory.
    notice = (tmp_path / "pub/snapshots/24/NOTICE").read_text(encoding="utf-8")
    assert "PSF-2.0" in notice


# ---------------------------------------------------------------------------
# Named: publishing requires calibrated provider result
# ---------------------------------------------------------------------------


def test_publish_requires_calibrated_provider_result(tmp_path) -> None:
    """Publishing refuses without a calibration record, or with a stale
    profile version."""
    rows = _pool()
    with pytest.raises(CalibrationError, match="calibration"):
        _publish(rows, calibration=None, out_dir=tmp_path / "a")

    stale = _calibration(profile_version=0)
    with pytest.raises(CalibrationError, match="profile version"):
        _publish(rows, calibration=stale, out_dir=tmp_path / "b")


# ---------------------------------------------------------------------------
# Happy path: snapshot ingests through the provider
# ---------------------------------------------------------------------------


def test_published_snapshot_ingests_through_provider(tmp_path) -> None:
    """The largest published snapshot round-trips through provider ingest."""
    published = _publish(_pool(), out_dir=tmp_path / "pub")
    snap = published[0]
    assert isinstance(snap, PublishedSnapshot)
    assert (tmp_path / "pub/snapshots/24/tstrings.jsonl").exists()

    registry = TrustedPolicyRegistry()
    registry.register(TStringPolicy())
    loaded = load_snapshot(
        tmp_path / "pub/snapshots/24/tstrings.jsonl", registry=registry
    )
    assert loaded.manifest.task_count == snap.snapshot.manifest.task_count
    assert loaded.manifest.fingerprint == snap.snapshot.manifest.fingerprint

    # Re-published bytes are identical (immutable).
    _publish(_pool(), out_dir=tmp_path / "pub2")
    assert (tmp_path / "pub/snapshots/24/tstrings.jsonl").read_bytes() == (
        tmp_path / "pub2/snapshots/24/tstrings.jsonl"
    ).read_bytes()
