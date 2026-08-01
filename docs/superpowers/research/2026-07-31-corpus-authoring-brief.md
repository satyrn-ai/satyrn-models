# Brief: seed-and-pattern corpus authoring

**Date:** 2026-07-31
**Status:** **superseded 2026-07-31** by the
[seed-and-pattern corpus design](../specs/2026-07-31-seed-and-pattern-corpus-design.md).
Retained as the record of the thinking that produced it; the spec wins wherever
the two differ.

> ⚠️ **Corrected: third-party sources are ruled out as *example* sources, not as
> *seed* sources.** This brief originally said "tdom and all third-party sources
> are ruled out," which reads as a blanket ban and contradicts this document's
> own "De-libraryization" section below. The accurate rule: **no training
> example may import a third-party package**, but third-party *literals* are
> valid seed material, because a literal is a pure stdlib artifact even when the
> assertions around it are not. See spec §1.1.
>
> This matters in practice — the
> [awesome-t-strings](https://github.com/t-strings/awesome-t-strings) list
> yields ~12 repos spanning SQL, HTML, logging, regex, and structured data, and
> that domain diversity is the direct structural counter to the correlation risk
> described below.

## Why this exists

The approved spec sequenced **measure → harvest → synthesize**, with synthesis
(SP3) gated on harvest proving insufficient. Harvest has now proven insufficient
*structurally*, not merely measurably:

- **No third-party *imports* in examples.** Training examples must teach the PEP
  750 language feature and the `string.templatelib` stdlib API — not a library's
  API surface. Examples importing `tdom` would bind the model's notion of
  t-strings to one niche library. This ruled out what had been ranked the largest
  available corpus *as a source of examples* — its literals survive as seeds
  (see "De-libraryization").
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

- **Stdlib-only.** No example may import a third-party package. Third-party
  *literals* remain valid seed material.
- Expected values come from executing real code, never from a model.
- Every example passes the full oracle contract before entering the corpus.
- Provenance on every row: source, exact ref, verifying interpreter version.
- Benchmark disjointness enforced by the contamination gate. **Updated:** the
  code-similarity blind spot noted here is **closed** — the gate is dual-axis
  (prompt and normalized code, separate thresholds). Its 0.70 code threshold was
  derived from an 11×24 distribution and must be re-derived at scale, and
  intra-corpus dedup — never present — is now owned by spec §5.1.

## Open questions — all resolved at SP5's brainstorm (2026-07-31)

| # | Question | Resolution |
|---|---|---|
| 1 | Where does the tool live — this repo or a standalone reusable one? | **This repo**, with clean seams so SP4 can extract it later. The only genuine reuse seam is `extract.py`'s swappable node matcher; the claim that generation and verification are feature-agnostic was examined and found false (spec §2.4). |
| 2 | Seed budget, extraction vs. hand authoring? | **Extraction-first**, then a grammar-shape × task-type coverage analysis, then authoring only the demonstrably-missed shapes. Self-Instruct's 100–200 is the floor for the *combined* budget (spec R1, R4). |
| 3 | Review UI — CLI, TUI, or web? | **CLI** with rendered previews, decisions written to committed files. Seed review is facts-first (executed facts shown beside the literal) with a typed binding palette that auto-accepts, so human attention lands only on unusual expressions (spec §3.5, R3). |
| 4 | How is effective diversity measured? | **AST structural fingerprints** as the primary metric, prompt-text diversity as a co-equal second axis (B-HEADER at corpus scale), embedding clustering third and for reporting only. Thresholds derived from a measured pilot distribution, never guessed (spec §5). |
| 5 | Does SP3 survive as a distinct sub-project? | **No — closed.** Its R2/R3 are absorbed into the pattern registry (negative coverage is the `NegativeControl` `Property` variant), R4 is SP5 R8, and R1 survives in altered form as SP5 R4's coverage analysis. |

Two questions the brainstorm raised that this brief did not anticipate, both
recorded in the spec: the **verifiability-bias risk** shared between corpus and
benchmark (spec §8), which forced benchmark redesign into its own sub-project;
and **prompt↔solution alignment**, answered by making prompt, solution, and
hidden test projections of a single `Exercise` intent (spec §3.2).
