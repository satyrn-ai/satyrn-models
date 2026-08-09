"""SP5 Task 3: safe AST extraction into candidates.

Focused command: ``uv run python -m pytest tests/authoring/test_extract.py -q``.
Tests consume the committed fixture corpus in
``tests/authoring/fixtures/collection_cases.json``.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "collection_cases.json"


def _load_fixtures() -> list[dict]:
    """Load the source-only fixture corpus."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fixture_by_id(fid: str) -> dict:
    for f in _load_fixtures():
        if f["id"] == fid:
            return f
    raise KeyError(f"fixture {fid!r} not found")


# ---------------------------------------------------------------------------
# Stage 1 — literal extraction (exact span)
# ---------------------------------------------------------------------------


def test_literal_multiline_extracts_exact_span() -> None:
    """A multiline t-string is extracted with its exact literal text."""
    from satyrn_model.authoring.extract import find_template_literals

    case = _fixture_by_id("literal_multiline")
    literals = find_template_literals(case["source"])
    assert len(literals) == 1, f"expected 1 literal, got {len(literals)}"
    lit = literals[0]
    expected = 't"""hello {name}\\nworld"""'
    assert lit.literal == expected, f"expected {expected!r}, got {lit.literal!r}"
    assert lit.free_names == ("name",)


def test_nested_shadowing_is_rejected() -> None:
    """A literal whose free name is shadowed in a nested scope is rejected."""
    from satyrn_model.authoring.extract import (
        ScopeShadowingError,
        find_template_literals,
    )

    case = _fixture_by_id("nested_shadowing")
    with pytest.raises(ScopeShadowingError, match="shadowed"):
        find_template_literals(case["source"])


# ---------------------------------------------------------------------------
# Stage 2 — assertion splitting, evidence, safety
# ---------------------------------------------------------------------------


def test_multiple_cases_split_at_assertion_boundaries() -> None:
    """Two independent assertions in one method → split into two candidates."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("multiple_cases")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 2, (
        f"expected 2 candidates from two assertions, got {len(result.candidates)}"
    )
    # Each candidate carries evidence from the enclosing function.
    for candidate in result.candidates:
        assert candidate.evidence.function_name == "test_case"


def test_multi_observation_preserves_aligned_properties() -> None:
    """A method with .strings and .values assertions preserves both."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("multi_observation")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 2, "both assertions must produce candidates"
    attrs = {c.check_intents[0].target for c in result.candidates}
    assert "template.strings[0]" in attrs
    assert "template.values[0]" in attrs


def test_evidence_assertion_mismatch_is_rejected() -> None:
    """Test name says values, assertion says strings → reject."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("evidence_assertion_mismatch")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 0, "contradiction must produce zero candidates"
    assert any("docstring says" in r.reason.lower() for r in result.rejections)


def test_loop_subtest_is_rejected() -> None:
    """Loop/subtest-generated cases are rejected."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("loop_subtest")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 0
    assert any(
        "loop" in r.reason.lower() or "subtest" in r.reason.lower()
        for r in result.rejections
    )


def test_private_helper_is_rejected() -> None:
    """Private assertion helpers are rejected."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("private_helper")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 0
    assert any("helper" in r.reason.lower() for r in result.rejections)


def test_no_evidence_is_rejected() -> None:
    """No method/docstring/comment intent → reject."""
    from satyrn_model.authoring.extract import extract_candidates

    case = _fixture_by_id("no_evidence")
    result = extract_candidates(case["source"])
    assert len(result.candidates) == 0
    assert any("evidence" in r.reason.lower() for r in result.rejections)


def test_unsafe_import_is_rejected() -> None:
    """``__import__`` inside a t-string interpolation is rejected."""
    from satyrn_model.authoring.extract import find_template_literals

    case = _fixture_by_id("unsafe_import")
    with pytest.raises(ValueError, match="unsafe|import"):
        find_template_literals(case["source"])


def test_unsafe_file_process_is_rejected() -> None:
    """File/process primitives inside t-strings are rejected."""
    from satyrn_model.authoring.extract import find_template_literals

    case = _fixture_by_id("unsafe_file_process")
    with pytest.raises(ValueError, match="unsafe|open"):
        find_template_literals(case["source"])


def test_side_effect_is_rejected() -> None:
    """Mutable side effects inside t-strings are rejected."""
    from satyrn_model.authoring.extract import find_template_literals

    case = _fixture_by_id("side_effect")
    with pytest.raises(ValueError, match="unsafe|side.effect"):
        find_template_literals(case["source"])
