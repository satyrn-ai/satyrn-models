"""References rendered from SP5 intents match their declared semantics."""

from satyrn_model.authoring.generate import apply_pattern
from satyrn_model.authoring.models import Seed
from satyrn_model.authoring.patterns.catalog import CATALOG
from satyrn_model.authoring.patterns.registry import (
    Pattern,
    PromptVariant,
    PropertySpec,
    validate_pattern,
)
from satyrn_model.authoring.task_builder import build_task, generated_intent


def test_render_pattern_emits_typed_full_renderer() -> None:
    pattern = next(item for item in CATALOG if item.id == "render-template")
    seed = Seed(
        id="render-seed",
        literal='t"{value!r:>8}"',
        free_names=("value",),
        bindings=(("value", '"hi"'),),
        occurrence_ids=("occ-render",),
        kind="authored",
    )
    exercise = apply_pattern(pattern, (seed,))
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "def render_template(template: Template) -> str:" in task.reference
    assert "convert(part.value, part.conversion)" in task.reference
    assert "format(value, part.format_spec)" in task.reference
    assert "''.join(template.strings)" not in task.reference


def test_interpolation_constructor_uses_expression_and_format_spec_fields() -> None:
    pattern = Pattern(
        id="construct-interpolation",
        description="construct an Interpolation directly",
        property_specs=(PropertySpec(kind="construct", operation="Interpolation"),),
        labels=frozenset({"construct"}),
        witnesses=("construct-interpolation",),
    )
    validate_pattern(pattern)
    exercise = apply_pattern(pattern, ())

    task = build_task(generated_intent(exercise, pattern), seeds=())

    assert '"World", \'name\', None, \'\'' in task.reference


def test_generated_task_uses_the_selected_reviewed_prompt_family() -> None:
    pattern = Pattern(
        id="prompt-family",
        description="inspect template strings",
        prompt_variants=(
            PromptVariant(id="concise", text="inspect template strings"),
            PromptVariant(
                id="program",
                text="write a Python program that returns template strings",
            ),
        ),
        property_specs=(
            PropertySpec(
                kind="introspect", target=".strings", index=0, field="strings"
            ),
        ),
        labels=frozenset({"introspect"}),
        witnesses=("introspect-strings",),
    )
    seed = Seed(
        id="prompt-seed",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=("occ-prompt",),
        kind="authored",
    )

    exercise = apply_pattern(pattern, (seed,), prompt_family="program")
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert task.prompt == "write a Python program that returns template strings"


def test_catalog_prompt_family_includes_derivable_bindings_and_literal() -> None:
    pattern = next(item for item in CATALOG if item.id == "intro-values")
    seed = Seed(
        id="context-seed",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=("occ-context",),
        kind="authored",
    )

    exercise = apply_pattern(pattern, (seed,), prompt_family="python-program")
    task = build_task(generated_intent(exercise, pattern), seeds=exercise.seeds)

    assert "Write a Python 3.14 program" in task.prompt
    assert 'name = "World"' in task.prompt
    assert '`t"Hello {name}"`' in task.prompt
    assert "module-level variable `result`" in task.prompt


def test_direct_introspection_uses_explicit_attribute_access() -> None:
    pattern = next(item for item in CATALOG if item.id == "intro-strings")
    seed = Seed(
        id="explicit-attribute",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=("occ-explicit",),
        kind="authored",
    )

    task = build_task(
        generated_intent(apply_pattern(pattern, (seed,)), pattern), (seed,)
    )

    assert "result = template.strings" in task.reference
    assert "getattr(" not in task.reference


def test_same_template_contrast_emits_distinct_requested_results() -> None:
    seed = Seed(
        id="contrast-seed",
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=(("name", '"World"'),),
        occurrence_ids=("occ-contrast",),
        kind="authored",
    )
    references = {}
    for outcome in ("template", "strings", "values", "joined_static", "rendered"):
        pattern = next(item for item in CATALOG if item.id == f"contrast-{outcome}")
        exercise = apply_pattern(pattern, (seed,))
        references[outcome] = build_task(
            generated_intent(exercise, pattern), exercise.seeds
        ).reference

    assert "result = template\n" in references["template"]
    assert "result = template.strings" in references["strings"]
    assert "result = template.values" in references["values"]
    assert 'result = "".join(template.strings)' in references["joined_static"]
    assert "result = render_template(template)" in references["rendered"]


def test_render_subskill_is_decomposed_before_full_renderer() -> None:
    pattern = next(
        item for item in CATALOG if item.id == "render-subskill-render_interpolation"
    )
    seed = Seed(
        id="subskill-seed",
        literal='t"{value!r:>8}"',
        free_names=("value",),
        bindings=(("value", '"hi"'),),
        occurrence_ids=("occ-subskill",),
        kind="authored",
    )
    exercise = apply_pattern(pattern, (seed,))

    task = build_task(generated_intent(exercise, pattern), exercise.seeds)

    assert (
        "def render_interpolation(interpolation: Interpolation) -> str:"
        in task.reference
    )
    assert "convert(interpolation.value, interpolation.conversion)" in task.reference
    assert "format(value, interpolation.format_spec)" in task.reference
