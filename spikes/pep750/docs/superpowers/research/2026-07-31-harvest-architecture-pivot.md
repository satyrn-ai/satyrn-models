# Harvest architecture pivot: harvest call sites, not callees

**Date:** 2026-07-31
**Trigger:** deep architectural review (Fable), requested after two fix rounds
on `tdom_harvest.py` failed to converge.
**Status:** decided, superseding the harvest-unit reading of spec §3.5.

> **Superseded 2026-07-31 by the project owner's stdlib-only decision.** This
> note's harvest-unit correction (call sites, not callees) still stands. Its
> recommendation to instantiate that correction against `tdom`'s test files
> does not: `tdom` is ruled out as a corpus source entirely. See
> [`DATASET_METHODOLOGY.md`](../../../DATASET_METHODOLOGY.md) section 1. The
> body below is preserved as a dated record and is not rewritten.

## The finding that decided it

Three review rounds hardened a dependency-closure resolver without anyone
asking whether the harvested examples contained the feature being taught.
T-string literal counts across tdom, verified directly:

| File | t-strings |
|---|---|
| `processor_test.py` | **341** |
| `parser_test.py` | 62 |
| `svg_test.py` | 20 |
| `template_utils_test.py` | 13 |
| `processor.py` | 8 |
| **`escaping.py`** | **0** |
| **`callables.py`** | **0** |
| `format.py`, `parser.py`, `protocols.py`, `tnodes.py`, `htmlspec.py` | 0 |

`escaping.py` and `callables.py` are precisely the two modules harvested in
SP2 R2. **All four shipped Examples contain zero t-strings.**
`tdom-escaping-escape_html_comment` is a competent exercise in HTML comment
escaping and teaches nothing whatsoever about PEP 750.

So the resolver — a miniature Python module bundler, whose bug class survived
two fix rounds — was built to unlock a ceiling of ~21 examples, most
containing none of the target feature, while 400+ real, tested, idiomatic
t-string usages sat in the test files, which the harvester consumed only as
oracle material and never as training material.

## Second, independent argument against the bundler

Even a *correct* bundler produces bad training data here. When the prompt is a
signature plus docstring and the reference solution is that function body plus
inlined copies of `tnodes.py` classes and `protocols.py` protocols, the
completion is not inferable from the prompt — only memorizable. Closure-heavy
inlined examples are bad training pairs by construction. At its best, the
bundler manufactures memorization fodder.

## Root cause in our own spec

Spec §3.5 says "harvest converts real code into tasks; it does not paraphrase
it." That principle is sound and is retained. What forced the complexity was an
unstated narrower premise smuggled inside it: **that the harvest unit is a
library-internal function, and that the oracle temp dir must be import-free.**
Neither was ever required by the user or by the research. Both are changed here.

## The decision

**Harvest call sites, not callees.** The t-string skill being taught is
overwhelmingly caller-side — constructing templates and invoking processors —
and call sites are naturally standalone (a t-string literal plus one import).
Callee-side code is where dependency closures live.

1. **Primary source becomes tdom's test files** (`processor_test.py`,
   `parser_test.py`, ...). Unit of harvest = one test function. Prompt = its
   intent; reference solution = the real t-string-bearing body; hidden oracle =
   its real assertion. No closure to resolve. Still §3.5-compliant: real code
   converted to tasks, not paraphrase.
2. **Oracle gains optional package access.** `Example` may declare
   `requires_packages`; `verify_candidate` puts the pinned tdom checkout on the
   subprocess's `sys.path` for those examples. The isolation properties that
   actually matter (subprocess, timeout, temp cwd, unseen hidden test) are all
   preserved — "no imports resolvable" was an accident of the temp-dir design,
   never the load-bearing guarantee. It also makes provenance *easier*: pin and
   dirty-check the tree once, closing the gap where inlined sibling modules
   escaped the per-file dirty-tree guard.
3. **Function-level harvest narrows to trivial closures only** (same-file or
   stdlib). `_resolve_relative_import` and the cross-file `_Closure` path are
   deleted rather than fixed — making the wrong-symbol bug class
   *unrepresentable* instead of gated.
4. **CPython's `test_templatelib.py` is already call-site material** with
   assertions attached, so Task 11 benefits from the same framing for free.

## Mandatory invariant, regardless of source

**`harvest_module` must self-verify:** every Example's `reference_solution` is
run through the real `verify_candidate` against its own `hidden_test` before
emission; failures are dropped loudly with reasons, never emitted. This
converts any future harvester bug from silent corpus poisoning into visible
yield loss.

That three review rounds passed before anyone ran "does each Example's own
reference solution pass its own hidden test" is itself the finding — the check
was missing from the architecture, not merely from the test suite. A sweep of
all 11 tdom modules (previous rounds validated only the 2-module slice) found
**6 of 11 emit Examples that fail their own hidden test.**

The gate is necessary but **not sufficient**: the round-1 poisoning case
*passed its own test*. Wrong-but-passing survives any gate, which is exactly
why the architecture changes rather than merely acquiring a gate.

**Additional filter:** an Example whose prompt, reference solution, and hidden
test collectively contain no `TemplateStr` and no `Template`-consuming code
does not belong in a t-strings corpus, whatever its provenance. This would
have caught all four shipped Examples on day one.
