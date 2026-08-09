"""construct-interpolation-expression-format used a >10 width, inconsistent
with the >8 convention every other format-bearing construct pattern uses,
and unstated in its prompt either way. See docs/superpowers/plans/
2026-08-09-sp5-construct-width-fix.md."""

from pathlib import Path

from satyrn_model.authoring.patterns.approvals import read_approvals
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import pattern_input_fingerprint

APPROVALS_PATH = Path(__file__).resolve().parents[2] / "patterns" / "approvals.jsonl"


def test_all_construct_interpolation_format_specs_use_the_same_width() -> None:
    family = [p for p in CATALOG if p.id.startswith("construct-interpolation-")]
    widths = {
        p.property_specs[0].format_spec
        for p in family
        if p.property_specs[0].format_spec
    }
    assert widths == {">8"}, f"inconsistent format-spec widths in the family: {widths}"


def test_expression_format_pattern_has_fresh_approval() -> None:
    approvals = read_approvals(APPROVALS_PATH)
    by_id = {a.pattern_id: a for a in approvals}
    pattern = next(
        p for p in CATALOG if p.id == "construct-interpolation-expression-format"
    )
    approval = by_id[pattern.id]
    assert approval.pattern_input_fingerprint == pattern_input_fingerprint(pattern)
