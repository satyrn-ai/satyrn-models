"""SP5 Task 5: collection import and exact-dedup gates.

Focused command: ``uv run python -m pytest tests/authoring/test_static_gates.py -q``.
"""

from satyrn_model.authoring.models import (
    Introspect,
    LocalCheckIntent,
    PolicyIntent,
    SourceEvidence,
    SourceExerciseCandidate,
    SourceOrigin,
    TaskIntent,
)


def _make_row(
    row_id: str,
    reference: str = 'name = "World"\ntemplate = t"Hello {name}"\n',
) -> SourceExerciseCandidate:
    """Build a fixture candidate row with minimal fields."""
    return SourceExerciseCandidate(
        id=row_id,
        origin=SourceOrigin(
            source_id="cpython-v3.14.5",
            path="Lib/test/test_templatelib.py",
            line_start=1,
            line_end=1,
            license="PSF-2.0",
        ),
        evidence=SourceEvidence(function_name="test_x"),
        intent=TaskIntent(
            id=row_id,
            description="test",
            properties=(Introspect(target=".strings", index=0, field="strings"),),
            policy_intent=PolicyIntent(
                requires_template=True,
                templatelib_apis_used=frozenset({"strings"}),
            ),
        ),
        check_intents=(LocalCheckIntent(kind="equals", target="template.strings[0]"),),
    )


# ---------------------------------------------------------------------------
# Import gates
# ---------------------------------------------------------------------------


def test_dynamic_import_rejected() -> None:
    """Code with ``__import__`` or dynamic import is rejected."""
    from satyrn_model.authoring.static_gates import check_imports

    assert check_imports("__import__('os')") is not None  # rejected
    assert check_imports("import os") is None  # allowed (stdlib)
    assert check_imports("from string import Template") is None


def test_third_party_surface_rejected() -> None:
    """Third-party API names surviving de-libraryization are rejected."""
    from satyrn_model.authoring.static_gates import check_third_party_names

    # Reference to a library-specific name after its import was stripped.
    bad = 'parser = TemplateParser()\nresult = parser.parse(t"<div>{x}</div>")\n'
    assert check_third_party_names(bad) is not None  # TemplateParser rejected

    # Pure stdlib reference — allowed.
    good = 'from string.templatelib import Template\nresult = Template("Hello")\n'
    assert check_third_party_names(good) is None


# ---------------------------------------------------------------------------
# Dedup gates
# ---------------------------------------------------------------------------


def test_exact_repeat_rejected() -> None:
    """Two byte-identical rows: the duplicate is rejected."""
    from satyrn_model.authoring.static_gates import deduplicate_rows

    row_a = _make_row("a")
    row_b = _make_row("b")  # same content, different id

    kept, dropped = deduplicate_rows([row_a, row_b])
    assert len(kept) == 1
    assert len(dropped) == 1
    assert dropped[0].id == "b"


def test_shared_skeleton_is_not_duplicate() -> None:
    """Rows sharing a structural skeleton are both retained (metric only)."""
    from satyrn_model.authoring.static_gates import deduplicate_rows

    row_a = _make_row("a")
    row_b = SourceExerciseCandidate(
        id="b",
        origin=row_a.origin,
        evidence=row_a.evidence,
        intent=TaskIntent(
            id="b",
            description="same skeleton, different description",
            properties=row_a.intent.properties,
            policy_intent=row_a.intent.policy_intent,
        ),
        check_intents=row_a.check_intents,
    )

    kept, dropped = deduplicate_rows([row_a, row_b])
    assert len(kept) == 2, "same-skeleton rows must both be retained"
    assert len(dropped) == 0
