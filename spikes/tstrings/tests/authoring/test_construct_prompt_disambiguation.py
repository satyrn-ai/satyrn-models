"""Two construct-interpolation-* descriptions became ambiguous once the
2026-08-09 construct-patterns batch added siblings that name their
conversion/expression explicitly. See docs/superpowers/plans/
2026-08-09-sp5-construct-prompt-fix.md."""

from pathlib import Path

from satyrn_model.authoring.patterns.approvals import read_approvals
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import pattern_input_fingerprint

APPROVALS_PATH = Path(__file__).resolve().parents[2] / "patterns" / "approvals.jsonl"


def test_conversion_format_description_names_its_conversion() -> None:
    pattern = next(p for p in CATALOG if p.id == "construct-interpolation-conversion-format")
    assert "!r" in pattern.description
    assert pattern.description != "construct an Interpolation with conversion and format metadata"


def test_expression_description_names_its_expression_kind() -> None:
    pattern = next(p for p in CATALOG if p.id == "construct-interpolation-expression")
    assert "attribute" in pattern.description
    assert pattern.description != "construct an Interpolation preserving its source expression"


def test_no_two_construct_interpolation_patterns_share_an_underdetermined_description() -> None:
    """Regression guard for the ambiguity this fix closes: no two patterns in
    the construct-interpolation-* family should have descriptions that read
    as a superset of one another once a more specific sibling exists."""
    family = [p for p in CATALOG if p.id.startswith("construct-interpolation-")]
    descriptions = [p.description for p in family]
    assert len(descriptions) == len(set(descriptions)), "duplicate descriptions in family"


def test_renamed_patterns_have_fresh_approvals() -> None:
    approvals = read_approvals(APPROVALS_PATH)
    by_id = {a.pattern_id: a for a in approvals}
    by_pattern_id = {p.id: p for p in CATALOG}
    for pattern_id in (
        "construct-interpolation-conversion-format",
        "construct-interpolation-expression",
    ):
        pattern = by_pattern_id[pattern_id]
        approval = by_id[pattern_id]
        assert approval.pattern_input_fingerprint == pattern_input_fingerprint(pattern)
