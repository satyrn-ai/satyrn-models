"""Six new construct-interpolation patterns closing expression/conversion/
format-spec gaps. See docs/superpowers/specs/
2026-08-09-sp5-construct-patterns-design.md for the coverage table these
close."""

from pathlib import Path

from satyrn_model.authoring.generate import generate_all
from satyrn_model.authoring.models import Construct
from satyrn_model.authoring.patterns.approvals import read_approvals
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import classify

APPROVALS_PATH = Path(__file__).resolve().parents[2] / "patterns" / "approvals.jsonl"

NEW_PATTERN_IDS = {
    "construct-interpolation-subscript",
    "construct-interpolation-call",
    "construct-interpolation-expression-r",
    "construct-interpolation-expression-format",
    "construct-interpolation-s-format",
    "construct-interpolation-a-format",
}

EXPECTED_SHAPES = {
    "construct-interpolation-subscript": (None, "items[0]", ""),
    "construct-interpolation-call": (None, "get_name()", ""),
    "construct-interpolation-expression-r": ("r", "user.name", ""),
    "construct-interpolation-expression-format": (None, "user.name", ">10"),
    "construct-interpolation-s-format": ("s", "value", ">8"),
    "construct-interpolation-a-format": ("a", "value", ">8"),
}


def test_six_new_construct_patterns_are_in_the_catalog() -> None:
    ids = {p.id for p in CATALOG}
    missing = NEW_PATTERN_IDS - ids
    assert not missing, f"catalog is missing: {missing}"


def test_new_patterns_have_the_expected_construct_shape() -> None:
    by_id = {p.id: p for p in CATALOG}
    for pattern_id, (conversion, expression, format_spec) in EXPECTED_SHAPES.items():
        pattern = by_id[pattern_id]
        assert len(pattern.property_specs) == 1
        spec = pattern.property_specs[0]
        assert spec.kind == "construct"
        assert spec.operation == "Interpolation"
        assert spec.conversion == conversion
        assert spec.expression == expression
        assert spec.format_spec == format_spec
        assert pattern.labels == frozenset({"construct"})
        assert pattern.requires == ("string.templatelib.Interpolation",)


def test_new_patterns_classify_as_construct() -> None:
    from satyrn_model.authoring.patterns.registry import build_properties

    by_id = {p.id: p for p in CATALOG}
    for pattern_id in NEW_PATTERN_IDS:
        pattern = by_id[pattern_id]
        properties = build_properties(pattern.property_specs)
        assert classify(properties) == frozenset({"construct"})
        assert isinstance(properties[0], Construct)


def test_format_specs_are_valid_for_the_hardcoded_string_value() -> None:
    """Every new format_spec must not raise against 'World' -- the value
    task_builder.py's _ref_construct always hardcodes for Interpolation
    construction."""
    by_id = {p.id: p for p in CATALOG}
    for pattern_id in NEW_PATTERN_IDS:
        spec = by_id[pattern_id].property_specs[0]
        format("World", spec.format_spec)  # must not raise


def test_new_patterns_are_approved() -> None:
    approvals_by_id = {a.pattern_id: a for a in read_approvals(APPROVALS_PATH)}
    missing = NEW_PATTERN_IDS - set(approvals_by_id)
    assert not missing, f"no approval recorded for: {missing}"


def test_each_new_pattern_generates_exactly_one_row() -> None:
    """Construct patterns are arity-0: one canonical row per pattern,
    independent of the seed pool (see the design doc's traced mechanism)."""
    approvals = read_approvals(APPROVALS_PATH)
    by_id = {p.id: p for p in CATALOG}
    for pattern_id in NEW_PATTERN_IDS:
        pattern = by_id[pattern_id]
        rows = generate_all([pattern], (), approvals)
        assert len(rows) == 1
        assert rows[0].seeds == ()
