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
