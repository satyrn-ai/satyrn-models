# Spec: seed-and-pattern corpus authoring (SP5)

**Date:** 2026-07-31
**Status:** approved after provider/consumer reconciliation; implemented by the
t-string training-data plan.
**Supersedes:** SP3's framing (synthesis gated on harvest proving insufficient).

Required pre-reading:
[corpus-authoring brief](../research/2026-07-31-corpus-authoring-brief.md) and
[spike findings](../research/2026-07-31-spike-findings.md). This spec assumes
both and does not restate their evidence.

---

## 1. What this builds and why

A set of reproducible, provider-qualified, provenance-tagged, **stdlib-only**
t-string dataset snapshots at a scale harvesting cannot reach, produced by
multiplying hand-curated *seeds*
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
seed multiplies. Provider-derived observations plus policy and data-quality
gates make a large automated path auditable; they do not make it infallible.

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

`satyrn_model.authoring` is a **consumer** of the provider contracts built on
`worktree-tstrings-rebuild`. This package owns t-string sources, seed and
exercise intent, rendering, data-specific policy, generation, and reports. It
does not implement `oracle`, generic `corpus`/`provenance` wire contracts,
benchmark contamination, model training, or evaluation.

> The spike branch (`worktree-overnight-tstrings-spike`) is reference, not
> foundation. Per the findings doc: *do not carry the spike's code forward;
> carry the judgment.* Two things it retrofitted are designed in here — an
> injectable verify function, and per-gate failure semantics.

CPython/PEP harvest and pattern authoring are two source adapters inside this
data project. Both emit provider `TaskRecord`s. Their local failure semantics
differ: a broken trusted-source extraction fails its source batch, while one
pattern bug produces a damage report naming the pattern and its blast radius.

### 2.1 Stages

| Stage | Command | Output | Committed |
|---|---|---|---|
| Extract | `authoring extract` | `seeds/extracted.jsonl`, `exercises/source.jsonl` | yes |
| Review seeds | `authoring review seeds` | `review/decisions.jsonl` | yes |
| Cover | `authoring coverage` | `reports/coverage.md` | yes |
| Author | *(manual)* | `seeds/authored.jsonl` | yes |
| Audit pattern | `authoring audit-pattern <id>` | `patterns/approvals.jsonl` | yes |
| Generate | `authoring generate` | `build/generated.jsonl` | **no** |
| Build | `authoring build` | `corpus/tstrings.jsonl`, `reports/build.md`, `reports/dropped.jsonl` | yes |

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
- `extract.py` — AST walk for `ast.TemplateStr`, emitting `Seed` records and
  self-contained CPython/PEP `SourceExercise` intents. Reads library source;
  never imports it and never inlines cross-module helpers. The node matcher is
  isolated for testability, not as a commitment to support other language
  features here.
- `seeds.py` — the `Seed` record and its JSONL round-trip.
- `facts.py` — calls the provider's timeout-bounded reference-execution API and
  stores deterministic t-string facts; no local evaluator subprocess.
- `patterns/` — approved pattern functions plus `registry.py`.
- `render.py` — projects an `Exercise` into prompt, reference program,
  provider `CheckSpec`s, and a `PolicyRef`.
- `generate.py` — applies patterns to seeds, emitting `Exercise` intents.
- `provider.py` — thin adapter for provider contract validation, reference
  execution, candidate verification, and contamination. No oracle logic.
- `diversity.py` — fingerprints, metrics, intra-corpus dedup.
- `review.py` — the CLI and decision files.

### 2.3 No model in the loop

**No LLM call exists anywhere in this package.** Patterns are drafted in a chat
session and land as reviewed source in `patterns/`. The pipeline runs offline
and deterministically. Embedding-based clustering is the sole exception and
informs reporting only — never acceptance.

### 2.4 Reuse boundary, honestly scoped

The isolated node matcher in `extract.py` is real and cheap. It does not make
this a multi-feature project. The claim that `generate` and policy are
feature-agnostic is **false** and is not made: the
old-form canary is definitionally f-vs-t, the on-target filter names
templatelib symbols, anti-vacuity injects a dummy t-string, and every worthwhile
pattern introspects `.strings`/`.values`/`convert`. What a future data project
may reuse is the stage decomposition and artifact/decision conventions.
Subprocess execution and its cache remain provider services, not reusable
authoring modules.

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

### 3.2 `Property` and exercise intents

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
class GeneratedExercise:
    id: str
    pattern_id: str
    seeds: tuple[Seed, ...]
    prop: Property

@dataclass(frozen=True)
class SourceExercise:
    id: str
    origin: SourceOrigin
    extracted_intent: str
    reference_program: str
    prop: Property
```

`ExerciseIntent` is the tagged union of these variants. `GeneratedExercise`
enforces `prop.arity == len(seeds)` at construction. `SourceExercise` carries
exact source provenance and has no fictional `pattern_id` or `seed_ids`.
Source extraction accepts only self-contained stdlib programs; it rejects
cross-module helper dependencies rather than adding a resolver/inliner.

**No expected value is stored on the intent or emitted row.** Nothing would tie
such a field to its exact intent, so a batching bug would yield a well-formed
but internally inconsistent exercise. `render.py` emits declarative
`CheckSpec`s for the exact reference program; the provider executes that
program and derives internal observations. The data project never serializes
those observations as trusted input.

**No composition tag.** Labels are derived mechanically from the `Property`
variant per the table above. Multi-label at the row, single-sourced at the
intent, nothing self-declared left to game. Single-label precedence would
systematically misfile renderer-idiom rows — which both author *and* consume a
template, and which the findings doc calls the canonical training content.

### 3.3 `Facts`

Produced by the provider reference-execution API for `(template_expr,
bindings)`, keyed by content hash of that pair: `strings`, `values`, and
`interpolations` with
`expression`/`conversion`/`format_spec`.

Per-seed facts are the degenerate case. Provider reference execution **must** be keyed on the
expression rather than the seed, because a composed template's facts are not
derivable from its parts even in principle: `Template.__add__` collapses
adjacent strings, so `t"Hello " + t"World"` yields `.strings == ("Hello World",)`.

Every seed is evaluated **twice**; a mismatch rejects it as nondeterministic,
catching `datetime.now()` and `random` at extraction time rather than as flaky
provider failures later. Every observation must use a provider-approved
serialization or comparison projection. A value with no approved
representation is rejected; this project does not embed `repr` output into
executable checks.

The provider performs subprocess isolation and timeout enforcement, batched
**per seed** (~200 calls, not 5k). This project never evaluates
third-party-authored expressions in-process and never implements a competing
subprocess runner.

### 3.4 `Provenance`

The provider owns a tagged provenance union. This project populates two real
variants rather than filling one shape with fictional values:

- source-derived rows identify repository, immutable ref, path, exact span,
  license record, and verifying interpreter;
- generated rows identify this project, pattern ID and source hash, all seed
  IDs, generator version, and verifying interpreter.

Per-seed origins live on the `Seed` records and are reached through `seed_ids`,
rather than copying one seed's origin onto a row built from three. A generated
row's pattern hash is the same key used by `approvals.jsonl`; a dirty registry
therefore cannot stamp a row with a commit ref that never contained it.

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

### 4.1 Provider verification boundary

Verification is an external provider contract. It executes references and
candidates in isolated subprocesses with timeouts and returns typed stages.
This project renders provider `CheckSpec`s and supplies the t-string
`FeaturePolicy`; it does not generate pytest files or interpret process exit
codes.

The canary carries a hard-won precision: `ast.Interpolation.format_spec` is
*itself* an `ast.JoinedStr`, so a naive "flag every JoinedStr" rejects **every
correct `t"{v:.2f}"`**. The rule exempts nodes reachable only through a
`.format_spec` slot while still descending into them, so a genuine f-string
nested in a spec expression is still caught.

The t-string policy retains the hard-won AST precision below, while the
provider owns invocation, caching, pooling, and stage preservation.
The policy is packaged as a dependency-isolated provider plugin: it depends on
provider contracts but imports no source, seed, pattern, or authoring module.

### 4.2 Check-spec grammar

The provider owns the closed `CheckSpec` tagged union and rejects arbitrary
Python checks. This project maps each `Property` variant to permitted provider
forms: value/field observation, type observation, containment observation, or
expected exception. Candidate-derived values cannot appear as their own
expected values because the wire contract has no expected-value field.

Whole-`Interpolation` equality stays banned by t-string policy; field-wise
projection through `Introspect.field` avoids unstable representation. Each
`Property` variant declares its permitted `CheckSpec` forms. An off-grammar
projection is a data-policy failure before snapshot publication.

### 4.3 Degenerate builder and anti-vacuity

Degenerates are derived from the same `Exercise` intent that produced the
solution, **not** reverse-engineered from the solution's AST. This closes a
defect found in the spike's shipped code: its builder covered only `ast.Assign`
and `ast.FunctionDef`, so an `AnnAssign`-style solution (`tpl: Template = t'...'`)
yielded a degenerate defining nothing.

Failure must originate at the provider's **semantic-check stage**. The provider
distinguishes this from parse, policy, execution, timeout, and infrastructure
failure. A degenerate dying before a check counts as **vacuity untested**, never
as vacuity tested. This project supplies intent-derived degenerates; it does not
parse subprocess or pytest output.

### 4.4 Cross-projection consistency

Prompt and checks are both projections of one `Property`, so they cannot
disagree about *which* property is under test. They can still disagree about how
it is described: a prompt renderer saying `.values` while the check renderer
checks `.strings` reproduces the defect centrally.

This is **a gate, not an impossibility**, and is named as such. The check
verifies that a rendered prompt references the property its rendered checks
observe. Per-renderer golden tests provably cannot catch it, since each renderer
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
| t-string policy validation | drop row, report |
| provider self-verification | drop row, report |
| provider anti-vacuity qualification | drop row, report |
| check-spec/property grammar | drop row, report |
| cross-projection consistency | fail the affected pattern |
| composition classifier | **fail the pattern** |
| missing or stale pattern audit | **halt the build** |
| any benchmark contamination | **halt publication** |

Contamination keeps its unconditional raise from the findings doc. There is no
"small enough to drop" exception. The provider re-derives prompt/code
similarity thresholds on the 500-row pilot because the spike's 11×24
distribution does not transfer; SP5 supplies calibration rows but does not own
or reinterpret the result.

### 4.7 Provider cache boundary

The provider owns execution caching and process pooling. Dataset manifests
record the provider and execution-contract versions used during verification.
A clean `authoring build --no-cache` asks the provider to bypass its cache and must
produce the same accepted rows and typed rejection reasons as a warm build.

This project may cache pure generation outputs by seed/pattern/input hash. It
must not cache or reinterpret provider verdicts independently.

### 4.8 Planted defects

Eight, in `tests/adversarial/`, each demonstrated failing in a **live run**
rather than asserted in prose. Four target gates rather than the pipeline,
because gates are where this bug class re-hosts.

| # | Planted | Must be caught by | Lands in |
|---|---|---|---|
| 1 | f-string solution to a template task | provider policy stage | R2c |
| 2 | attempted candidate-vs-candidate check | provider contract rejection | R2d |
| 3 | vacuous check (`assert True`-grade intent) | provider task qualification | R2c |
| 4 | `AnnAssign`/`ClassDef` solution + vacuous check | provider returns *vacuity untested* | R2c |
| 5 | prompt renderer describing `.values`, test checking `.strings` | cross-projection check | R5 |
| 6 | row lacking a feature its `Property` implies | classifier | R5 |
| 7 | `TemplateStr` solution labelled `requires_template=False` | label gate | R2c |
| 8 | duplicate of a benchmark task | provider contamination halts | R6b |

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

The provider must not consume a snapshot for training until the snapshot
manifest records the committed thresholds and passes provider eligibility.

### 5.3 Published scale slices

This project publishes 500, 2k, and 5k dataset snapshots with composition held
constant and effective diversity reported. `sampling.toml` records the
selection rule and random seed; each manifest records the selected row IDs and
all input fingerprints.

The provider trains and scores these slices. Its held-out curve and diagnosis
(working corpus, correlation, or task-distribution bias) are consumer results,
not authoring build outputs.

### 5.4 Build report

`reports/build.md` carries source-derived/generated counts, total row count,
the three diversity numbers, achieved versus target composition mix, drops
grouped by reason **and by pattern** (a
pattern-shaped defect appears as a cluster — that is the signal worth
surfacing), provider eligibility/contamination result, and the provider/version
fingerprints. Provider cache hit rate is operational telemetry, not an SP5 data
metric.

---

## 6. Testing strategy

1. **Unit tests per module.**
2. **The eight planted defects**, live. A first-class deliverable, not test
   hygiene.
3. **Golden tests per (Property variant, renderer)**, plus the cross-projection
   check, which per-renderer goldens provably cannot catch.
4. **Property and invariant tests** — provider-observation determinism and
   serialization compatibility,
   JSONL round-trip preserving tuple types and frozen-dataclass equality, arity
   enforcement, content-derived id stability, atomic artifact writes on
   interrupted builds.
5. **End-to-end:**
   - **Golden mini-corpus** — 3 fixture seeds × 2 fixture patterns through
     extract→generate→build, output asserted byte-identical. The only test that
     catches cross-stage integration drift.
   - **Provider equivalence** — provider cold and warm modes produce identical
     accepted rows and typed stages; this is a contract test, not a local
     oracle implementation test.
   - **Provider fixture compatibility** — the pinned contract fixtures validate
     from this worktree and fail clearly on version drift.

---

## 7. Rungs

| Rung | Summary |
|---|---|
| R1 | **Source validation + extraction.** `grep -c 't"' ≥ 1` across all candidate repos **before** building extraction — the tdom category error's standing corrective. `sources.toml` records URL, pinned SHA, license, and (post-extraction) novel-skeleton contribution; zero-contribution repos drop from future refreshes. Shallow clones into a gitignored cache, `assert_source_pin`. AST extraction emits literal seeds plus self-contained CPython/PEP `SourceExercise` intents; cross-module helpers are rejected. Content-derived ids. |
| R2a | **Provider adapter + contract fixtures.** Reference execution, verification, and typed stages are consumed, not implemented. |
| R2b | **Data model** — `Seed`, `SourceExercise | GeneratedExercise`, `Property`, generated-arity invariant. Pure dataclasses; pulled early because R2c/R2d depend on `Property`. |
| R2c | **T-string policy + provider qualification integration** + defects 1, 3, 4, 7. No runner. |
| R2d | **Property-to-`CheckSpec` grammar** + defect 2. The provider owns the generic wire grammar. |
| R3 | **Seed facts + review CLI.** Call provider reference execution twice and reject unsupported observations. Facts-first review with palette auto-accept and cached `(name, expression)` decisions. Seed dedup by fingerprint bucket. |
| R4 | **Coverage analysis + seed authoring.** Grammar-shape × task-type matrix (`rt`-strings, implicit concatenation, nested quotes, format-spec nesting, `!r`/`!s`/`!a`, multiline, empty edge cases × emit/introspect/transform/negative). Owner authors seeds filling measured gaps; Self-Instruct's 100–200 is the floor for the combined budget. |
| R5 | **Patterns and generation.** Renderers, cross-projection check, composition classifier, pattern registry, `audit-pattern`, generation to the fingerprinted cache. Defects 5, 6. |
| R6a | **Provider integration + generation cache**, with cold/warm provider equivalence and pure-generation cache invalidation tests. |
| R6b | **Build-gate integration** — provider contamination/eligibility call, local intra-corpus dedup, composition-mix reporting, and defect 8. |
| R6c | **Reports** — `build.md`, `dropped.jsonl`. |
| R6d | **Adjudication CLI** + migration report. UI rather than verification; may trail R7. |
| R7 | **Pilot + threshold derivation.** ~500 rows. Commit diversity thresholds, the classifier tolerance band, and the review-budget fraction with their derivations; supply calibration pairs/rows for provider-owned contamination thresholds. |
| R8 | **Dataset slice publication.** Immutable 500 → 2k → 5k snapshots, composition held constant, manifests and effective-diversity reports committed. Provider performs the training sweep. |

Rungs are deliberately small around verification-heavy work: each planted defect
is *designed to fail first*, so bundling six into one rung builds in six
potential fix rounds. That shape cost the spike a task that needed two fix
rounds, a pivot, and deletion.

### 7.1 Blocking dependencies

- R2a and every verified-row claim require the provider's versioned dataset,
  reference-execution, policy, and typed-stage contract fixtures.
- Final build publication requires a provider benchmark fingerprint and
  contamination result. Benchmark design and baseline strength are not SP5
  work.
- R8 requires the R7 composition and diversity thresholds, but not a model run.
  Training and evaluation may occur later without changing the published data.

---

## 8. Known residual risks

**Verifiability bias at the consumer boundary.** Execution-derived
ground truth only defines tasks whose answers are mechanically checkable, which
is the same sub-skill skew already found in the 24-row corpus. The deployment
skill is different: choosing `t"` over `f"` in open-ended code and writing the
renderer idiom unprompted. If the provider benchmark shares this restricted
distribution, its scale curve could rise while prior-fallback behaviour stays
flat. This project cannot fix that corpus-side; it reports composition and
leaves the independent benchmark response to the provider.

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
   reproduces `corpus/tstrings.jsonl` **byte-identically**.
2. All eight planted defects fail live in CI.
3. Corpus ≥ 5k rows; distinct-skeleton count and composition mix within the
   bands committed at R7; zero benchmark contamination conflicts.
4. Human decisions across both decision files number ≤ the review-budget
   fraction of emitted rows committed at R7 — the measurable form of "the
   owner's time went to seeds and patterns, not per-example review."
5. Immutable 500, 2k, and 5k snapshots published with composition held
   constant, effective diversity reported, and provider/benchmark fingerprints
   recorded. No model-performance verdict is required from this project.
