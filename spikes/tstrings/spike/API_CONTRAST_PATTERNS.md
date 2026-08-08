# Schema-extension request: API-contrast properties

**To:** the SP5 corpus owner (`sp5-corpus-brainstorm`)
**From:** the training worktree (`spike-tstrings-training`)
**Status:** blocked — needs a contract change, not a catalog addition

Repair step 4 has two halves. The capability contrasts — return the tuple, join
only the static strings, fully render — are **done**: they already exist as
approved `contrast-*` patterns, and `spike/build_curriculum.py` selects them on
a shared seed set so the same template appears under each instruction.

The second half, negative examples for the hallucinated APIs, cannot be built.
An earlier draft of this document proposed five new catalog entries. That was
wrong: **the property contract cannot express "this API does not exist"**, so
the work is a schema extension that invalidates existing approvals, not a
catalog addition. This is a request for that change.

## What the run showed

Failures were concentrated, not random: 17 import errors, 13 attribute errors,
12 type errors. The adapter invented:

| Hallucinated API | Correct form |
| --- | --- |
| `from string.templatelib import StaticPart` | no such type; static parts are plain `str` |
| `from string.templatelib import static_parts` | `template.strings` |
| `template.static_parts` | `template.strings` |
| `template.render()` | an explicit loop, or a typed render function |
| `template.specs` | `interpolation.format_spec` per interpolation |

All ten `.strings` answers routed to the correct *result* and still failed,
because they imported `StaticPart`. Intent was learned; the API surface was not.

This matters for how the curriculum repair should be read. The curriculum fix
addresses capabilities that had **zero** training rows. These API failures are
different in kind: they occurred on tasks whose sibling patterns
(`contrast-author-strings`, 44 rows) were trained *heavily*. More rows of the
same shape will not fix them.

## Why it cannot be expressed today

Checked against `src/satyrn_model/authoring/patterns/registry.py` and
`models.py`:

1. `PropertySpec.kind` is a closed `Literal` of eight members (registry.py:59):
   `introspect`, `render_template`, `join_static_parts`, `select_result`,
   `render_subskill`, `compose_templates`, `construct`, `negative`. None can
   carry "the following import is invalid".
2. The one negative path hard-codes its meaning: `NegativeControl` is
   constructed as `NegativeControl(expected_solution_kind="fstring")`
   (registry.py:179), and the dataclass (`models.py:108`) has no field for
   *which* wrong API is being contrasted. Every negative is an f-string
   negative.
3. `_validate_witnesses` maps expected witnesses from a closed dict, so a new
   rejection witness has nowhere to register.
4. `classify_operation` raises on any row with more than one property
   (registry.py:206-210). A pattern that pairs "the valid form" with "the
   invalid form" in one row is rejected by construction — which also kills the
   `api-contrast-valid-surface` positive control the earlier draft proposed.

## Requested change

1. **New property kind** `api_contrast`, with fields naming the invalid
   surface and its valid replacement — roughly
   `invalid_form: str`, `valid_form: str`, `failure: Literal["import",
   "attribute", "call"]`. This keeps one property per row, so
   `classify_operation` still holds; the contrast lives inside the property
   rather than across two properties.
2. **`classify_operation`** returns `api_contrast` for it.
3. **Witnesses** for the rejection cases, in the style of the existing
   `reject-template-str` and `reject-static-join`: `reject-static-part-import`,
   `reject-static-parts-attribute`, `reject-template-render`,
   `reject-template-specs`.
4. **`GENERATOR_VERSION` bump** (currently `0.2.0`, registry.py:47). This
   invalidates every `pattern_input_fingerprint`, so **all 51 existing
   approvals must be re-audited**. That is the main cost of this request and
   the reason it is worth batching with any other pending schema work.
5. **`composition.toml`** gains an `api_contrast` operation target and a
   property-profile entry.

## Then, five patterns

One per hallucinated API, each contrasting the invalid form with the valid one
on the same template, in both consumer and author roles — the adapter
hallucinated `StaticPart` in author tasks specifically:

- `api-contrast-static-part-import`
- `api-contrast-static-parts-attribute`
- `api-contrast-template-render`
- `api-contrast-format-spec-access`
- `api-contrast-convert-import` (the one surface it got right; a positive
  control to avoid teaching blanket import avoidance)

## Sequencing note

Nothing here blocks repair steps 5 and 6. `build_curriculum.py` fails closed on
unapproved patterns, so this cannot leak into training early. But an adapter
trained on the current curriculum should still be expected to produce
`ImportError` on `.strings` tasks even when it routes intent correctly — that
was 17 of the observed failures, and the largest single bucket. Any step-6
promotion gate run before this lands should treat API-surface failures as
expected-and-unaddressed rather than as evidence the curriculum repair failed.
