"""SP5 Task 7: patterns, transitive approval, and generated cache.

Focused command: ``uv run python -m pytest tests/authoring/test_patterns.py -q``.

Covers the plan's three named tests —
``test_helper_change_invalidates_approval``, ``test_prompt_values_check_strings_fails``,
``test_property_feature_mismatch_fails_pattern`` — plus classifier coverage,
cache self-invalidation, and audit persistence.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from satyrn_model.authoring.generate import (
    generate_all,
    generate_cached,
    generation_fingerprint,
    read_generated,
    write_generated,
)
from satyrn_model.authoring.models import (
    ComposeTemplates,
    Construct,
    Domain,
    Introspect,
    JoinStaticParts,
    NegativeControl,
    RenderTemplate,
    Seed,
)
from satyrn_model.authoring.patterns.approvals import (
    ApprovalError,
    PatternApproval,
    audit_pattern,
    read_approvals,
    require_approval,
)
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import (
    Pattern,
    PatternValidationError,
    PromptVariant,
    PropertySpec,
    classify,
    pattern_input_fingerprint,
    validate_pattern,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed(
    sid: str, literal: str, bindings: tuple = (), domain: Domain = "text"
) -> Seed:
    return Seed(
        id=sid,
        literal=literal,
        free_names=tuple(n for n, _ in bindings),
        bindings=tuple(bindings),
        occurrence_ids=(f"occ-{sid}",),
        kind="authored",
        domain=domain,
    )


SEED_A = _seed("seed-a", 't"Hello {name}"', (("name", '"World"'),))
SEED_B = _seed("seed-b", 't"Goodbye {name}"', (("name", '"World"'),))


def _intro_pattern(**kw) -> Pattern:
    base = dict(
        id="intro-strings",
        description="introspect the static string parts of a template",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".strings", index=0, field="strings"
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("templatelib",),
        witnesses=("introspect-strings",),
    )
    base.update(kw)
    return Pattern(**base)


# ---------------------------------------------------------------------------
# Named: helper change invalidates approval
# ---------------------------------------------------------------------------


def test_helper_change_invalidates_approval() -> None:
    """A declared helper change alters the fingerprint and stale approvals
    refuse generation."""
    p1 = _intro_pattern(requires=("templatelib", "helper-v1"))
    p2 = dataclasses.replace(p1, requires=("templatelib", "helper-v2"))

    fp1 = pattern_input_fingerprint(p1)
    fp2 = pattern_input_fingerprint(p2)
    assert fp1 != fp2

    approvals = [
        PatternApproval(
            pattern_id=p1.id,
            pattern_input_fingerprint=fp1,
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]

    # The changed pattern no longer matches its approval — refused.
    with pytest.raises(ApprovalError, match="stale"):
        require_approval(p2, approvals, fp2)

    # Generation refuses stale approval too.
    with pytest.raises(ApprovalError, match="stale"):
        generate_all([p2], (SEED_A,), approvals)


# ---------------------------------------------------------------------------
# Named: cross-projection gate (prompt vs checks)
# ---------------------------------------------------------------------------


def test_prompt_values_check_strings_fails() -> None:
    """A pattern whose prompt claims 'values' but whose checks introspect
    '.strings' is rejected: prompt and checks must be projections of one
    intent."""
    bad = _intro_pattern(
        id="bad-cross",
        description="introspect the values of a template",
    )
    with pytest.raises(PatternValidationError, match="values"):
        validate_pattern(bad)


def test_prompt_check_subjects_consistent_passes() -> None:
    """Matching prompt/check subjects validate cleanly."""
    ok = _intro_pattern(description="introspect the strings of a template")
    validate_pattern(ok)


def test_every_prompt_family_must_match_the_property_subject() -> None:
    pattern = _intro_pattern(
        prompt_variants=(
            PromptVariant(id="concise", text="inspect template strings"),
            PromptVariant(id="wrong", text="inspect template values"),
        )
    )

    with pytest.raises(PatternValidationError, match="prompt family 'wrong'"):
        validate_pattern(pattern)


def test_prompt_families_are_reviewed_generation_inputs() -> None:
    base = _intro_pattern()
    varied = dataclasses.replace(
        base,
        prompt_variants=(
            PromptVariant(id="concise", text=base.description),
            PromptVariant(id="program", text="write code to inspect strings"),
        ),
    )

    assert pattern_input_fingerprint(varied) != pattern_input_fingerprint(base)


def test_generate_all_emits_one_row_per_prompt_family_and_seed() -> None:
    pattern = _intro_pattern(
        prompt_variants=(
            PromptVariant(id="concise", text="inspect template strings"),
            PromptVariant(id="program", text="write code to inspect strings"),
        )
    )
    approvals = [
        PatternApproval(
            pattern_id=pattern.id,
            pattern_input_fingerprint=pattern_input_fingerprint(pattern),
            approved_at="2026-08-03T00:00:00+00:00",
        )
    ]

    rows = generate_all([pattern], (SEED_A, SEED_B), approvals)

    assert len(rows) == 4
    assert {row.prompt_family for row in rows} == {"concise", "program"}
    assert len({row.id for row in rows}) == 4


# ---------------------------------------------------------------------------
# Named: composition-classifier gate
# ---------------------------------------------------------------------------


def test_property_feature_mismatch_fails_pattern() -> None:
    """A pattern that declares a label its properties cannot produce fails:
    nothing self-declared is left to game."""
    bad = _intro_pattern(
        id="bad-labels",
        labels=frozenset({"render"}),
    )
    with pytest.raises(PatternValidationError, match="labels"):
        validate_pattern(bad)


def test_render_pattern_requires_executable_counterexample_witnesses() -> None:
    """A render label cannot be approved without the known wrong idioms."""
    pattern = next(item for item in CATALOG if item.id == "render-template")
    incomplete = dataclasses.replace(pattern, witnesses=("render-conversion-format",))

    with pytest.raises(PatternValidationError, match="reject-template-str"):
        validate_pattern(incomplete)

    validate_pattern(pattern)


def test_classify_derives_labels_from_every_property() -> None:
    """Labels are mechanically derived from every Property variant, including
    both Construct operations and negative controls."""
    props = (
        Introspect(target=".strings", index=0, field="strings"),
        RenderTemplate(),
        JoinStaticParts(),
        ComposeTemplates(),
        Construct(operation="Interpolation"),
        Construct(operation="convert"),
        NegativeControl(expected_solution_kind="fstring"),
    )
    assert classify(props) == frozenset(
        {
            "introspect",
            "render_template",
            "join_static_parts",
            "compose_templates",
            "construct",
            "negative",
        }
    )


# ---------------------------------------------------------------------------
# Approval lifecycle and audit
# ---------------------------------------------------------------------------


def test_audit_pattern_records_fingerprint(tmp_path) -> None:
    """audit_pattern records the current fingerprint; approval round-trips."""
    p = _intro_pattern()
    path = tmp_path / "approvals.jsonl"
    audit_pattern(p, path)

    approvals = read_approvals(path)
    assert len(approvals) == 1
    assert approvals[0].pattern_id == p.id
    assert approvals[0].pattern_input_fingerprint == pattern_input_fingerprint(p)


def test_audit_pattern_refuses_invalid_pattern_without_writing(tmp_path) -> None:
    """Approval is a semantic gate, not merely a fingerprinting operation."""
    invalid = dataclasses.replace(_intro_pattern(), witnesses=())
    path = tmp_path / "approvals.jsonl"

    with pytest.raises(PatternValidationError, match="lacks witness"):
        audit_pattern(invalid, path)

    assert not path.exists()


def test_entire_catalog_validates() -> None:
    """Every pattern shipped for approval satisfies the executable gates."""
    for pattern in CATALOG:
        validate_pattern(pattern)
        assert {variant.id for variant in pattern.prompt_variants} == {
            "direct",
            "python-program",
            "pep750-request",
        }
        assert all(variant.include_seed_context for variant in pattern.prompt_variants)


def test_every_catalog_pattern_has_a_fresh_approval() -> None:
    """Regression guard: a pattern with no (or stale) approval makes
    generate_all raise ApprovalError and blocks the entire corpus build.
    Two independent reviews missed exactly this on 2026-08-09 because
    nothing asserted it."""
    approvals_path = Path(__file__).resolve().parents[2] / "patterns" / "approvals.jsonl"
    approvals = {a.pattern_id: a for a in read_approvals(approvals_path)}

    missing = [p.id for p in CATALOG if p.id not in approvals]
    assert not missing, f"patterns with no approval at all: {missing}"

    stale = [
        p.id
        for p in CATALOG
        if approvals[p.id].pattern_input_fingerprint != pattern_input_fingerprint(p)
    ]
    assert not stale, f"patterns with a stale (fingerprint-mismatched) approval: {stale}"


def test_generate_refuses_missing_approval() -> None:
    """Generation refuses a pattern with no approval at all."""
    p = _intro_pattern()
    with pytest.raises(ApprovalError, match="no approval"):
        generate_all([p], (SEED_A,), [])


def test_generate_all_applies_patterns_to_seeds() -> None:
    """Approved patterns emit one GeneratedExercise per arity chunk."""
    p = _intro_pattern()
    approvals = [
        PatternApproval(
            pattern_id=p.id,
            pattern_input_fingerprint=pattern_input_fingerprint(p),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    rows = generate_all([p], (SEED_A, SEED_B), approvals)
    assert len(rows) == 2  # arity 1 → one exercise per seed
    for row in rows:
        assert row.pattern_id == p.id
        assert row.pattern_fingerprint == pattern_input_fingerprint(p)
        assert isinstance(row.properties[0], Introspect)


def test_generate_all_emits_one_canonical_seed_independent_construct() -> None:
    """Construct operations do not multiply one task across unrelated seeds."""
    pattern = next(item for item in CATALOG if item.id == "construct-convert")
    approvals = [
        PatternApproval(
            pattern_id=pattern.id,
            pattern_input_fingerprint=pattern_input_fingerprint(pattern),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    rows = generate_all([pattern], (SEED_A, SEED_B), approvals)
    assert len(rows) == 1
    assert rows[0].seeds == ()


def test_composition_generation_never_mixes_seed_domains() -> None:
    """A composed task remains attributable to one semantic domain."""
    pattern = next(item for item in CATALOG if item.id == "compose-templates")
    approvals = [
        PatternApproval(
            pattern_id=pattern.id,
            pattern_input_fingerprint=pattern_input_fingerprint(pattern),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    seeds = (
        _seed("html-a", 't"<b>A</b>"', domain="html"),
        _seed("sql-a", 't"SELECT a"', domain="sql"),
        _seed("html-b", 't"<b>B</b>"', domain="html"),
        _seed("sql-b", 't"SELECT b"', domain="sql"),
    )

    rows = generate_all([pattern], seeds, approvals)

    assert len(rows) == 6
    domains = [{seed.domain for seed in row.seeds} for row in rows]
    assert domains.count({"html"}) == 3
    assert domains.count({"sql"}) == 3


def test_generation_groups_composition_by_source_kind_and_domain() -> None:
    pattern = next(item for item in CATALOG if item.id == "compose-templates")
    approvals = [
        PatternApproval(
            pattern_id=pattern.id,
            pattern_input_fingerprint=pattern_input_fingerprint(pattern),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    extracted = dataclasses.replace(SEED_A, id="seed-extracted", kind="extracted")
    rows = generate_all(
        [pattern], (SEED_A, extracted, SEED_B, extracted), approvals
    )

    assert len(rows) == 6
    assert all(len({seed.kind for seed in row.seeds}) == 1 for row in rows)


# ---------------------------------------------------------------------------
# Transient generated cache: self-invalidates on any input change
# ---------------------------------------------------------------------------


def test_generated_cache_self_invalidates_on_input_change(tmp_path) -> None:
    """A cached artifact whose input fingerprint no longer matches is
    regenerated and rewritten."""
    p = _intro_pattern()
    approvals = [
        PatternApproval(
            pattern_id=p.id,
            pattern_input_fingerprint=pattern_input_fingerprint(p),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    cache = tmp_path / "generated.jsonl"

    rows1 = generate_all([p], (SEED_A,), approvals)
    write_generated(rows1, generation_fingerprint([p], (SEED_A,)), cache)

    # Seed set changed — cache is stale, regeneration must happen.
    rows2 = generate_cached([p], (SEED_B,), approvals, cache)
    assert rows2 == generate_all([p], (SEED_B,), approvals)
    assert [r.seeds[0].id for r in rows2] == ["seed-b"]

    fp, cached_rows = read_generated(cache)
    assert fp == generation_fingerprint([p], (SEED_B,))
    assert [r.seeds[0].id for r in cached_rows] == ["seed-b"]


def test_generation_fingerprint_includes_reviewed_domain() -> None:
    """Changing a seed's composition label invalidates generated artifacts."""
    html_seed = dataclasses.replace(SEED_A, domain="html")

    assert generation_fingerprint([], (SEED_A,)) != generation_fingerprint(
        [], (html_seed,)
    )


def test_generated_cache_hits_when_fingerprint_matches(tmp_path) -> None:
    """Unchanged inputs return the cached rows, not regenerated ones."""
    p = _intro_pattern()
    approvals = [
        PatternApproval(
            pattern_id=p.id,
            pattern_input_fingerprint=pattern_input_fingerprint(p),
            approved_at="2026-08-02T00:00:00+00:00",
        )
    ]
    cache = tmp_path / "generated.jsonl"
    rows = generate_all([p], (SEED_A,), approvals)
    write_generated(rows, generation_fingerprint([p], (SEED_A,)), cache)

    out = generate_cached([p], (SEED_A,), approvals, cache)
    assert out == rows
