# Spec: seed-and-pattern corpus authoring (SP5)

**Date:** 2026-07-31
**Status:** brainstormed and approved; input to `writing-plans`.
**Supersedes:** SP3's framing (synthesis gated on harvest proving insufficient).

Required pre-reading:
[corpus-authoring brief](../research/2026-07-31-corpus-authoring-brief.md) and
[spike findings](../research/2026-07-31-spike-findings.md). This spec assumes
both and does not restate their evidence.

---

## 1. What this builds and why

A corpus of verified, provenance-tagged, **stdlib-only** t-string examples at a
scale harvesting cannot reach, produced by multiplying hand-curated *seeds*
through reviewed *patterns*, with every expected value derived by **executing**
real code on the pinned interpreter.

Three measured facts force this shape:

- Harvest cannot reach scale under stdlib-only sourcing. CPython's
  `test_templatelib.py` is 193 lines / 13 test methods; PEP 750 adds a few dozen
  examples. That is 1–2 orders of magnitude short.
- `n=24` produces memorization without transfer: 0% held-out against ~100%
  training-prompt recall. The pipeline is not the constraint; corpus size is.
- The base model has no latent t-string knowledge (0/11 zero-shot and with docs
  in context), so results are attributable to training.

The design inverts the human's role: **source, not gate.** Review effort scales
with output volume; seeding effort scales with the diversity needed, and each
seed multiplies. Execution-derived ground truth is what makes a large
auto-accept path safe.

### 1.1 Third-party sources are seed sources, not example sources

The brief's blanket "tdom and all third-party sources are ruled out" is narrowed
here: **no training example may import a third-party package**, but third-party
*literals* are valid seed material. A t-string literal inside a library's tests
is a pure stdlib artifact — `t"<div class={cls}>{content}</div>"` is 100% PEP
750; only the surrounding `TemplateParser.parse(...)` assertions are
library-specific. Literals are extracted and rebuilt into stdlib-only exercises
("de-libraryization").

This matters because the [awesome-t-strings](https://github.com/t-strings/awesome-t-strings)
list yields roughly a dozen repos spanning genuinely different domains — SQL
(`sql-tstring`, `t-sql`), HTML (`tdom`, `tstring-html`, `ludic`,
`pyhtml-enhanced`), logging (`tstringlogger`), regex (`regex-template`),
structured data (`tstring-structured-data`), plus `better-dedent`, `tstr`,
`tstring-util`. Domain diversity in the seed pool is the direct structural
counter to the correlation risk, since a `regex-template` literal is shaped
nothing like a `tdom` one.

### 1.2 The threat model this is designed against

Per the findings doc, one bug class dominated the spike: **wrong, but passes its
own test** — three distinct defects, one recurring after being "fixed", none
caught by the test suite, every one requiring someone actively trying to break
it. The real corpus survived only because a stronger adversary was run by hand
than the committed code enforced.

The governing rule, stated narrowly: **make the bad state unrepresentable where
you can; where only a gate is possible, the gate itself needs an adversarial
test.** Anti-vacuity is inherently a gate — it is a claim about a test's
discriminating power — so this spec does not attempt to eliminate gates. It
requires each one to carry a planted defect demonstrated failing in a live run.

Auto-accept at scale converts every tolerated residual into a systemic one: a
flawed *pattern* replicates identically across all its rows, so per-row
assurance is the wrong unit. Audits are per-pattern.

---

## 2. Architecture

`satyrn_model.authoring`, a peer of `harvest`, over a **reimplemented**
verification core (`oracle`, `gate`, `corpus`, `provenance`, `contamination`).

> The spike branch (`worktree-overnight-tstrings-spike`) is reference, not
> foundation. Per the findings doc: *do not carry the spike's code forward;
> carry the judgment.* Two things it retrofitted are designed in here — an
> injectable verify function, and per-gate failure semantics.

The `authoring` / `harvest` split earns its keep on differing failure
semantics: harvest raises on a bad row; authoring reports. One pattern bug at
row 3121 must produce a damage report naming the pattern and its blast radius,
not a stack trace.

### 2.1 Stages

| Stage | Command | Output | Committed |
|---|---|---|---|
| Extract | `authoring extract` | `seeds/extracted.jsonl` | yes |
| Review seeds | `authoring review seeds` | `review/decisions.jsonl` | yes |
| Cover | `authoring coverage` | `reports/coverage.md` | yes |
| Author | *(manual)* | `seeds/authored.jsonl` | yes |
| Audit pattern | `authoring audit-pattern <id>` | `patterns/approvals.jsonl` | yes |
| Generate | `authoring generate` | `build/generated.jsonl` | **no** |
| Build | `authoring build` | `corpus/authored.jsonl`, `reports/build.md`, `reports/dropped.jsonl` | yes |

`coverage` must run meaningfully on `extracted.jsonl` alone, so the
Cover→Author→Cover loop has a defined first iteration.

Generation is a pure function of committed inputs, so it is **transient as a
contract** but materializes to a gitignored `build/generated.jsonl` carrying an
input fingerprint (seeds hash + pattern-registry hash + generator version) and
self-invalidating on mismatch. It is a cache that knows when it disagrees, not a
second source of truth. `reports/dropped.jsonl` is committed with **full row
content** — drops referenced only by ID are undebuggable.

### 2.2 Modules

- `sources.py` — manifest, clone cache, `assert_source_pin(root, expected_sha)`
  via `git rev-parse HEAD`. Deliberately **not** the CPython pin assertion,
  which demands an exact tag *and* tag ≡ interpreter version; neither
  generalizes to third-party repos. The interpreter check survives as a
  separate global precondition asserted once per run.
- `extract.py` — AST walk for `ast.TemplateStr`, emitting `Seed` records. Reads
  library source; never imports it. Node matcher is a parameter (the one real
  SP4 seam).
- `seeds.py` — the `Seed` record and its JSONL round-trip.
- `evaluate.py` — subprocess-isolated, timeout-bounded expression evaluation.
- `patterns/` — approved pattern functions plus `registry.py`.
- `render.py` — projects an `Exercise` into prompt, reference solution, and
  hidden test.
- `generate.py` — applies patterns to seeds, emitting `Exercise` intents.
- `verify.py` — memoizing, pooling wrapper injected into the gate chain.
- `diversity.py` — fingerprints, metrics, intra-corpus dedup.
- `review.py` — the CLI and decision files.

### 2.3 No model in the loop

**No LLM call exists anywhere in this package.** Patterns are drafted in a chat
session and land as reviewed source in `patterns/`. The pipeline runs offline
and deterministically. Embedding-based clustering is the sole exception and
informs reporting only — never acceptance.

### 2.4 The SP4 seam, honestly scoped

The swappable node matcher in `extract.py` is real and free. The claim that
`generate` and `verify` are feature-agnostic is **false** and is not made: the
old-form canary is definitionally f-vs-t, the on-target filter names
templatelib symbols, anti-vacuity injects a dummy t-string, and every worthwhile
pattern introspects `.strings`/`.values`/`convert`. What SP4 reuses is the stage
decomposition, the artifact and decision conventions, the subprocess evaluator,
and the cache.

---

## 3. Data model

### 3.1 `Seed`

```python
@dataclass(frozen=True)
class Seed:
    id: str                                  # embeds sha256(literal + bindings)
    literal: str                             # "t'<div class={cls}>{body}</div>'"
    free_names: tuple[str, ...]
    bindings: tuple[tuple[str, str], ...]    # (('cls', "'card'"), ...)
    origin: SeedOrigin                       # repo, path, ref, line
    kind: Literal["extracted", "authored"]
```

`bindings` exists because an extracted literal's free names were bound to
**library objects in their original scope**. Extraction proposes stdlib-only
source expressions; seed review confirms them. Tuples rather than dicts
throughout, since the dataclass is frozen and hashable; the JSONL round-trip
normalizes lists back to tuples in `__post_init__` or equality and hashing
silently break.

Ids are **content-derived** so the `seed_ids` join in provenance is
tamper-evident. An audit trail whose targets can be edited underneath it is not
an audit trail.

### 3.2 `Property` and `Exercise`

`Property` is a tagged union. Each variant declares its **arity** and the
assertion-grammar forms it may render to.

| Variant | Fields | Arity | Expected value | Implied labels |
|---|---|---|---|---|
| `Introspect` | `target`, `index`, `field` | 1 | fact at that path | consuming |
| `Render` | `idiom` | 1 | executed rendered output | authoring + consuming |
| `Transform` | `op`, `arity` | 2+ | facts of the composed expression | authoring |
| `NegativeControl` | `expected_solution_kind` | 1 | executed non-template solution | negative |

```python
@dataclass(frozen=True)
class Exercise:
    id: str
    pattern_id: str
    seeds: tuple[Seed, ...]
    prop: Property
```

`__post_init__` enforces `prop.arity == len(seeds)`. That is genuine
unrepresentability and costs nothing.

**No expected value is stored on the intent.** Nothing would tie such a field to
its `(seeds, prop)`, so a batching bug would yield a well-formed but internally
inconsistent exercise. Instead `render_hidden_test` derives it by calling the
evaluator for the exact expression it embeds; a mismatch surfaces as a
`KeyError`, not a wrong literal.

**No composition tag.** Labels are derived mechanically from the `Property`
variant per the table above. Multi-label at the row, single-sourced at the
intent, nothing self-declared left to game. Single-label precedence would
systematically misfile renderer-idiom rows — which both author *and* consume a
template, and which the findings doc calls the canonical training content.

### 3.3 `Facts`

Produced by `evaluate(template_expr, bindings) -> Facts`, keyed by content hash
of that pair: `strings`, `values`, and `interpolations` with
`expression`/`conversion`/`format_spec`.

Per-seed facts are the degenerate case. The evaluator **must** be keyed on the
expression rather than the seed, because a composed template's facts are not
derivable from its parts even in principle: `Template.__add__` collapses
adjacent strings, so `t"Hello " + t"World"` yields `.strings == ("Hello World",)`.

Every seed is evaluated **twice**; a mismatch rejects it as nondeterministic,
catching `datetime.now()` and `random` at extraction time rather than as flaky
oracle failures later. Every value must satisfy `eval(repr(v)) == v`, since
these are embedded into hidden tests as source literals; a value with a
non-evaluable repr is rejected or compared via `str` explicitly.

Evaluation is subprocess-isolated with a timeout, batched **per seed** (~200
runs, not 5k). In-process evaluation is rejected outright: no timeout, no
isolation, and seed expressions are third-party-authored.

### 3.4 `Provenance`

```python
    source_repo: str            # this project
    source_path: str            # patterns/<pattern_id>.py
    source_ref: str             # the pattern's source_sha256
    verified_python: str
    seed_ids: tuple[str, ...] = ()
    pattern_id: str | None = None
    generator_version: str | None = None
```

Every original field stays *true* for a synthesized row rather than becoming a
polite fiction. `source_ref` records the pattern's `source_sha256` rather than a
git SHA, because a dirty registry would otherwise stamp rows with a ref that
never existed — and provenance then agrees with `approvals.jsonl` by
construction, since that is the same key.

Per-seed origins live on the `Seed` records and are reached through `seed_ids`,
rather than copying one seed's origin onto a row built from three. Harvested
rows leave the three new fields empty and load unchanged.

### 3.5 Decision files

Split by lifecycle, because the two have different keys and invalidation rules
and one malformed writer must not corrupt both.

- `patterns/approvals.jsonl` — `{pattern_id, source_sha256, approved_at,
  audit_sha256, audit_passed_at}`. Editing an approved pattern invalidates both
  its approval and its audit. `build` refuses a pattern whose current hash has
  no matching record.
- `review/decisions.jsonl` — `{kind: "seed" | "row" | "binding", content_sha256,
  verdict, reason, decided_at}`. Because a pattern edit invalidates prior row
  decisions wholesale, `review` emits a migration report ("212 rows changed
  since you approved them") scoping re-review to actual diffs.

---

## 4. Verification and gates

### 4.1 Oracle

pytest in an isolated subprocess with a timeout — never in-process `exec`, which
has no timeout, no isolation, and no notion of a hidden test. Three-check
contract: hidden asserts, the feature is actually used (`ast.TemplateStr`
present), and an old-form canary rejecting f-string / `.format()` / `%`.

The canary carries a hard-won precision: `ast.Interpolation.format_spec` is
*itself* an `ast.JoinedStr`, so a naive "flag every JoinedStr" rejects **every
correct `t"{v:.2f}"`**. The rule exempts nodes reachable only through a
`.format_spec` slot while still descending into them, so a genuine f-string
nested in a spec expression is still caught.

`verify_candidate` is injectable throughout the gate chain, so caching and
pooling need no fork of the invariants.

### 4.2 Assertion grammar

Every assertion in a rendered hidden test must match one of four forms. `CExpr`
is defined structurally: an expression whose only free name is `candidate`,
built from attribute and subscript access plus a whitelist of pure wrappers
(`len`, `type`, `str`, `tuple`, templatelib functions).

| Form | Shape | Rendered by |
|---|---|---|
| 1 | `assert <CExpr> == <literal>` | Introspect, Render, Transform |
| 2 | `assert [not] isinstance(<CExpr>, C)`, `C ∈ {Template, Interpolation, str, tuple}` | Introspect, NegativeControl |
| 3 | `assert <literal> in / not in <CExpr>` | Render |
| 4 | `with pytest.raises(E[, match=<literal>]): <CExpr>` | NegativeControl |

Multiple `candidate` references on **one** side are legal and necessary — the
renderer idiom is `candidate.render(candidate.template) == 'hi'`. The ban is on
candidate references on *both* sides, which is what makes the spike's
encoding-no-expected-value defect unrenderable rather than merely detected.

Local aliasing is forbidden via a per-test statement whitelist — imports,
asserts, `raises` blocks, nothing else — so the one-side analysis never needs
dataflow. Whole-`Interpolation` equality stays banned; field-wise projection via
`Introspect.field` covers it and sidesteps the repr-round-trip question.

Each `Property` variant declares its permitted forms, so the check is
per-variant. Off-grammar drops the row.

### 4.3 Degenerate builder and anti-vacuity

Degenerates are derived from the same `Exercise` intent that produced the
solution, **not** reverse-engineered from the solution's AST. This closes a
defect found in the spike's shipped code: its builder covered only `ast.Assign`
and `ast.FunctionDef`, so an `AnnAssign`-style solution (`tpl: Template = t'...'`)
yielded a degenerate defining nothing.

Failure must originate in an **assertion**. pytest's returncode alone cannot
distinguish an assertion failure from a collection or import error, so the
runner parses failed-vs-error; a degenerate dying before executing any assert
counts as **vacuity untested**, never as vacuity tested. In the spike, that
conflation meant a degenerate crashing on `AttributeError` was certified as a
discriminating test.

### 4.4 Cross-projection consistency

Prompt and hidden test are both projections of one `Property`, so they cannot
disagree about *which* property is under test. They can still disagree about how
it is described: a prompt renderer saying `.values` while the test renderer
checks `.strings` reproduces the defect centrally.

This is **a gate, not an impossibility**, and is named as such. The check
verifies that a rendered prompt references the property its rendered test
asserts. Per-renderer golden tests provably cannot catch it, since each renderer
individually matches its own golden output.

### 4.5 Composition classifier

Verifies that each emitted row exhibits the AST features its `Property` variant
implies — `TemplateStr` in the solution for authoring, templatelib consumer API
for consuming, `Interpolation()`/`convert()` for constructor,
`requires_template=False` for negative control. The corpus mix is computed over
`Property` variants. A row lacking a feature its variant implies fails **the
pattern**, within a tolerance band derived at R7 alongside the other thresholds.

This **subsumes the spike's separate on-target filter**. That filter asked
whether a row contained a t-string or templatelib-consuming code at all; the
classifier asks the strictly stronger question of whether it contains the
features its declared intent implies. A row passing the classifier necessarily
passes on-target, so the two are not both maintained.

### 4.6 Per-gate failure semantics

| Gate | On failure |
|---|---|
| `requires_template` validation | drop row, report |
| self-verification | drop row, report |
| anti-vacuity | drop row, report |
| assertion grammar | drop row, report |
| cross-projection consistency | drop row, report |
| composition classifier | **fail the pattern** |
| missing or stale pattern audit | **halt the build** |
| contamination | **raise** above the agreed drop-rate bound |

Contamination keeps its raise per the findings doc's carry-forward list. Below
the bound, conflicting rows are dropped and reported; above it, the conflict is
systemic and the run halts. The bound starts at **2% of emitted rows** and is
re-derived at R7. Its 0.70 code-axis threshold was derived from an 11×24
distribution and **must likewise be re-derived at scale**.

### 4.7 Oracle cache

Key: length-prefixed fields over reference solution, hidden test,
`requires_template`, the timeout value, `ORACLE_CONTRACT_VERSION`, the lockfile
hash, and interpreter version.

Each element is load-bearing. Omitting the contract version would freeze
pre-fix verdicts across a gate change — the most on-brand possible failure for
this project. The lockfile hash covers pytest version and plugins, which affect
outcomes. Length-prefixing avoids concatenation collisions across field
boundaries. `stage="timeout"` results are **never** cached, being a function of
machine load rather than content. The cache is scoped to `verify_candidate`
only; the cheap AST checks always recompute, since the on-target filter reads
the prompt, which is not in the key.

`--no-cache` reverifies from scratch, so the cache is never load-bearing for
correctness.

### 4.8 Planted defects

Eight, in `tests/adversarial/`, each demonstrated failing in a **live run**
rather than asserted in prose. Four target gates rather than the pipeline,
because gates are where this bug class re-hosts.

| # | Planted | Must be caught by | Lands in |
|---|---|---|---|
| 1 | f-string solution to a template task | canary | R2c |
| 2 | candidate-vs-candidate hidden test *(bypasses projection; tests the checker)* | grammar checker | R2d |
| 3 | vacuous hidden test (`assert True`-grade) | anti-vacuity | R2c |
| 4 | `AnnAssign`/`ClassDef` solution + vacuous test | dropped as *vacuity untested* | R2c |
| 5 | prompt renderer describing `.values`, test checking `.strings` | cross-projection check | R5 |
| 6 | row lacking a feature its `Property` implies | classifier | R5 |
| 7 | `TemplateStr` solution labelled `requires_template=False` | label gate | R2c |
| 8 | duplicate of a benchmark task | contamination halts | R2d |

Defect 4 is the one the spike's own code did **not** catch.

---

## 5. Measurement

### 5.1 Metrics

- **Structural fingerprints** — AST skeletons of the template literal and
  reference solution, identifiers and constants erased, shape retained. Counts
  distinct skeletons. Deterministic, no model.
- **Prompt-text diversity** — distinct prompt-template count plus n-gram
  diversity. This is roadmap backlog item B-HEADER at corpus scale: a model can
  learn a few dozen prompt-format→answer-format mappings and transfer nothing.
  The AST metric is structurally blind to it. Renderers must vary surface
  framing (comment / docstring / chat) as a condition of pattern approval.
- **Embedding clustering** — second lens for paraphrases the AST view calls
  distinct. Reporting only, never acceptance.

**Intra-corpus dedup** lives here, by fingerprint **bucketing** (linear), not
similarity scoring — the findings doc names it the genuinely missing piece and
notes the naive form is O(n²). Benchmark × corpus stays with contamination and
is linear anyway, since the benchmark is fixed.

### 5.2 Bootstrap

Dedup is **binary**, not distributional — two rows in one bucket are duplicates
— so it gates from build one. Deferring it would compute the pilot's diversity
numbers over a corpus still containing the duplicates they exist to detect.

Diversity *thresholds* wait, and are derived without self-referential
calibration:

0. Run the measurement suite over the existing 24-row corpus **plus planted
   reference pairs** — a known near-duplicate that must share a bucket, a
   known-diverse pair that must not. The measurement suite is a gate; it gets
   adversarial cases like the rest.
1. ~500-row pilot. Human reads the report.
2. Thresholds derived and committed **with their derivation**.
3. Full build gated.

**No training run consumes a corpus built before thresholds exist.**

### 5.3 Sweep decision rule

Plot held-out score against **effective diversity**, never row count:

| Reading | Action |
|---|---|
| Score rises with diversity | Corpus is working; continue |
| Rows rise, diversity flat, score plateaus | Corpus is correlated — the lever is **more seeds**, not more patterns |
| Diversity rises, score flat | Seeds/patterns are not the constraint; suspect task-distribution bias |

Before charging the benchmark sub-project with the third reading, rule out
B-LOSS-MASK (the spike used naive `prompt + solution` concatenation with no
prompt-token masking) and B-FORMAT.

Composition is held constant across sweep points, or the points are not
comparable — the `n=24` anchor is already polluted by having only ~9 of 24 rows
contain a t-string literal. `sampling.toml` records the selection rule and seed
value, since subsets are not otherwise derivable from committed inputs.

### 5.4 Build report

`reports/build.md` carries row count, the three diversity numbers, achieved
versus target composition mix, drops grouped by reason **and by pattern** (a
pattern-shaped defect appears as a cluster — that is the signal worth
surfacing), the contamination result, and cache hit rate.

---

## 6. Testing strategy

1. **Unit tests per module.**
2. **The eight planted defects**, live. A first-class deliverable, not test
   hygiene.
3. **Golden tests per (Property variant, renderer)**, plus the cross-projection
   check, which per-renderer goldens provably cannot catch.
4. **Property and invariant tests** — evaluator determinism, repr round-trip,
   JSONL round-trip preserving tuple types and frozen-dataclass equality, arity
   enforcement, content-derived id stability, atomic artifact writes on
   interrupted builds.
5. **End-to-end:**
   - **Golden mini-corpus** — 3 fixture seeds × 2 fixture patterns through
     extract→generate→build, output asserted byte-identical. The only test that
     catches cross-stage integration drift.
   - **Cache equivalence** — cold and warm builds produce identical corpora, and
     bumping `ORACLE_CONTRACT_VERSION` provably triggers full re-verification.
     The design leans its entire economics on this cache, and stale-cache bugs
     are silent by nature.
   - **pytest failed-vs-error parser fixtures** — real pytest output for
     assertion failure, collection error, import error, and timeout. Load-bearing
     for defect 4 and fragile across pytest versions, which is why the lockfile
     hash is in the cache key.

---

## 7. Rungs

| Rung | Summary |
|---|---|
| R1 | **Source validation + extraction.** `grep -c 't"' ≥ 1` across all candidate repos **before** building extraction — the tdom category error's standing corrective. `sources.toml` records URL, pinned SHA, license, and (post-extraction) novel-skeleton contribution; zero-contribution repos drop from future refreshes. Shallow clones into a gitignored cache, `assert_source_pin`. AST extraction with free names and palette-proposed bindings. Content-derived ids. |
| R2a | **Oracle + stage parser**, with output fixtures. |
| R2b | **Data model** — `Seed`, `Exercise`, `Property`, arity invariant. Pure dataclasses; pulled early because R2c/R2d depend on `Property`. |
| R2c | **Row-level gate chain** + defects 1, 3, 4, 7. |
| R2d | **Assertion-grammar checker** + defects 2, 8. |
| R3 | **Seed evaluation + review CLI.** Subprocess evaluator, run twice, repr round-trip. Facts-first review with palette auto-accept and cached `(name, expression)` decisions. Seed dedup by fingerprint bucket. |
| R4 | **Coverage analysis + seed authoring.** Grammar-shape × task-type matrix (`rt`-strings, implicit concatenation, nested quotes, format-spec nesting, `!r`/`!s`/`!a`, multiline, empty edge cases × emit/introspect/transform/negative). Owner authors seeds filling measured gaps; Self-Instruct's 100–200 is the floor for the combined budget. |
| R5 | **Patterns and generation.** Renderers, cross-projection check, composition classifier, pattern registry, `audit-pattern`, generation to the fingerprinted cache. Defects 5, 6. |
| R6a | **Oracle cache + process pool**, with equivalence tests. |
| R6b | **Build-gate integration** — contamination, intra-corpus dedup, composition-mix reporting over the R5 classifier. |
| R6c | **Reports** — `build.md`, `dropped.jsonl`. |
| R6d | **Adjudication CLI** + migration report. UI rather than verification; may trail R7. |
| R7 | **Pilot + threshold derivation.** ~500 rows. Commits, each with its derivation: diversity thresholds, the classifier tolerance band, the contamination drop-rate bound, and the review-budget fraction of §9.4. |
| R8 | **Scale sweep.** 500 → 2k → 5k, composition held constant, decision rule applied. |

Rungs are deliberately small around verification-heavy work: each planted defect
is *designed to fail first*, so bundling six into one rung builds in six
potential fix rounds. That shape cost the spike a task that needed two fix
rounds, a pivot, and deletion.

### 7.1 Blocking dependency

**R8 is blocked on the benchmark sub-project**, which must settle four things:

1. Benchmark size — at `n=11`, 0/11 carries a ~25% upper confidence bound by the
   rule of three, too thin to read the sweep's differences.
2. **Naturalistic completion tasks**, scored only on "used a template
   correctly," authored **before any pattern exists** so they cannot be shaped
   by what patterns turn out to be easy to write. This is the answer to the
   verifiability-bias problem in §8.
3. Retrieval-arm strength (findings doc open question 6, raised at Gate 1 and
   never decided). A redesigned benchmark with the same weak with-docs arm still
   cannot adjudicate the §3.2 gate.
4. Composition targets (open question 2).

The benchmark is no longer frozen: its attached baselines are two 0% numbers
that a greedy-decoding rerun reproduces in minutes.

---

## 8. Known residual risks

**Verifiability bias, shared between corpus and benchmark.** Execution-derived
ground truth only defines tasks whose answers are mechanically checkable, which
is the same sub-skill skew already found in the 24-row corpus. The deployment
skill is different: choosing `t"` over `f"` in open-ended code and writing the
renderer idiom unprompted. Because the current benchmark is drawn from the same
restricted distribution, the scale curve could rise while prior-fallback
behaviour stays flat and **no number in the system would show it**. Contamination
halts a run; shared bias inflates it silently. Mitigated benchmark-side by
§7.1's naturalistic slice, not fixable corpus-side.

**Correlation.** 200 seeds × 30 patterns is not 6000 independent examples.
Mitigated by domain-diverse seeds (§1.1), composing/transforming patterns, and
measuring effective diversity rather than row count — but only *mitigated*.

**Contamination's fundamental blind spot.** Some real duplication is uncatchable
by text similarity: a known pair scores 0.267 on code and 0.566 on prompt with
no threshold separating it from noise. "Gate passes" does not mean "no
contamination."

**Cross-projection consistency is a gate.** Alignment is only as good as the
renderers. Planted defect 5 tests it; nothing makes it impossible.

---

## 9. Done condition

Falsifiable:

1. On a clean checkout, `authoring build --no-cache` from committed inputs
   reproduces `corpus/authored.jsonl` **byte-identically**.
2. All eight planted defects fail live in CI.
3. Corpus ≥ 5k rows; distinct-skeleton count and composition mix within the
   bands committed at R7; zero contamination conflicts above the agreed bound.
4. Human decisions across both decision files number ≤ the review-budget
   fraction of emitted rows committed at R7 — the measurable form of "the
   owner's time went to seeds and patterns, not per-example review."
5. Three composition-matched sweep points recorded, with the §5.3 decision
   rule's verdict written down. **Either verdict satisfies this**: "corpus
   correlated" or "task-distribution bias" is a successful outcome under the
   roadmap's negative-result-is-success rule.
