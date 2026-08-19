# Brief: seed-and-pattern corpus authoring

> **Historical and non-normative.** This dated brief does not define current
> behavior. See the [spike index](../../../README.md) and current
> [product design](../../../../../specs/design.md).

**Date:** 2026-07-31
**Status:** brainstormed with the project owner, not yet specced. This is the
input to SP5's own brainstorm → spec → plan cycle, which happens in its own
worktree.

> ⚠️ **This brief is ahead of the surrounding docs on `main`.** The overnight
> spike branch (`worktree-overnight-tstrings-spike`) carries corrections not yet
> merged here — most importantly that **tdom and all third-party sources are
> ruled out**. Read this brief's Constraints section as authoritative over
> anything on `main` that still recommends tdom.

## Why this exists

The approved spec sequenced **measure → harvest → synthesize**, with synthesis
(SP3) gated on harvest proving insufficient. Harvest has now proven insufficient
*structurally*, not merely measurably:

- **No third-party sources.** Training examples must teach the PEP 750 language
  feature and the `string.templatelib` stdlib API — not a library's API surface.
  Examples importing `tdom` would bind the model's notion of t-strings to one
  niche library. This ruled out what had been ranked the largest available
  corpus.
- **What remains is tiny.** CPython's `Lib/test/test_string/test_templatelib.py`
  is 193 lines / 13 test methods. PEP 750 adds a few dozen examples. The owner
  can supply a handful more from other projects. That is 1–2 orders of magnitude
  below the spec's "low thousands" target.

So synthesis is no longer a gap-filler. It is the primary source, and it needs
its own design rather than SP3's four planned rungs.

## The design, as brainstormed

**The human is the source, not the gate.** Review effort scales with output
volume; seeding effort scales with the diversity needed, and each seed
multiplies. Inverting the human's role is what makes this tractable.

1. **Seeds** — real t-string literals. Extracted from real code where possible
   (see "de-libraryization" below), hand-authored by the owner to fill gaps that
   extraction misses. Seeds carry realistic shape: nested interpolation,
   attribute holes, awkward whitespace, format specs. This is the thing
   generation is worst at inventing and the human is best at supplying.
2. **Patterns** — parameterized exercise kinds ("assert this template's
   `.strings`", "write a renderer producing X", "what is this interpolation's
   `format_spec`?"). An LLM proposes them; **the owner approves each pattern
   once**. Review is per-pattern (dozens) rather than per-example (hundreds).
3. **Cross-product, executed** — each approved pattern is applied
   deterministically across seeds, and **expected values are computed by
   actually executing the template**. Ground truth comes from the interpreter,
   never from a model.
4. **Oracle + gates** — every generated example still passes the existing
   verification path: hidden asserts in an isolated subprocess with timeout,
   the `ast.TemplateStr` feature check, the old-form canary (f-string /
   `.format()` / `%`), the self-verification gate, the on-target filter, and the
   anti-vacuity check.
5. **Human adjudicates only the uncertain middle** — verified-but-degenerate,
   near-duplicates, low-confidence transformations.

### De-libraryization

The t-string *literals* inside a third-party library's tests are pure stdlib
artifacts — `t"<div class={cls}>{content}</div>"` is 100% PEP 750; only the
surrounding `TemplateParser.parse(...)` / `TFragment(...)` assertions are
library-specific. So real-world-shaped literals can be **extracted as seeds and
rebuilt into stdlib-only exercises without importing anything third-party.**

This rescues the shape while discarding the API, and it directly counters the
degeneracy that sank the original corpus (roughly 15 of its 24 examples were
variants of `name = "World"; t"Hello {name}"`).

## Prior art

The method has published precedent — this is not a novel gamble:

- **[Template-Based Data Generation](https://arxiv.org/abs/2411.18104)** is
  substantially this design: an LLM generates parameterized meta-templates that
  synthesize a large stream of problem/solution pairs, with generation and
  verification integrated via reject-sampling **plus code execution**.
- **[Code Execution as Grounded Supervision](https://arxiv.org/html/2506.10343v1)**
  — program determinism is what makes the labels trustworthy.
- **[Grounding Code Generation with I/O Specifications](https://arxiv.org/html/2402.08073v2)**
  — deriving specs from execution states.
- **Self-Instruct** seeds with **100–200 hand-written examples** before
  generating variations. A useful calibration for the owner's seed budget —
  meaningfully more than the ~30 initially floated.

Tooling surveyed and *not* adopted, with reasons:
[Argilla](https://argilla.io) / [distilabel](https://github.com/argilla-io/distilabel),
[Bespoke Curator](https://github.com/bespokelabsai/curator), CuratorKIT, Easy
Dataset, Augmentoolkit. All treat the LLM as the source of ground truth with a
human or LLM judge filtering afterward. None derive expected values by
execution, which is precisely the property that makes a large auto-accept path
safe here. Their pipeline plumbing may still be worth borrowing later.

## Known risk to design against

**Generated examples are correlated.** 30 seeds × 20 patterns is not 600
independent examples; it is 30 templates viewed 20 ways. The model can overfit
to those specific templates while the corpus *looks* large. Consequences:

- **Seed diversity matters more than seed count, and more than pattern count.**
  Ten wildly different seeds beat fifty near-identical ones.
- Favour patterns that **compose or transform** seeds (concatenate two, nest one
  inside another's format spec, convert an f-string to an equivalent template)
  over patterns that merely introspect one — composed outputs are not a function
  of a single seed, which breaks the correlation.
- The scale sweep must measure *effective* diversity, not row count.

## Constraints inherited (non-negotiable)

- **Stdlib-only.** No example may import a third-party package.
- Expected values come from executing real code, never from a model.
- Every example passes the full oracle contract before entering the corpus.
- Provenance on every row: source, exact ref, verifying interpreter version.
- Benchmark disjointness enforced by the contamination gate — note the gate
  currently compares prompt text only and has a known code-similarity blind spot
  that must be closed before this corpus is used for training.

## Open questions for SP5's brainstorm

1. Where does the tool live — this repo, or a standalone reusable one? (The
   method generalizes to any new-syntax-teaching corpus, including the 3.15 work
   in SP4.)
2. What is the seed budget in practice, and how much extraction vs. hand
   authoring? Self-Instruct's 100–200 is the reference point.
3. What is the review UI — CLI, TUI, or web? What makes pattern approval fast?
4. How is effective diversity measured, so the correlation risk is observable
   rather than theoretical?
5. Does SP3 (targeted synthesis) survive as a distinct sub-project, or is it
   absorbed here? Its R3 (contrastive old→new pairs) and R4 (scale sweep) look
   like SP5 rungs now.
