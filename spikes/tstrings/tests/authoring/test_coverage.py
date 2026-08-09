"""SP5 Task 4: coverage, authoring, and collection checkpoint.

Focused command: ``uv run python -m pytest tests/authoring/test_coverage.py -q``.
"""

from pathlib import Path

from satyrn_model.authoring.models import (
    ComposeTemplates,
    Construct,
    Introspect,
    NegativeControl,
    PolicyIntent,
    RenderTemplate,
    Seed,
    SourceEvidence,
    SourceExerciseCandidate,
    SourceOrigin,
    TaskIntent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_origin() -> SourceOrigin:
    return SourceOrigin(
        source_id="cpython-v3.14.5",
        path="Lib/test/test_templatelib.py",
        line_start=1,
        line_end=1,
        license="PSF-2.0",
    )


def _make_candidate(
    prop_type: str = "introspect",
    seed_literal: str = 't"Hello {name}"',
) -> SourceExerciseCandidate:
    """Build a fixture candidate with a specific property type."""
    policy = PolicyIntent(
        requires_template="introspect" in prop_type or "render" in prop_type,
        templatelib_apis_used=frozenset(["strings"]),
    )
    if prop_type == "introspect":
        prop = (Introspect(target=".strings", index=0, field="strings"),)
    elif prop_type == "render_template":
        prop = (RenderTemplate(),)
    elif prop_type == "construct-interpolation":
        prop = (Construct(operation="Interpolation"),)
        policy = PolicyIntent(
            requires_template=False, templatelib_apis_used=frozenset()
        )
    elif prop_type == "construct-convert":
        prop = (Construct(operation="convert"),)
        policy = PolicyIntent(
            requires_template=False, templatelib_apis_used=frozenset()
        )
    elif prop_type == "transform":
        prop = (ComposeTemplates(),)
    elif prop_type == "negative":
        prop = (NegativeControl(expected_solution_kind="f-string"),)
        policy = PolicyIntent(
            requires_template=False, templatelib_apis_used=frozenset()
        )
    else:
        raise ValueError(f"unknown prop_type: {prop_type}")

    return SourceExerciseCandidate(
        id=f"cand-{prop_type}",
        origin=_make_origin(),
        evidence=SourceEvidence(function_name="test_x"),
        intent=TaskIntent(
            id=f"intent-{prop_type}",
            description=f"coverage fixture: {prop_type}",
            properties=prop,
            policy_intent=policy,
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_coverage_runs_without_provider() -> None:
    """Coverage analysis produces a report from extraction data alone."""
    from satyrn_model.authoring.coverage import CoverageReport, analyze_coverage

    candidates = [
        _make_candidate("introspect"),
        _make_candidate("introspect"),
        _make_candidate("render_template"),
        _make_candidate("negative"),
    ]
    seeds: list[Seed] = []  # no authored seeds yet

    report = analyze_coverage(candidates, seeds)

    assert isinstance(report, CoverageReport)
    assert report.property_counts["introspect"] == 2
    assert report.property_counts["render_template"] == 1
    assert report.property_counts["negative"] == 1
    assert report.property_counts["construct"] == 0  # gap
    assert report.property_counts["compose_templates"] == 0  # gap
    assert report.source_counts["extracted"] == 4
    assert report.source_counts["authored"] == 0
    assert not report.rows_are_provider_qualified
    assert "construct" in report.gaps
    assert "compose_templates" in report.gaps


def test_authored_seed_closes_reported_gap() -> None:
    """Adding an authored seed increases the authored count in coverage."""
    from satyrn_model.authoring.coverage import analyze_coverage

    candidates = [_make_candidate("introspect")]
    seeds_before: list[Seed] = []

    before = analyze_coverage(candidates, seeds_before)
    assert before.source_counts["authored"] == 0

    seed = Seed(
        id="seed-auth-1",
        literal='t"Hello {greeting}"',
        free_names=("greeting",),
        bindings=(("greeting", "'hi'"),),
        occurrence_ids=("occ-auth-1",),
        kind="authored",
    )
    after = analyze_coverage(candidates, [seed])
    assert after.source_counts["authored"] == 1
    assert after.source_counts["extracted"] == 1


def test_same_skeleton_distinct_semantics_are_retained() -> None:
    """Seeds sharing a structural skeleton are still distinct seeds."""
    from satyrn_model.authoring.coverage import analyze_coverage, skeleton_of

    seed_a = Seed(
        id="a",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", "'Alice'"),),
        occurrence_ids=("oa",),
        kind="authored",
    )
    seed_b = Seed(
        id="b",
        literal='t"Goodbye {name}"',
        free_names=("name",),
        bindings=(("name", "'Bob'"),),
        occurrence_ids=("ob",),
        kind="authored",
    )

    # Same skeleton, different content.
    skel_a = skeleton_of(seed_a)
    skel_b = skeleton_of(seed_b)
    assert skel_a == skel_b, (
        f"same AST shape should produce same skeleton, got {skel_a!r} vs {skel_b!r}"
    )

    # But they are distinct seeds.
    report = analyze_coverage([], [seed_a, seed_b])
    assert report.source_counts["authored"] == 2
    assert report.skeleton_buckets == 1  # one distinct skeleton


def test_review_decision_round_trip(tmp_path: Path) -> None:
    """Seed review decisions survive JSONL round-trip."""
    from satyrn_model.authoring.review import (
        ReviewDecision,
        read_decisions,
        write_decisions,
    )

    d = ReviewDecision(
        seed_id="abc",
        verdict="accepted",
        reason="looks good",
        content_sha256="sha",
    )
    path = tmp_path / "decisions.jsonl"
    write_decisions([d], path)
    loaded = read_decisions(path)
    assert len(loaded) == 1
    assert loaded[0] == d


def test_coverage_md_is_written(tmp_path: Path) -> None:
    """Coverage report is emitted as Markdown with all required sections."""
    from satyrn_model.authoring.coverage import analyze_coverage, write_coverage_md

    candidates = [
        _make_candidate("introspect"),
        _make_candidate("render_template"),
    ]
    seeds: list[Seed] = [
        Seed(
            id="s1",
            literal='t"{x}"',
            free_names=("x",),
            bindings=(("x", "1"),),
            occurrence_ids=("o1",),
            kind="authored",
        )
    ]
    report = analyze_coverage(candidates, seeds)
    path = tmp_path / "coverage.md"
    write_coverage_md(report, path)

    text = path.read_text(encoding="utf-8")
    assert "# SP5 Coverage Report" in text
    assert "## Property Coverage" in text
    assert "## Source Coverage" in text
    assert "## Gaps" in text
    assert "## Structural Diversity" in text
    assert "introspect" in text
    assert "Not provider-qualified" in text
