# SP5 Select/Render Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the author-role gap in `select_result` (1 pattern, 9→10)
and `render_subskill` (5 patterns, 7→12), per `SP5_SCALE_BRIEF.md`
Priority 4 and the approved design at
`docs/superpowers/specs/2026-08-09-sp5-select-render-patterns-design.md`.

**Architecture:** Task 1 is a pure catalog-data addition (the code path
already exists in `task_builder.py`'s `_ref_author`). Task 2 adds real new
reference-generation code — five new branches in `_ref_author` for
`RenderSubskill` stages that currently raise `ValueError` — plus five
matching catalog entries.

**Tech Stack:** Python 3.14, the existing `satyrn_model.authoring`
package, pytest.

## Global Constraints

- Run every command from `spikes/tstrings/`.
- Every new author-role function must take `template: Template` as its
  parameter (not a narrower type like `Interpolation`) — matching every
  other author function already in `_ref_author`, even where the
  underlying computation only needs the first interpolation.
- All 5 new `render_subskill` reference bodies were independently executed
  against a real `Template` before being written into this plan — verified
  correct output, not just "should work."
- Do not touch `introspect` patterns, `composition.toml`, or
  `sampling.toml` — out of scope per the design doc.

---

## Task 1: Add `contrast-author-template`

**Files:**
- Modify: `src/satyrn_model/authoring/patterns/catalog.py`
- Test: `tests/authoring/test_select_render_patterns.py` (new file, this
  task adds the `select_result` test; Task 2 extends the same file)

**Interfaces:**
- Consumes: `satyrn_model.authoring.generate.apply_pattern`,
  `satyrn_model.authoring.task_builder.{build_task, generated_intent}`,
  `satyrn_model.authoring.patterns.catalog.CATALOG`,
  `satyrn_model.authoring.models.Seed` — all existing, unchanged.
- Produces: `CATALOG` gains one pattern, id `contrast-author-template`.

- [ ] **Step 1: Write the failing test**

Create `tests/authoring/test_select_render_patterns.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_select_render_patterns.py::test_contrast_author_template_defines_an_identity_function -v`
Expected: FAIL — `StopIteration` from the `next(...)` call, since
`contrast-author-template` doesn't exist in `CATALOG` yet.

- [ ] **Step 3: Add the pattern**

In `src/satyrn_model/authoring/patterns/catalog.py`, find the
`contrast-author-*` comprehension (search for
`id=f"contrast-author-{outcome}"`) and add `"template"` as the first entry
in its `for outcome, description in (...)` tuple:

```python
        for outcome, description in (
            (
                "template",
                "define a typed template function returning the template itself",
            ),
            ("strings", "define a typed template function returning template.strings"),
            ("values", "define a typed template function returning template.values"),
            (
                "joined_static",
                "define a typed template function joining only template.strings",
            ),
            (
                "rendered",
                "define a typed template function that fully renders the template",
            ),
        )
```

(Only the new `"template"` tuple is new — the other four already exist,
keep them exactly as they are, just add the new one before them.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_select_render_patterns.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/satyrn_model/authoring/patterns/catalog.py tests/authoring/test_select_render_patterns.py
git commit -m "Add contrast-author-template pattern"
```

---

## Task 2: Add the 5 render_subskill author patterns

**Files:**
- Modify: `src/satyrn_model/authoring/task_builder.py`
- Modify: `src/satyrn_model/authoring/patterns/catalog.py`
- Test: `tests/authoring/test_select_render_patterns.py` (extend the file
  from Task 1)

**Interfaces:**
- Consumes: same as Task 1, plus `satyrn_model.authoring.models.
  RenderSubskill` (existing).
- Produces: `_ref_author` in `task_builder.py` handles all 6
  `RenderSubskill` stages (was 1 of 6); `CATALOG` gains 5 patterns.

- [ ] **Step 1: Write the failing tests**

Append to `tests/authoring/test_select_render_patterns.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/authoring/test_select_render_patterns.py -v`
Expected: the 5 new-pattern tests FAIL (patterns don't exist yet); the
final `test_construct_still_raises_for_genuinely_unsupported_properties`
test PASSES already (it exercises existing behavior, not new — that's
fine, it's a guard for later, not something this step changes).

- [ ] **Step 3: Add the 5 new `_ref_author` branches**

In `src/satyrn_model/authoring/task_builder.py`, find this line (near the
end of `_ref_author`):

```python
    if isinstance(prop, RenderSubskill) and prop.stage == "render_template":
        return _ref_render(RenderTemplate(), seeds)
    raise ValueError(f"unsupported authoring property {prop!r}")
```

Replace it with:

```python
    if isinstance(prop, RenderSubskill) and prop.stage == "render_template":
        return _ref_render(RenderTemplate(), seeds)
    if isinstance(prop, RenderSubskill) and prop.stage == "iterate_parts":
        return (
            "from string.templatelib import Interpolation, Template\n\n"
            "def iterate_parts(\n"
            "    template: Template,\n"
            ") -> tuple[str | Interpolation, ...]:\n"
            "    return tuple(template)\n\n"
            f"{preamble}\nresult = iterate_parts(template)\n"
        )
    if isinstance(prop, RenderSubskill) and prop.stage == "classify_parts":
        return (
            "from string.templatelib import Template\n\n"
            "def classify_parts(template: Template) -> tuple[str, ...]:\n"
            "    return tuple(\n"
            '        "static" if isinstance(part, str) else "interpolation"\n'
            "        for part in template\n"
            "    )\n\n"
            f"{preamble}\nresult = classify_parts(template)\n"
        )
    if isinstance(prop, RenderSubskill) and prop.stage == "convert_value":
        return (
            "from string.templatelib import Template, convert\n\n"
            "def convert_value(template: Template) -> object:\n"
            "    interpolation = template.interpolations[0]\n"
            "    return convert(interpolation.value, interpolation.conversion)\n\n"
            f"{preamble}\nresult = convert_value(template)\n"
        )
    if isinstance(prop, RenderSubskill) and prop.stage == "format_value":
        return (
            "from string.templatelib import Template, convert\n\n"
            "def format_value(template: Template) -> str:\n"
            "    interpolation = template.interpolations[0]\n"
            "    value = convert(interpolation.value, interpolation.conversion)\n"
            "    return format(value, interpolation.format_spec)\n\n"
            f"{preamble}\nresult = format_value(template)\n"
        )
    if isinstance(prop, RenderSubskill) and prop.stage == "render_interpolation":
        return (
            "from string.templatelib import Template, convert\n\n"
            "def render_interpolation(template: Template) -> str:\n"
            "    interpolation = template.interpolations[0]\n"
            "    value = convert(interpolation.value, interpolation.conversion)\n"
            "    return format(value, interpolation.format_spec)\n\n"
            f"{preamble}\nresult = render_interpolation(template)\n"
        )
    raise ValueError(f"unsupported authoring property {prop!r}")
```

`preamble` is already in scope — it's assigned once near the top of
`_ref_author` (`preamble = _template_lines(seeds[0]) if seeds else
_fallback_template()`) and every branch in the function already reuses it
the same way; do not reassign or duplicate it.

- [ ] **Step 4: Add the 5 new catalog entries**

In `src/satyrn_model/authoring/patterns/catalog.py`, find the single
`render-subskill-author-template` pattern (search for `id="render-subskill-author-template"`)
and add 5 new patterns immediately after it (before the comprehension's
closing — this is a standalone tuple entry, not part of a comprehension,
so add 5 more standalone `_p(...)` entries in the same style):

```python
    _p(
        id="render-subskill-author-iterate_parts",
        description="define a typed template function returning the ordered parts",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="iterate_parts"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
    _p(
        id="render-subskill-author-classify_parts",
        description="define a typed template function classifying each part",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="classify_parts"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
    _p(
        id="render-subskill-author-convert_value",
        description="define a typed template function applying the first interpolation's conversion",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="convert_value"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
    _p(
        id="render-subskill-author-format_value",
        description="define a typed template function converting and formatting the first interpolation",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="format_value"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
    _p(
        id="render-subskill-author-render_interpolation",
        description="define a typed template function that renders one interpolation",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="render_interpolation"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/authoring/test_select_render_patterns.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 6: Run the full authoring test suite**

Run: `uv run python -m pytest tests/authoring/ -v`
Expected: PASS, all tests, no failures. In particular confirm
`test_entire_catalog_validates` in `tests/authoring/test_patterns.py`
still passes for all 6 new patterns (it iterates the whole `CATALOG` and
checks every pattern has the 3 standard prompt-variant ids — since these
are built via the same `_p()` helper as everything else, this should pass
without extra work, but confirm rather than assume).

- [ ] **Step 7: Commit**

```bash
git add src/satyrn_model/authoring/task_builder.py src/satyrn_model/authoring/patterns/catalog.py tests/authoring/test_select_render_patterns.py
git commit -m "Add 5 render_subskill author-role patterns"
```

---

## What this plan does not do

Matches the design doc: no `introspect` changes, no `composition.toml`/
`sampling.toml` changes, no new seeds. Does not claim to hit `select_result`'s
43% or `render_subskill`'s 45% composition target — the design doc's own
math shows `select_result`'s share barely moves (and technically drops
slightly relative to the new, larger total) while `render_subskill`'s
moves meaningfully closer (18.2%→27.0%) but doesn't reach 45%. This is a
deliberate increment, not a claim of completion.
