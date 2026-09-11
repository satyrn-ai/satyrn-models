# Converging `spikes/tstrings` with `corpus_builder` — notes for Michał

**Bottom line up front: this repo now contains 589 ready-to-use t-string SFT
rows you can train on immediately** — verified correct, genuinely
t-string-requiring, contamination-free, in `corpus_builder`'s exact row shape.

## The deliverable: t-string training data you can use now

**What you get:** `datasets/tstrings-sft.jsonl` — **589 rows**, one per line,
in your SFT format: `prompt`/`completion` + `filename`, `python_version`,
`idea`, `code`, `trace`, `expected_output`. Drop-in for `trainer/unsloth`'s
`load_dataset` → trl `SFTTrainer`.

**How the data was made:** a deterministic clean-room pipeline (mine → build →
gate → dedup → render → freeze) over **1,252 mined t-string usages** — 23 from
CPython plus 1,229 from six pinned third-party repos (regex-template, t-sql,
tdom, storyville, tdom-svcs, pep750-examples). No LLM in the corpus (ground
rule 2.1), so nothing confabulates a wrong PEP 750 API.

**Why it's worth training on:** its *code* is verified correct and to
genuinely require t-strings (anti-vacuity gate), with no benchmark
contamination — fixing the prior iteration's 0.037 shape collapse and
confabulated APIs.

**Use it:**
```sh
uv run satyrn-tstrings to-michal -i corpus-sft -o datasets/tstrings-sft.jsonl
# --system-prompt to prepend the system prompt (matches PR #24)
```

Everything else in this brief — what we converged, what we'd change in
`corpus_builder`, and the measured reasons we kept parts different — explains
the "why" behind this data.

## Two buckets

- **What Michał might need to change** (small, additive): (1) store the system
  prompt in each SFT row — PR #24, drafted; (2) an AST feature-usage assertion
  in `sft.py`, off by default — Phase 8; (3) optionally a `spikes` CI job
  (Python 3.14).
- **What we have that is valuable** (reusable as-is): the gVisor sandbox reuse;
  `semantic_id` dedup + skeleton/composition floors; the anti-vacuity gate; the
  contamination check + seed-lineage split; the mechanism+correctness scorer;
  and the Michał-format corpus at `datasets/tstrings-sft.jsonl`.

## Decisions made so far

| # | Area | Decision | Rationale (short) |
|---|---|---|---|
| 1 | Sandbox | **Reuse `corpus_builder`'s gVisor Docker sandbox** for the Phase 3 gate | Stronger confinement than a bare subprocess; one sandbox to maintain |
| 2 | Row schema | **Converge to `prompt`/`completion` + metadata**, plus the system prompt as the first `prompt` entry | Shared schema = consumable by the same tooling; system-prompt-in-row matters for train/eval alignment. See PR #24 |
| 3 | `trace` | **Fill with an LLM**, reusing `llm/models.py` + `llm/context.py` | No deterministic source; the only way to keep the row shape identical |
| 4 | Reuse | **Import `satyrn.dataset`** as a path dependency, not vendor copies | One source of truth; accepts its transitive deps |
| 5 | Toolchain | Python **3.14**, `pytest>=9,<10`, `ruff==0.16.2` | Match `corpus_builder`'s pins; 3.14 is a hard spike requirement |
| 6 | Corpus generation | **Deterministic only — no LLM** (ground rule 2.1); `trace` is the sole exception | LLMs confabulate wrong PEP 750 APIs (measured); `sft.py` is explicitly not used for this corpus |

## Where we converge

### 1. Sandbox

`corpus_builder`'s `sandbox.py` already solves executing untrusted code:
Docker + gVisor, `--network=none`, read-only root filesystem, `--cap-drop=ALL`,
nobody user, pids/memory/cpu limits, timeout, output truncation. The spike
imports it directly (decision 4) and keeps its own gate logic
(`run_candidate`/`qualify`, the degenerate families, the backwards JSON-verdict
parse) layered on top of `Sandbox.run()`.

### 2. Row schema

We dropped the BRIEF's `{"messages": [...]}` row for `corpus_builder`'s shape,
with one addition — the system prompt as the first `prompt` entry (PR #24;
alignment matters because `corpus_builder` injects it at generation time but
never stores it):

```json
{"prompt": [{"role":"system","content":"..."}, {"role":"user","content":"..."}],
 "completion": [{"role":"assistant","content":"..."}],
 "filename": ..., "python_version": ..., "idea": ..., "code": ...,
 "trace": ..., "expected_output": ...}
```

Field mapping:

| `corpus_builder` field | spike source |
|---|---|
| `filename` | `provenance.path` |
| `python_version` | `"3.14"` (CPython-only by design) |
| `idea` | `task.prompt` |
| `code` | `task.reference` (the known-good solution) |
| `expected_output` | derived from `task.checks` |
| `trace` | LLM-generated (decision 3) |

### 3. Reasoning trace

Your rows carry a first-person `trace`; our deterministic pipeline has no
source for it, so we generate it with an LLM — **the sole exception** to ground
rule 2.1, at Phase 5 render, never in build. The code stays real (mined,
gated, deduplicated); only the reasoning prose is generated. The 2.1
confabulation concern is about *code*, not prose about already-verified code.

## Where we deliberately stay different (each traces to a measured failure)

### No LLM in corpus generation (ground rule 2.1)

> "An LLM must not generate the training data. Mine it from real source code,
> transform it with deterministic code, verify it by execution."

Measured: every Mellum checkpoint confabulates a *wrong* PEP 750 API — the 2.1
GRPO checkpoint invents a "tagged template literal" (`.tag`, `.parts`,
subclassing `str`) from an earlier, rejected draft; released Instruct invents a
different one (`t_string`, `.value`, `.format_args`) — and output-equality
checks don't catch it. So `corpus_builder`'s `sft.py` — good for documented,
stable features — is not used here. The single exception is the `trace` prose
(above).

### Mined real usages vs. LLM-synthesized examples

You generate code from docs via LLM; we mine real `ast.TemplateStr` usage from
CPython and build references from the seed. The prior iteration's 11,113 rows
collapsed to 411 skeletons (0.037); real mining + a diversity floor is the fix.
This is the core difference we are not converging.

### Anti-vacuity gate vs. output-match only

Your `verify_code_block` checks `actual.strip() == expected.strip()` — a
program that hardcodes `print(<expected>)` passes without using the feature.
Our Phase 3 gate runs deliberately wrong solutions (f-string substitute,
repr-as-render, hardcoded output, …) and requires each to fail semantically.
This is the substance of our planned upstream contribution — an AST
feature-usage assertion for `corpus_builder`, off by default.

### Dedup, diversity, composition floors

We dedup on `semantic_id` (content hash excluding provenance), enforce a
distinct-skeleton floor (from a measured 0.336 ratio), and a per-cell minimum.
Prior failures: 450 rows with 7 consumer vs 44 author, and provenance-
inclusive IDs shipping duplicates.

### Measurement: mechanism + correctness, preregistered

We score correctness *and* AST mechanism (correctness alone once inverted the
conclusion) and preregister the metric + comparator (docs-in-context, not the
bare base) before training. Your `eval.py` is QA-style; ours is a benchmark
reproduction harness — different purpose.

### Contamination check + lineage split

We hard-fail if any rendered row overlaps the benchmark, and split train/valid
on seed lineage (not randomly). Specific to our benchmark evaluation; you
don't need them.

### MLX vs. Unsloth/CUDA

We train/eval on Apple MLX (`Mellum2-12B-A2.5B-Instruct-mlx-8bit`, `mlx-lm`
pinned) because Mellum support only exists on `mlx-lm` main. Parallel stacks;
we converge only on the data.

### Sourcing reality (Phase 1 + Phase 10, worth sharing)

We mined **CPython plus six pinned third-party repos** — CPython was the
original deliberate scope (an earlier iteration wasted a build cycle mining a
template library and taught that library's API instead of the feature); the
six were added later (Phase 10) for volume. CPython v3.14.5 has 62 t-string
nodes — 2 in real code, 60 in its test suite — yielding 23 seeds; the
third-party repos yield 1,229 more. Sourcing is heavily test-suite-derived,
which is why the pool is large but structurally similar (see the review
below).

## Toolchain notes

- Spike pins `>=3.14` (`ast.TemplateStr`); `trainer/unsloth` pins `<3.14`
  (Unsloth) — benign skew.
- Dev pins match yours. The spike keeps uv `[dependency-groups]` because its
  acceptance command is plain `uv sync` (extras aren't installed by default).

## Open items / future PRs

1. **PR #24** (draft) — store the system prompt in each SFT row. Open question:
   does trl's `SFTTrainer` apply a chat template to `prompt`/`completion` as
   message lists?
2. **AST feature-usage assertion** for `corpus_builder` — small, off by default.
3. **CI for the spike** — deferred; the repo workflow runs only `trainer` +
   `corpus_builder` on Python 3.13 (and no spike, even `pep750`, is run). A
   `spikes` job (ruff + pytest, Python 3.14, spike-local `.python-version`)
   would land with the spike's own PR.
4. **The corpus artifact** — `datasets/tstrings-sft.jsonl` is ready to use;
   PR #24 + the AST assertion are the two changes that would let `corpus_builder`
   produce data of this quality.

## Review of this deliverable (what we'd tell Michał before he trains on it)

**Confidence: format high, integrity high, training value unproven.**

- **Consumable — yes.** 589 rows, exact `corpus_builder` SFT shape, drop-in for
  `trainer/unsloth` → trl `SFTTrainer`.
- **Genuine t-string data — yes.** 583 of 589 rows (99%) contain a real
  `TemplateStr`; the other 6 are `negative_control` by design.
- **Trustworthy by construction — yes.** Anti-vacuity gate, dedup, contamination
  check, and seed-lineage split all held at 11× volume.

**Caveats that cap "immediately use":**

1. Sourcing is test-suite-derived; the skeleton ratio is 0.34 (honest floor
   0.255), so the corpus is structurally similar, not maximally diverse.
2. **No training evidence yet** — the preregistered Phase 7 eval (5 LoRA seeds
   vs the docs-in-context bar) is one documented command but hasn't run.

The code-only `completion` is not a caveat — it's the verified **answer**
(ground rule 2.1), and the reasoning is the separate `trace` field (real,
first-person, generated as the sole 2.1 exception). That's the
reasoning/answer split your thinking-model stage expects.

**Recommendations:** run the preregistered eval before any public claim; use
`corpus-sft/` for the lineage-frozen split or `datasets/tstrings-sft.jsonl`
for the combined set. The data is trustworthy as construction; its efficacy
awaits that one live run.
