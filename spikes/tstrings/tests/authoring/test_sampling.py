"""SP5 Task 9: pilot sampling and calibrated thresholds.

Focused command: ``uv run python -m pytest tests/authoring/test_sampling.py -q``.

Covers the plan's two named tests — ``test_sampling_is_nested_and_stratified``
and ``test_final_500_requires_calibration_record`` — plus calibration
derivation, record persistence, and plan validation.
"""

import pytest

from satyrn_model.authoring.sampling import (
    CalibrationError,
    CalibrationRecord,
    PlanValidationError,
    SampleRow,
    SamplingPlan,
    derive_calibration,
    finalize_500,
    read_calibration,
    select_pilot,
    write_calibration,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row(
    row_id: str,
    source_kind: str = "authored",
    property: str = "introspect",
    pattern_id: str = "intro-strings",
    seed_id: str = "seed-1",
) -> SampleRow:
    return SampleRow(
        row_id=row_id,
        source_kind=source_kind,
        property=property,
        pattern_id=pattern_id,
        seed_id=seed_id,
        skeleton=f"skel-{property}",
        prompt=f"prompt-{row_id}",
    )


def _plan(tmp_path) -> SamplingPlan:
    return SamplingPlan.load(
        tmp_path / "sampling.toml",
        text="""\
[plan]
target_rows = 100
nested_order = ["source_kind", "property", "seed"]

[plan.strata.source_kind]
extracted = 0.40
authored = 0.60

[plan.strata.property]
introspect = 0.50
render = 0.50

# seed level: no per-seed quotas; distinct seeds are prioritized.
""",
    )


def _pool() -> list[SampleRow]:
    """A pool large enough to fill every quota for target_rows=100.

    Quotas: extracted 40 (introspect 20, render 20), authored 60
    (introspect 30, render 30).  The extracted-introspect bucket holds
    24 rows across 4 distinct seeds (6 each) so leaf-level seed
    prioritization is actually exercised.
    """
    rows: list[SampleRow] = []
    for i in range(24):  # extracted introspect: 4 seeds x 6 rows
        rows.append(
            _row(
                f"e-int-{i}",
                source_kind="extracted",
                property="introspect",
                pattern_id="intro-strings",
                seed_id=f"seed-e{i % 4}",
            )
        )
    for i in range(20):  # extracted render: 20 distinct seeds
        rows.append(
            _row(
                f"e-ren-{i}",
                source_kind="extracted",
                property="render",
                pattern_id="render-join",
                seed_id=f"seed-r{i}",
            )
        )
    for i in range(40):  # authored introspect
        rows.append(
            _row(
                f"a-int-{i}",
                source_kind="authored",
                property="introspect",
                pattern_id="intro-strings",
                seed_id=f"seed-a{i}",
            )
        )
    for i in range(40):  # authored render
        rows.append(
            _row(
                f"a-ren-{i}",
                source_kind="authored",
                property="render",
                pattern_id="render-join",
                seed_id=f"seed-b{i}",
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Named: nested and stratified sampling
# ---------------------------------------------------------------------------


def test_sampling_is_nested_and_stratified(tmp_path) -> None:
    """Selection allocates per the nested order and strata, and prioritizes
    distinct seeds at the leaf level."""
    plan = _plan(tmp_path)
    selected = select_pilot(_pool(), plan=plan, target_rows=100)

    assert len(selected) == 100  # pool fills every quota

    # Level 1: source_kind proportions hold.
    extracted = [r for r in selected if r.source_kind == "extracted"]
    authored = [r for r in selected if r.source_kind == "authored"]
    assert len(extracted) == 40
    assert len(authored) == 60

    # Level 2: property proportions hold within the pool.
    introspect = [r for r in selected if r.property == "introspect"]
    render = [r for r in selected if r.property == "render"]
    assert len(introspect) == 50
    assert len(render) == 50

    # Leaf: distinct seeds come first — the selected prefix before any
    # repeat seed covers every distinct seed in the extracted-introspect
    # bucket (4 seeds x 6 rows each, quota 20).
    e_int = [
        r
        for r in selected
        if r.property == "introspect" and r.source_kind == "extracted"
    ]
    seen: set[str] = set()
    prefix = 0
    for r in e_int:
        if r.seed_id in seen:
            break
        seen.add(r.seed_id)
        prefix += 1
    assert prefix == len({r.seed_id for r in e_int}) == 4


def test_committed_sampling_toml_owns_target_and_seed_leaf() -> None:
    """Composition marginals have one owner; sampling keeps only the leaf."""
    from pathlib import Path as _Path

    plan = SamplingPlan.load(_Path(__file__).resolve().parents[2] / "sampling.toml")
    rows = [
        SampleRow(
            row_id=f"r{i}",
            source_kind="authored",
            property="introspect",
            pattern_id="intro-strings",
            seed_id=f"seed-{i % 40}",
        )
        for i in range(600)
    ]
    selected = select_pilot(rows, plan=plan, target_rows=500)
    assert len(selected) == 500
    assert plan.nested_order == ("seed",)


def test_plan_validation_rejects_bad_proportions(tmp_path) -> None:
    """A plan whose strata do not sum to one is rejected."""
    with pytest.raises(PlanValidationError):
        SamplingPlan.load(
            tmp_path / "bad.toml",
            text="""\
[plan]
target_rows = 100
nested_order = ["source_kind"]

[plan.strata.source_kind]
extracted = 0.40
authored = 0.40
""",
        )


# ---------------------------------------------------------------------------
# Named: the final 500 requires a calibration record
# ---------------------------------------------------------------------------


def test_final_500_requires_calibration_record(tmp_path) -> None:
    """Finalizing a 500-row selection refuses without a matching calibration
    record, and passes only when profile version and target agree."""
    plan = _plan(tmp_path)
    selected = select_pilot(_pool(), plan=plan, target_rows=100)

    # No calibration record at all.
    with pytest.raises(CalibrationError, match="calibration"):
        finalize_500(selected, None, profile_version=1)

    # Stale profile version — profile changed, old pilot does not match.
    stale = CalibrationRecord(
        profile_version=0,
        target_rows=100,
        derived_at="2026-08-02T00:00:00+00:00",
        diversity={"distinct_skeletons": 2},
        composition_tolerance={"introspect": [0.40, 0.60]},
        review_budget=0.10,
    )
    with pytest.raises(CalibrationError, match="profile version"):
        finalize_500(selected, stale, profile_version=1)

    # Target mismatch.
    wrong_target = CalibrationRecord(
        profile_version=1,
        target_rows=500,
        derived_at="2026-08-02T00:00:00+00:00",
        diversity={"distinct_skeletons": 2},
        composition_tolerance={"introspect": [0.40, 0.60]},
        review_budget=0.10,
    )
    with pytest.raises(CalibrationError, match="target"):
        finalize_500(selected, wrong_target, profile_version=1)

    # Matching record passes (targeting the actual selection size).
    ok = CalibrationRecord(
        profile_version=1,
        target_rows=len(selected),
        derived_at="2026-08-02T00:00:00+00:00",
        diversity={"distinct_skeletons": 2},
        composition_tolerance={"introspect": [0.40, 0.60]},
        review_budget=0.10,
    )
    finalize_500(selected, ok, profile_version=1)


# ---------------------------------------------------------------------------
# Calibration derivation and persistence
# ---------------------------------------------------------------------------


def test_derive_calibration_records_diversity_and_tolerance(tmp_path) -> None:
    """Derivation records observed diversity and composition tolerance for
    the pilot, and never selects a semantic-near gate."""
    plan = _plan(tmp_path)
    selected = select_pilot(_pool(), plan=plan, target_rows=100)
    record = derive_calibration(selected, profile_version=1, target_rows=100)

    assert record.diversity["distinct_skeletons"] >= 1
    assert "introspect" in record.composition_tolerance
    # SP5 never selects contamination/near-duplicate thresholds.
    assert record.semantic_near_gate is None

    path = tmp_path / "calibration.json"
    write_calibration(record, path)
    assert read_calibration(path) == record
