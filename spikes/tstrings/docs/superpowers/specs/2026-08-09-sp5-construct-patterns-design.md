# SP5 construct patterns: closing combinatorial gaps in a capped property

Addresses `SP5_SCALE_BRIEF.md` Priority 3, scoped to `construct` only —
`compose_templates` (6.0% of the candidate pool, already above its own 5%
`composition.toml` target) is left alone; see "Why `compose_templates` is
out of scope" below.

## The mechanism, traced through the real code

`SP5_SCALE_BRIEF.md` reports `construct` at "0.2% (10 rows)" of the 5035-row
candidate pool and calls that unteachable. Checked directly against
`generate.py:96-117` rather than assumed: `Construct` has arity 0 (it
doesn't consume a seed — `pattern_arity()` in `registry.py` returns `0` for
any `PropertySpec(kind="construct")`), and `generate_all`'s handling of
zero-arity patterns is:

```python
if n == 0:
    rows.append(apply_pattern(pattern, (), prompt_family=variants[0].id))
    continue
```

One row, per pattern, always — no loop over seeds. (Every pattern actually
declares 3 prompt variants via the shared `_p()` helper; the arity-0 branch
just never uses more than `variants[0]`, which is the real reason variant
count doesn't matter here.) Counted the catalog directly: 10 `construct`-
kind patterns are approved (`patterns/approvals.jsonl` confirms all 10),
which matches the brief's "10 rows" exactly. **This means no amount of
seed-sourcing —
which is what the two prior branches on this integration branch already
did — can move this number.** The only lever is patterns themselves, which
is why this is scoped as a small carve-out from Priority 4's general
"new patterns only after 1-3" deferral: for this one property, patterns
*are* what "populate" means.

## What each pattern actually builds

Traced `task_builder.py:_ref_construct` (lines 333-349) for the
`operation="Interpolation"` family (7 of the 10 existing patterns; the
other 3 cover `operation="convert"`, which only varies by `conversion` and
is already exhaustively covered — `r`/`s`/`a`, 3 values, 3 patterns, no
gap):

```python
return (
    "from string.templatelib import Interpolation\n"
    "result = Interpolation(\n"
    f"    \"World\", {prop.expression!r}, {prop.conversion!r}, "
    f"{prop.format_spec!r}\n"
    ")\n"
)
```

The constructed value is always the hardcoded string `"World"`;
`expression` is purely descriptive text embedded as a repr'd string
literal (never evaluated, never checked against a real expression) — it
represents what the *source* interpolation's expression text would have
been (e.g. `"user.name"` for an original `{user.name}`). Nothing in this
reference calls `format()` on the constructed object, so — unlike the
`RenderSubskill`/seed-mining cases where an invalid `format_spec` breaks
the pipeline's own render step — an invalid spec here wouldn't be
mechanically caught. Still worth using only real, valid Python format specs
for correctness; just noting the risk profile differs from the recent
seed-sourcing branches.

## The gap

Existing 7 `operation="Interpolation"` patterns, by `(expression,
conversion, format_spec)`:

| pattern | expression | conversion | format_spec |
| --- | --- | --- | --- |
| construct-interpolation-basic | `value` | none | `` |
| construct-interpolation-r | `value` | `r` | `` |
| construct-interpolation-s | `value` | `s` | `` |
| construct-interpolation-a | `value` | `a` | `` |
| construct-interpolation-format | `value` | none | `>8` |
| construct-interpolation-expression | `user.name` | none | `` |
| construct-interpolation-conversion-format | `value` | `r` | `>8` |

`expression` only takes two values across all 7 patterns, and the
non-`value` one (`user.name`, an attribute access) is never combined with
any conversion or format spec. `s`+format and `a`+format are both unfilled
even though `r`+format exists. And no pattern uses a subscript or call
expression shape at all — the same expression-kind vocabulary
(name/attribute/subscript/call) this project already used to judge seed
shape diversity in the prior two branches.

## The six new patterns

Each is one more tuple in the *existing* generator comprehension at
`catalog.py:348-415` (the `construct-interpolation-*` family is already
built from a list of `(pattern_id, description, conversion, expression,
format_spec)` tuples) — this is a small, mechanical addition to established
machinery, not new pattern-authoring infrastructure.

| id | description | conversion | expression | format_spec |
| --- | --- | --- | --- | --- |
| `construct-interpolation-subscript` | construct an Interpolation preserving a subscript source expression | none | `items[0]` | `` |
| `construct-interpolation-call` | construct an Interpolation preserving a call source expression | none | `get_name()` | `` |
| `construct-interpolation-expression-r` | construct an Interpolation with an attribute expression and !r conversion metadata | `r` | `user.name` | `` |
| `construct-interpolation-expression-format` | construct an Interpolation with an attribute expression and a format spec | none | `user.name` | `>10` |
| `construct-interpolation-s-format` | construct an Interpolation with !s conversion and format metadata | `s` | `value` | `>8` |
| `construct-interpolation-a-format` | construct an Interpolation with !a conversion and format metadata | `a` | `value` | `>8` |

All six format specs (`>10`, `>8` ×2) are plain alignment specs, valid for
any string — re-verified `format("World", ">10")` and `format("World",
">8")` both succeed, matching the existing `conversion-format` pattern's
already-proven `>8`.

This brings `construct` from 10 rows to 16 — a genuine 60% increase
in real combinatorial coverage, not padding (zero overlap with the existing
7: two new expression shapes, plus the s/a+format and attribute+conversion/
format combinations that were missing).

## What this does not close

Being upfront about scale, since it matters for expectations: `construct`'s
1-row-per-pattern structure means reaching `composition.toml`'s own 1%
target — let alone "a few percent" — as the candidate pool keeps growing
from other properties (which scale with seed count) would eventually
require dozens of hand-authored patterns, not six. This batch is a
deliberate down payment on the clearest unfilled combinations, not a claim
that it reaches the brief's percentage target. Closing the rest is either
more patterns later, or a `generate_all` code change to multiply zero-arity
patterns some other way (e.g. against multiple prompt variants) — neither
is in scope here.

## Why `compose_templates` is out of scope for this brainstorm

Already at 6.0% of the candidate pool per the brief's own numbers, above
its 5% `composition.toml` target, and (unlike `construct`) it scales with
seed supply — the prior two branches' seed additions plausibly already
improved it further as a side effect, the same way they closed most of
Priority 2. No evidence surfaced that it needs new patterns right now; a
future brainstorm can re-check the actual current candidate-pool
distribution if it's ever in question again.
