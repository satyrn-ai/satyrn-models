# How the corpus-building machinery works

For anyone extending the corpus (starting with `SP5_SCALE_BRIEF.md`'s ~30
seeds) who needs the concepts, not just the file list. `src/satyrn_model/
authoring/` is ~4,300 lines across `authoring/*.py` and `authoring/patterns/`;
this is the small map, not a restatement of the code.

## Why not an off-the-shelf synthetic-data tool

**No LLM call exists anywhere in this pipeline** — that's a design decision
stated directly in `patterns/catalog.py`'s docstring, not an oversight.
`DATASET_METHODOLOGY.md` considered distilabel and Bespoke Curator and put
neither in its top three priorities. The reason isn't "off-the-shelf tools
are bad" — it's that the thing being taught is exactly the thing an LLM gets
wrong. `MODEL_NOTES.md` documents the base model confabulating a specific,
plausible-looking wrong PEP 750 API (a rejected "tagged template" draft with
`.tag`/`.parts`). Asking an LLM to *generate* the training examples risks
baking that same wrong API into the ground truth — contaminating the cure
with the disease it's meant to fix.

So the pipeline sources content two other ways instead: real, executable code
mined from CPython's own stdlib and test suite (ground truth that exists
independent of any model's opinion), and small hand-authored seeds, reviewed
by a person. Every candidate — regardless of source — is verified by actually
executing it and checking its behavior against a reference, not by an LLM's
self-assessment or a generic quality filter. The composition machinery below
(exact marginals, mandatory strata, negative controls) exists for the same
reason: earlier informal sampling let one property dominate and produced data
that didn't generalize (see `pep750`'s `DATASET_METHODOLOGY.md`, "Data design
principles"). None of this is generic corpus-building — it's a response to
specific, previously-measured failure modes.

## The pipeline, in order

1. **Occurrence → Seed** (`models.py`, `seeds.py`). An `Occurrence` is one
   location in one source (a file, a line range, a license). Many occurrences
   of identical content collapse into one `Seed` — dedup by content, not by
   location.
2. **Sourcing** (`sources.py`, `sources.toml`). A `Seed` may only come from a
   `[[source]]` pinned by an exact commit SHA, an allow-listed SPDX license,
   and attribution. Currently one source: CPython, tag `v3.14.5`. This rule —
   stdlib-only, exact version pins — exists because an earlier revision spent
   most of a build cycle mining a third-party library (`tdom`) before
   realizing it taught the library's API, not the language feature (see
   `pep750/DATASET_METHODOLOGY.md` §"Ground truth worth mining").
3. **Extraction** (`extract.py`). Finds t-string literals in a source file via
   AST parsing only — it never imports the source module, so a candidate
   can't execute arbitrary code from a third-party source during extraction.
4. **Patterns** (`patterns/catalog.py`, `patterns/registry.py`). A `Pattern`
   is a reviewed, hand-authored code template — not generated — that gets
   applied to a `Seed` to produce a candidate task. Its composition labels
   (which `property`/`operation`/`domain` it satisfies) are derived
   mechanically by a classifier, not self-declared, so a pattern can't claim
   coverage it doesn't have. `patterns/approvals.jsonl` is the audit ledger:
   a fingerprint over every declared input (helpers, templates, renderer
   deps), and editing any of them invalidates the approval.
5. **Generation** (`generate.py`). A pure function: approved patterns + seeds
   + approvals → candidate rows. Cached (`build/generated.jsonl`, gitignored)
   with an input fingerprint that self-invalidates the cache the moment any
   input changes — not a second source of truth.
6. **Task building** (`task_builder.py`). Converts one `TaskIntent`
   (description, properties, policy) into a `TaskRecord` using the
   *provider's* contract types. This is the one deliberately narrow seam
   between "authoring" and "verification" — it doesn't import the rest of
   the authoring pipeline.
7. **Static gates** (`static_gates.py`) run before any provider call: import
   allowlist, de-libraryization, intra-corpus exact-duplicate rejection.
8. **Qualification** (the provider's `oracle/qualify.py:qualify_task`, not
   authoring code — `build.py` calls it and states explicitly "no oracle
   logic lives here"). This is the real interpreter check: materialize
   reference observations, execute the candidate, verify its behavior
   matches — the fix for `pep750`'s "did not raise" defect. Also checks
   every *degenerate* candidate (old-form fallback) actually fails, so a
   task can't be satisfied by avoiding the feature.
9. **Diversity vs. dedup** (`diversity.py`) — three distinct things, not
   conflated: exact-content duplicates are a hard build-time rejection;
   semantic/near-duplicates are reported, never gated; structural
   fingerprints (identifiers/constants erased) are a diversity metric only,
   never proof of a duplicate.
10. **Composition** (`composition.py`, `composition.toml`). Target marginal
    proportions across five dimensions — `property`, `source_kind`, `role`,
    `domain`, `operation` — plus `mandatory_strata` that must always appear
    (including a `negative` control) and no implicit uniform default: every
    stratum in the file must be represented.
11. **Sampling** (`sampling.py`, `sampling.toml`). A nested, stratified
    selection plan (source kind → property → pattern → seed) that pulls from
    the qualified pool to hit composition's targets, preferring distinct
    seeds/patterns at the leaf so the selection doesn't collapse onto a few
    of them.
12. **Build** (`build.py`). Renders qualified intents into `TaskRecord`s,
    applies the gates above plus provider qualification, dedups, and halts
    the whole publication on any benchmark contamination. Writes atomic
    artifacts: the corpus snapshot, `reports/dropped.jsonl` (full content of
    everything rejected, not just a count), `reports/build.md`, and a
    row → seed → occurrence lineage bundle.
13. **Review** (`review.py`). Human verdicts on seeds, keyed by a content
    hash — so re-review is scoped to what actually changed, not the whole
    seed set.
14. **Publish** (`publish.py`). Writes nested snapshots — 500 ⊂ 2k ⊂ 5k — by
    stratifying the largest first and selecting each smaller size from the
    larger one, so row IDs nest by construction. Every snapshot is rechecked
    (qualification, contamination, composition match against calibration)
    immediately before its atomic write, alongside its manifest, lineage,
    and source/license `NOTICE`.

## Where to look for what

| question | file |
| --- | --- |
| What counts as a valid source? | `sources.toml`, `sources.py` |
| What proportions is the corpus targeting? | `composition.toml` |
| How does a 500-row pilot get selected? | `sampling.toml`, `sampling.py` |
| What's a `Pattern`, and which ones are approved? | `patterns/catalog.py`, `patterns/approvals.jsonl` |
| What's thin in the current pool, and what to add next? | `SP5_SCALE_BRIEF.md` |
| How does a candidate actually get checked for correctness? | `oracle/qualify.py`, `oracle/verify.py` (provider, not authoring) |

## Where this machinery's output actually goes

This document stops at step 14 — a published, composition-matched corpus
snapshot. What happens to it after that (training, evaluation, the trained
result) is a separate concern with its own harness (`spike/`) and is not
part of the authoring pipeline described here. See `README.md`'s "What is
established" for the actual numbers, and `adapters/m2i-runA-*/` for the
trained adapters themselves — `corpus-sft/` (this pipeline's published
output, re-shaped into Mellum2's SFT schema) is their only connection to
everything above.
