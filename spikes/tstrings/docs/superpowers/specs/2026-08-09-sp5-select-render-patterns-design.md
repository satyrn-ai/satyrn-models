# SP5 select_result/render_subskill patterns: closing the author-role gap

Addresses `SP5_SCALE_BRIEF.md` Priority 4 ("new patterns only after 1-3"),
now that all six domain floors are met (84 seeds, 57 patterns). Scoped to
the two properties `composition.toml` actually weights most heavily.

## Why these two properties, checked against real generation output

Ran `generate_all` over the current full catalog and seed pool rather than
reasoning from the brief's old snapshot — 9,673 candidate rows:

| property | actual share | `composition.toml` target |
| --- | --- | --- |
| `introspect` | 28.7% | not a target at all (`composition.toml`'s own comment: "replaced by contrasted outcomes and explicit rendering subskills") |
| `select_result` | 23.4% | 43% |
| `render_subskill` | 18.2% | 45% |
| `render_template` | 10.4% | — |
| `join_static_parts` | 7.8% | 4% |
| `compose_templates` | 6.0% | 5% |
| `negative` | 5.2% | 2% |
| `construct` | 0.2% | 1% |

`select_result` and `render_subskill` are `composition.toml`'s two largest
targets (88% combined) and the two most under-supplied relative to that
weight, despite this session's seed growth. Traced why: every arity-1
property gets almost exactly the same ~252 rows per pattern
(`introspect` 2772/11≈252, `select_result` 2268/9≈252, `render_subskill`
1764/7≈252 — `generate_all` multiplies pattern × matching seeds
identically regardless of property). Candidate-pool share is driven almost
entirely by pattern *count* per property, not seed count — seeds already
did their job this session; patterns are the actual lever now.
`introspect` — the largest single chunk, and explicitly deprecated by the
composition profile — is out of scope; removing/deprecating existing
approved patterns is a different, more invasive decision than adding new
ones.

## The two gaps, traced through the real reference-generation code

Both properties have a `role="consumer"` / `role="author"` split — author
patterns ask the model to "define a typed template function," consumer
patterns ask for an inline computation. Checked `task_builder.py`'s
`_ref_author` (the function that builds author-role reference code)
directly:

**`select_result`: one missing pattern, zero code changes.** Consumer
covers all 5 outcomes (`template`, `strings`, `values`, `joined_static`,
`rendered`); author covers only 4 — `contrast-author-template` doesn't
exist. `_ref_author`'s `SelectTemplateResult` branch (`task_builder.py`
~216-242) *already* has a complete `outcome="template"` case (function
name `identity`, return type `Template`, body `return template`) — the
code path exists and is dead simply because no pattern in `catalog.py`'s
`contrast-author-*` comprehension includes `"template"` in its outcome
list. Adding the pattern is a one-line addition to that existing
comprehension, the same shape as the earlier construct-patterns fix.

**`render_subskill`: five missing patterns, real code needed.** Consumer
covers all 6 stages; author covers only `render_template`. `_ref_author`'s
`RenderSubskill` branch is:

```python
if isinstance(prop, RenderSubskill) and prop.stage == "render_template":
    return _ref_render(RenderTemplate(), seeds)
raise ValueError(f"unsupported authoring property {prop!r}")
```

Any other stage raises. This is a genuine gap, not a missing catalog
entry — `_ref_author` needs five new branches.

## The 6 new patterns

### `contrast-author-template` (select_result)

Added to the existing `contrast-author-*` comprehension in `catalog.py`,
`outcome="template"`, description `"define a typed template function
returning the template itself"`. No `task_builder.py` change — the
existing `identity` function path handles it.

### 5 new render_subskill author patterns

Each mirrors the "author" framing already established by
`render-subskill-author-template` — a typed function taking
`template: Template`, matching every other author function's signature in
the file (none of the existing author functions take a narrower parameter
type like `Interpolation` directly, so these don't either, even though
their consumer counterparts extract `interpolation =
template.interpolations[0]` partway through):

| stage | function | returns |
| --- | --- | --- |
| `iterate_parts` | `def iterate_parts(template: Template) -> tuple[str \| Interpolation, ...]: return tuple(template)` | the ordered parts |
| `classify_parts` | `def classify_parts(template: Template) -> tuple[str, ...]: return tuple("static" if isinstance(p, str) else "interpolation" for p in template)` | per-part classification |
| `convert_value` | `def convert_value(template: Template) -> object: interpolation = template.interpolations[0]; return convert(interpolation.value, interpolation.conversion)` | the converted first value |
| `format_value` | `def format_value(template: Template) -> str: interpolation = template.interpolations[0]; value = convert(...); return format(value, interpolation.format_spec)` | the converted+formatted first value |
| `render_interpolation` | `def render_interpolation(template: Template) -> str: interpolation = template.interpolations[0]; value = convert(...); return format(value, interpolation.format_spec)` | same body as `format_value`, framed as "render one interpolation" |

`render_interpolation`'s author body is identical to `format_value`'s —
that's real: the consumer-side `render_interpolation` stage already
defines a nested helper function internally
(`task_builder.py`'s `_ref_render_subskill`, stage `render_interpolation`)
that does the same convert-then-format work; the author framing just
asks for it as the top-level function instead of an inline one. Distinct
prompts, same underlying computation — matching how `render_template`'s
consumer and author patterns already share logic today.

Five new `catalog.py` entries,
`render-subskill-author-{iterate_parts,classify_parts,convert_value,
format_value,render_interpolation}`, `role="author"`,
`requires=("string.templatelib",)` (matching the existing consumer
`render-subskill-*` family), plus one new `elif isinstance(prop,
RenderSubskill)` branch in `_ref_author` dispatching on `prop.stage` to
the five function bodies above.

## What this brings

Every arity-1 pattern produces exactly (seed count × 3 prompt variants)
rows — confirmed exactly: 84 seeds × 3 = 252, matching all three measured
per-pattern averages precisely. So each new pattern adds ~252 rows, and
the total pool grows too as patterns are added, which matters for the
percentage math:

- `select_result`: 9 → 10 patterns, rows 2268 → 2520.
- `render_subskill`: 7 → 12 patterns, rows 1764 → 3024.
- New total: 9673 + 6×252 = 11185.
- `select_result` share: 23.4% → **22.5%** — it actually drops slightly,
  because `render_subskill` grows five times faster and inflates the
  shared denominator more than `select_result`'s own one-pattern gain.
- `render_subskill` share: 18.2% → **27.0%** — the real, meaningful move,
  closer to its 45% target though still under it.

Worth being precise about this rather than waving at "both move toward
target": adding one pattern to a property whose sibling property is adding
five doesn't grow that property's *relative* share, even though its
absolute row count does grow. If closing `select_result`'s gap toward 43%
mattered on its own timeline, it would need more than the one pattern this
batch adds — this batch's honest framing is "close the two authoring-code
gaps that exist today," not "hit a percentage."

## What this does not do

Does not touch `introspect` (deprecated but untouched — a separate
decision). Does not touch `composition.toml`/`sampling.toml` targets
themselves. Does not add new seeds — this is pure pattern work, the first
branch in this whole effort where seeds are genuinely not the constraint.
Does not attempt to close the full 43%/45% target gap in one pass; five
new render_subskill patterns roughly double that property's share but
don't fully close it — a reasonable next increment, not a claim of
completion.
