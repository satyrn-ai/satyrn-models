"""New select_result/render_subskill author-role patterns. See
docs/superpowers/specs/2026-08-09-sp5-select-render-patterns-design.md."""

from satyrn_model.authoring.generate import apply_pattern
from satyrn_model.authoring.models import Seed
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.task_builder import build_task, generated_intent

SEED = Seed(
    id="select-render-seed",
    literal='t"Hello, {name}"',
    free_names=("name",),
    bindings=(("name", "'World'"),),
    occurrence_ids=("occ-select-render",),
    kind="authored",
    domain="text",
)


def test_contrast_author_template_defines_an_identity_function() -> None:
    pattern = next(p for p in CATALOG if p.id == "contrast-author-template")
    assert pattern.role == "author"
    assert pattern.property_specs[0].kind == "select_result"
    assert pattern.property_specs[0].outcome == "template"

    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def identity(template: Template) -> Template:" in task.reference
    assert "return template" in task.reference
    assert "result = identity(template)" in task.reference


NEW_RENDER_SUBSKILL_AUTHOR_IDS = {
    "render-subskill-author-iterate_parts",
    "render-subskill-author-classify_parts",
    "render-subskill-author-convert_value",
    "render-subskill-author-format_value",
    "render-subskill-author-render_interpolation",
}


def test_five_new_render_subskill_author_patterns_are_in_the_catalog() -> None:
    ids = {p.id for p in CATALOG}
    missing = NEW_RENDER_SUBSKILL_AUTHOR_IDS - ids
    assert not missing, f"catalog is missing: {missing}"
    for pattern_id in NEW_RENDER_SUBSKILL_AUTHOR_IDS:
        pattern = next(p for p in CATALOG if p.id == pattern_id)
        assert pattern.role == "author"
        assert pattern.property_specs[0].kind == "render_subskill"


def test_author_iterate_parts_returns_ordered_parts() -> None:
    pattern = next(
        p for p in CATALOG if p.id == "render-subskill-author-iterate_parts"
    )
    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert (
        "def iterate_parts(\n    template: Template,\n) -> tuple[str | Interpolation, ...]:"
        in task.reference
    )
    assert "return tuple(template)" in task.reference
    assert "result = iterate_parts(template)" in task.reference


def test_author_classify_parts_labels_each_part() -> None:
    pattern = next(
        p for p in CATALOG if p.id == "render-subskill-author-classify_parts"
    )
    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def classify_parts(template: Template) -> tuple[str, ...]:" in task.reference
    assert '"static" if isinstance(part, str) else "interpolation"' in task.reference
    assert "result = classify_parts(template)" in task.reference


def test_author_convert_value_applies_conversion() -> None:
    pattern = next(
        p for p in CATALOG if p.id == "render-subskill-author-convert_value"
    )
    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def convert_value(template: Template) -> object:" in task.reference
    assert "interpolation = template.interpolations[0]" in task.reference
    assert "convert(interpolation.value, interpolation.conversion)" in task.reference
    assert "result = convert_value(template)" in task.reference


def test_author_format_value_converts_and_formats() -> None:
    pattern = next(
        p for p in CATALOG if p.id == "render-subskill-author-format_value"
    )
    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def format_value(template: Template) -> str:" in task.reference
    assert "format(value, interpolation.format_spec)" in task.reference
    assert "result = format_value(template)" in task.reference


def test_author_render_interpolation_converts_and_formats() -> None:
    pattern = next(
        p for p in CATALOG if p.id == "render-subskill-author-render_interpolation"
    )
    exercise = apply_pattern(pattern, (SEED,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def render_interpolation(template: Template) -> str:" in task.reference
    assert "format(value, interpolation.format_spec)" in task.reference
    assert "result = render_interpolation(template)" in task.reference


def test_construct_still_raises_for_genuinely_unsupported_properties() -> None:
    """_ref_author's final raise still guards real gaps -- this isn't a
    catch-all that got silently disabled by the new branches."""
    import pytest

    from satyrn_model.authoring.models import NegativeControl
    from satyrn_model.authoring.task_builder import _ref_author

    with pytest.raises(ValueError, match="unsupported authoring property"):
        _ref_author(NegativeControl(expected_solution_kind="fstring"), (SEED,))
