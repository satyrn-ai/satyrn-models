# SP5 seed sourcing: ~20 new seeds for regex, sql, html

Addresses `SP5_SCALE_BRIEF.md` Priority 1, scoped to three of its four gap
domains: bring regex, sql, and html to 12-15 distinct seeds (currently regex
3, sql 7, html 7, against text 17 and data 6). **Logging is deliberately
skipped in this pass** — see below. Everything else in the brief — patterns,
`construct`/`compose_templates` population, extraction breadth beyond this —
is explicitly lower-priority and gated on this landing first, and stays out
of scope here.

## Why this isn't a simple "extract more from CPython" job

Pinned CPython `v3.14.5` was checked directly, not assumed. Every file in the
pinned tag that touches `templatelib` was fetched and its literal
`ast.TemplateStr` nodes counted:

| file | t-string literals | domain |
| --- | --- | --- |
| `Lib/test/test_string/test_templatelib.py` | 20 (10 already mined) | text/data |
| `Lib/test/test_tstring.py` | 69 | text/data (grammar/syntax tests) |
| `Doc/library/string.templatelib.rst` | 23 | text/data |
| `Doc/whatsnew/3.14.rst` | 5 | text/data |
| `Lib/string/templatelib.py` | 1 | text |

One in-domain hit across all of it: `t'<img {attributes}>'`
(`Doc/whatsnew/3.14.rst:365`). CPython has ~108 unmined literals — a real
extraction gap worth closing eventually — but they are uniformly text/data.
Mining them deepens the skew this brief calls the top-priority problem; it
does not fix it. t-strings are ~8 months old: no stdlib module yet uses them
for SQL, HTML, logging, or regex, so **no amount of CPython mining reaches
Priority 1.**

## The one-time exception

Approved explicitly for this task: a small set of **third-party, stdlib-only,
permissively-licensed** sources may supply seeds for the gap domains in
scope (regex, sql, html).
This is not a reopening of the stdlib-only rule that `DATASET_METHODOLOGY.md`
established after the `tdom` incident (`CORPUS_MACHINERY.md`'s "Why not an
off-the-shelf synthetic-data tool" section) — it is a scoped, reviewed,
one-time addition of specific sources, each checked below against the same
failure mode: does this source teach the *language feature*, or does it teach
a *library's API surface*? Future third-party sources need the same review;
this exception does not create a standing policy of "third-party is fine now."

**Two candidates were checked and rejected before landing on the sources
below — worth recording so the rejection reasoning isn't lost:**

- `pgjones/sql-tstring` (161★, top search hit for "sql tstring"): its `t()`
  helper is a hand-rolled parser over *plain strings* with manual
  `{placeholder}` syntax — it does not use real PEP 750 `t"..."` literal
  syntax at all. Mining it would teach a library's parsing convention, not
  the language feature. Caught by reading `src/sql_tstring/t.py` directly
  rather than trusting a literal grep.
- `ilotoki0804/tstr`'s `test_logging.py` / `test_sqlite.py`: build templates
  via `generate_template("...")` from plain strings, not `t"..."` literal
  syntax. Same failure mode, same rejection.
- `psycopg` (`tests/test_tstring.py`, 78 real SQL literals, arguably *the*
  motivating library for t-strings in SQL): **not used.** Licensed
  LGPL-3.0, which is not in `sources.toml`'s `allowed_licenses`. Decision:
  leave it out rather than special-case the license policy — `t-sql` alone
  clears the SQL target several times over, so there's no forced trade here.

## New sources

All four verified as real `ast.TemplateStr` usage (parsed with Python 3.14's
own `ast` module, not grep) at the exact pinned commit, not local working
state. Local html projects were pinned to each repo's **last-pushed remote
SHA** (not local HEAD, which was ahead) so the pin is reproducible by anyone
re-running the pipeline without depending on this machine's disk.

| id | url | sha | license | distinct literals at pin | domain |
| --- | --- | --- | --- | --- | --- |
| `regex-template-2026` | `github.com/treyhunner/regex-template` | `f4ea6979113623760153eb6666a3aacdbe681fa3` | MIT | 33 | regex |
| `t-sql-2026` | `github.com/nhumrich/t-sql` | `01275e310804ff4409aa206afd4b2ddae5082ecd` | MIT | 214 | sql |
| `tdom-2026` | `github.com/ianjosephwilson/tdom` | `98264091b3154a36f4af2e205ac6c3b7c793fb20` | MIT | \* | html |
| `storyville-2026` | `github.com/pauleveritt/storyville` | `5fe71ce49dcf15674dbda063135f8dd4a3a9c954` | MIT | \* | html |
| `tainie-2026` | `github.com/pauleveritt/tainie` | `6f5d31997bb58b170c0c80d40ef464600cbfadf6` | Apache-2.0 | \* | html |
| `tdom-svcs-2026` | `github.com/pauleveritt/tdom-svcs` | `d2f6e3a1f7f0ff9295fe596ea29316e024c3befd` | MIT | \* | html |

\* Combined html total at these four pins: **506 distinct literals** after
the screen below (measured directly against `git archive` snapshots of the
pinned SHAs, not the local working trees).

Each gets a `[[source]]` record with `source_class = "third_party"` (new
value, distinct from `"cpython"`) so provenance stays legible in
`reports/source-inventory.json`, and `extraction_mode = "ast"`, matching
CPython's. `sources.py`'s `assert_source_pin` already generalizes to
non-CPython repos by design (its docstring says so explicitly) — no code
change needed there, only new TOML entries plus attribution text per repo.

## The screen: what gets mined vs. discarded

The `tdom` failure was specifically about a source teaching library API
instead of language syntax. Two of these sources are themselves rendering
libraries (`tdom`, and to a lesser extent `storyville`/`tainie`/`tdom-svcs`
which build on it), so the same risk applies to their literals, at smaller
scale than mining the *library's own code* would have been (we're mining
call sites — usage — not the library's internals).

Every candidate literal is screened for library-specific shapes before it
becomes a seed:

- **Drop component interpolation** — `<{Component}>`, `</{Component}>`. This
  is tdom's own component-substitution convention, not stdlib syntax.
  Measured: 59 of 699 raw distinct html literals (8.4%).
- **Drop bare attribute-spread** — `<tag {attrs}>` where the interpolation
  stands in for a whole attribute set. Also tdom-specific. Measured: 11 of
  699 (1.6%).
- **Keep everything else** — plain elements, attributes, text content, SVG,
  comments, void elements, `!r`/`!s`/`!a` conversions, format specs. These
  read the same under any renderer or none; ~90% of the raw pool survives.
- **`t-sql` and `regex-template` get the equivalent check**: neither's
  literals use a bespoke component/DSL marker inside the *literal itself* —
  interpolations are plain names/expressions (`{cols}`, `{user_id}`,
  `{pattern}`). Some carry library-specific format-spec codes as an
  artifact of their own renderer contract (e.g. `regex-template`'s
  `{digits:safe}`, `t-sql`'s param-style specs). The seed layer only
  records `literal` + `bindings` + `free_names` — it does not interpret
  `format_spec` semantics, so this is inert at the seed stage. **Flag for
  whoever authors patterns against these seeds later** (out of scope here,
  per the brief's own priority order): don't build a pattern that teaches
  the source library's format-spec meaning as if it were a stdlib
  convention.

After the screen, standard `seeds.py` dedup applies: identical `(literal,
bindings)` collapses to one `Seed` with multiple `occurrence_ids`, exactly as
CPython occurrences already do.

## Shape verification: confirming these are new shapes, not new volume

`SP5_SCALE_BRIEF.md` is explicit that row/literal *count* is the misleading
number — "structure is what the model learns from," and 5035 rows already
collapse onto 270 shapes. A sourcing plan that hits domain floor counts
without adding new structure would repeat that problem at smaller scale. So
before trusting the pool sizes above, each candidate pool was checked against
the *current* 44 seeds using a shape fingerprint at the seed level: each
interpolation's expression kind (name/attribute/call/subscript/binop/const),
conversion (`!r`/`!s`/`!a`/none), and format-spec presence (yes/no), with
identifiers and literal constants erased — the same
identifiers-and-constants-erased-skeleton principle `diversity.py` already
applies to generated task references, just computed one layer earlier, on
raw seed literals rather than post-pattern output.

| domain | shapes in current seeds | new distinct shapes in candidate pool | overlap |
| --- | --- | --- | --- |
| regex | 2 | 14 | 0 |
| sql | 5 | 47 | 3 |
| html | 3 | 78 | 2 |

Near-zero overlap in all three: the candidate pools land almost entirely on
structure the current 44 seeds don't have — multi-interpolation literals,
conversion + format-spec combinations, attribute/subscript/call expressions
instead of bare names, CTEs and UNIONs in sql, SVG and comments in html. This
is what makes the "8-10 new seeds per domain" selection in the next section
a real coverage move rather than duplication dressed as coverage (the exact
failure mode the brief warns about for the existing 5035-row pool).

One methodological caveat: this shape fingerprint is a *proxy* for the
project's actual diversity metric, which operates on generated `TaskRecord`
references after pattern application, not raw seed literals — patterns are
explicitly out of scope here (see "What this does not do" below). The
fingerprint above measures interpolation-structure diversity at the seed
level only; it doesn't (and can't yet) confirm downstream pattern-generated
shape diversity, since no patterns exist against these seeds yet.

## Selection down to seed counts

Raw pools (506 html, 214 sql, 33 regex) are all larger than the 12-15 target
floors, so selection — not scarcity — governs the final set. Within each
domain, prefer literals that:

1. Have at least one interpolation (a handful of static-only literals are
   fine for `join_static_parts`/negative coverage, but the pool shouldn't be
   dominated by them).
2. Vary binding type across the selected set — string, int, bool, float,
   expression, attribute access — so the domain doesn't collapse onto one
   binding shape.
3. Vary conversion/format-spec presence (`!r`, `:.2f`, bare) where the
   source has it, since `SP5_SCALE_BRIEF.md`'s `render_subskill` marginal
   depends on this variety existing at the seed level.
4. Skip near-duplicates by structural fingerprint (identifiers/constants
   erased) — same diversity-not-dedup treatment `CORPUS_MACHINERY.md` §9
   already applies to authored seeds, applied here at selection time so the
   pipeline's own dedup isn't doing double duty.

Target roughly 8-10 new seeds each for html, sql, regex, bringing them to
15-17, 15-17, and 11-13 respectively.

## Logging: skipped in this pass

Explicitly out of scope for this task, by decision, not oversight. Record
of why it would have been the hard case, so a future pass doesn't have to
re-derive it: even after the widened hunt, real logging usage is thin.
`davepeck/pep750-examples` (MIT, already vendored locally) has exactly 2
distinct literals — `t"Hello, {name}!"` and `t"${amount:0.2f}"` — both via
`logger.info(t"...")`. `NMRhub/tstring-logger` has no usage examples to
mine. `pR0Ps/tstringlogger` has the richest logging-domain shapes found —
e.g. `t"{hello} {w!r}: {pi=:.2f} {d['a']} {obj.b}"` — but is inadmissible:
`pyproject.toml` declares `license = "LGPL-3.0-only"` explicitly and the
repo has no `LICENSE` file either, the same license category as psycopg.
Logging stays at its current 4 seeds until a follow-on task takes it on,
most likely via hand-authoring under a rubric since mining doesn't reach it.

## What this does not do

No pattern authoring, no `composition.toml`/`sampling.toml` changes, no
`construct`/`compose_templates` population, no logging seeds — all
explicitly lower-priority or out of scope per this decision, left for a
follow-on task once these seeds land and are reviewed. No code changes to
`sources.py`/`seeds.py`/`extract.py` are anticipated; `assert_source_pin`
and the seed/occurrence dedup already generalize to non-CPython sources by
design.
