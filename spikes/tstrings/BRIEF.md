# BRIEF: t-strings training spike, clean-room rebuild

This document is the complete specification for a clean-room rebuild of the
t-strings training spike. It is written to be implemented by someone — human or
model — with no prior context on this project. Everything needed is here or is
reachable from a path named here.

Read this whole document before writing any code. The ground rules in section 2
are the ones most likely to be violated by an implementer acting reasonably
without context.

---

## Amendments (convergence with `corpus_builder`)

This BRIEF is amended by `docs/corpus-builder-convergence.md`, which is
authoritative for the following decisions. Where this document conflicts with
that one, the amendment wins; the roadmap's phase ordering is unchanged.

1. **Phase 3 executor.** The anti-vacuity gate runs candidates through
   `corpus_builder`'s gVisor Docker sandbox (`satyrn.dataset.utils.sandbox`),
   imported directly, instead of a bare subprocess. The gate logic
   (`run_candidate` / `qualify`, the degenerate families, the backwards
   JSON-verdict parse) is unchanged.
2. **Phase 5 row schema.** Rendered rows use `corpus_builder`'s shape:
   `prompt` (with the deployment system prompt as its first entry),
   `completion`, plus metadata `filename`, `python_version`, `idea`, `code`,
   `trace`, `expected_output`. The `{"messages": [...]}` shape is dropped.
3. **Reasoning `trace`.** The `trace` field is generated with an LLM
   (`satyrn.dataset.llm`), a hybrid of deterministic code and generated
   reasoning.
4. **Dependencies.** The spike imports `satyrn.dataset` (path dependency on
   `satyrn-corpus-builder`) rather than remaining fully self-contained.
5. **Toolchain.** Dev pins match `corpus_builder` exactly (`pytest>=9,<10`,
   `ruff==0.16.2`); Python 3.14 is pinned spike-locally via
   `spikes/tstrings/.python-version` (repo root stays 3.13, per the
   `spikes/pep750` precedent).

---

## 1. What you are building

A pipeline that produces supervised fine-tuning (SFT) data teaching a small code
model to use **PEP 750 template strings** (t-strings), a Python 3.14 language
feature, plus the evaluation harness that measures whether the training worked.

The feature being taught, stated precisely because models get this wrong:

```python
from string.templatelib import Template, Interpolation

name = "world"
template = t"Hello {name}!"          # a t-string literal; type is Template
template.strings                      # ('Hello ', '!')       — static parts
template.values                       # ('world',)            — evaluated values
template.interpolations               # (Interpolation(...),) — full metadata
isinstance(template, str)             # False — Template is NOT a str subclass
```

A `Template` is not a string and does not render itself. Code must walk
`.strings` / `.interpolations` to produce output. This is the whole point of the
feature and the thing the corpus must teach.

The end state is:

1. A corpus of verified t-strings tasks rendered as chat-format SFT rows.
2. A gate proving each task genuinely *requires* t-strings — an f-string
   solution must demonstrably fail.
3. An out-of-distribution benchmark and a scorer that measures both correctness
   and whether the model actually used the feature.
4. Multi-seed LoRA training runs and an honest report.

---

## 2. Ground rules — non-negotiable

**2.1 An LLM must not generate the training data.** Mine it from real source
code, transform it with deterministic code, verify it by execution. Do not call
an LLM API to write corpus rows, reference solutions, or prompts.

This rule exists because of measured evidence, not preference. Every Mellum
checkpoint tested confabulates a *wrong* PEP 750 API, and each one confabulates
a different wrong API:

- The 2.1 GRPO step-200 checkpoint invents a "tagged template literal" with
  `.tag` and `.parts`, subclassing `str` — an API from an **earlier, rejected
  PEP 750 draft**. This artifact is **specific to 2.1**; do not attribute it to
  other checkpoints.
- The released Instruct checkpoint invents a *different* wrong API: `t_string`,
  `.value`, `.format_args`.
- All checkpoints sometimes resolve "t-string" as **"triple-quoted string"** and
  emit an f-string in triple quotes.

A generator model asked to write t-strings training data will produce
confident, runnable, wrong-API code. Output-equality checks do not catch this,
because a program can print the right answer while using the wrong API or no
API at all.

There is a working LLM-based SFT generator in this repo at
`corpus_builder/src/satyrn/dataset/sft.py` (author: Michał Karzyński). It is
good code and appropriate for its purpose — generating data about documented,
stable features. **Do not use it for this corpus.** The temptation to do so is
the single most likely way this rebuild goes wrong.

**2.2 "Did not raise" never establishes correctness.** A task enters the corpus
only if a deliberately degenerate solution has been *executed* and *observed to
fail*. See section 7, Phase 3.

**2.3 Record false directions.** Rejected candidates are written to disk with a
reason, not silently dropped. Negative results are valid results and are
reported as such.

**2.4 Stop on benchmark contamination.** If training rows overlap the benchmark,
fail the build. Do not explain it away or filter quietly.

**2.5 Never execute mined source.** Extraction is AST-only. Parse, never
import, never `exec`.

---

## 3. What you inherit

A previous iteration of this spike exists on branch `integration/tstrings-spike`
at path `spikes/tstrings/`. **Do not read its source code** — this is a
clean-room rebuild and its abstractions are deliberately not being carried
forward. You may copy the following **data artifacts**, which are inputs, not
implementations:

```sh
# The out-of-distribution benchmark. Authored by an agent with no repository
# access, specifically so its phrasing could not mirror the training corpus.
git show integration/tstrings-spike:spikes/tstrings/benchmark/ood-v2/tasks.jsonl   > benchmark/ood-v2/tasks.jsonl
git show integration/tstrings-spike:spikes/tstrings/benchmark/ood-v2/manifest.json > benchmark/ood-v2/manifest.json
git show integration/tstrings-spike:spikes/tstrings/benchmark/ood-v2/fingerprint.txt > benchmark/ood-v2/fingerprint.txt
```

`tasks.jsonl` is 100 tasks. `fingerprint.txt` must read exactly:

```
3a94d381b74c5e905f7005d5f2d93eb1e493cc74568381f143f1a0b033832658
```

**You must also copy the trained adapters and their recorded scores.** Phase 6's
acceptance criterion depends on them; without these, Phase 6 cannot be
validated and the whole measurement chain is unanchored.

```sh
# Six LoRA adapters: m2i-runA-repair-v2, m2i-runA-seed43 … m2i-runA-seed47
git archive integration/tstrings-spike spikes/tstrings/adapters | tar -x --strip-components=2
# Recorded scores from the previous harness on the same 100-task benchmark
git archive integration/tstrings-spike spikes/tstrings/results | tar -x --strip-components=2
```

**The documentation block is also frozen data.** The docs-in-context evaluation
arm places a specific documentation text in the prompt, and its score depends
entirely on which text that is. Copy it:

```sh
git show integration/tstrings-spike:spikes/tstrings/spike/pep750-docs-context-v3.md \
  > benchmark/pep750-docs-context-v3.md
```

It must be 5588 bytes with sha256:

```
582c42a688a406abe9494705dde670964a23d5512b8d0d11a6679c60c2f50f31
```

Freezing the benchmark while leaving the docs block unpinned would defeat the
purpose: the docs arm is the comparator that decides whether this project
succeeded, and an unpinned comparator drifts.

These adapters are reference *data* for validating your instrument. Do not read
the code that produced them.

Nothing else is carried forward.

---

## 4. Why this rebuild exists

The previous iteration produced real results and real, documented failures. The
failures are why the phase acceptance criteria below are shaped the way they
are. Do not treat them as arbitrary.

- **Shape collapse.** A build of 11,113 candidate rows collapsed onto only 411
  distinct program skeletons — a ratio of 0.037. Generating many rows is easy;
  generating many *different* rows is the actual problem. This is why Phase 2
  and Phase 4 acceptance is measured in distinctness, not volume.

  Read that 0.037 carefully: it is the **full un-deduped build**, and it is the
  wrong denominator for judging a post-deduplication corpus. The same iteration
  selected a 500-row pilot from that build and carried **168 distinct
  skeletons — a ratio of 0.336** (`reports/threshold-derivation.json` on
  `integration/tstrings-spike`). Pilot scale, after deduplication and
  composition control, is the regime your Phase 4 output lives in. 0.336 is the
  anchor. Anyone quoting 0.037 as the bar to beat is comparing against the
  wrong stage of the pipeline.
- **Composition imbalance.** In a 450-row training split there were 7 consumer
  `.strings` rows against 44 author `.strings` rows. Downstream batching cannot
  repair a corpus that is lopsided at the source. This is why Phase 4 requires a
  composition floor.
- **Duplicate leakage.** Task IDs included provenance, so deduplication keyed on
  them let byte-identical lessons ship repeatedly under different sources, and
  validation answers appeared in training under other framings. This is why
  Phase 2 defines *two* IDs and Phase 4 dedups on the semantic one.
- **Measurement instability.** Four successive scoring instruments produced four
  different verdicts on the same completions. Exact-match alone declared total
  collapse; a naive "is it a `str`" check mis-scored tasks; type-match alone
  declared the untrained model the winner while it used zero t-strings. Only
  type + mechanism together produced a sensible reading. This is why the Phase 6
  scorer checks mechanism, always.
- **A parsing bug produced a spurious result.** Completions that called
  `print()` were misfiled as infrastructure failures, hitting only the untrained
  control arm and manufacturing a significant-looking p-value that evaporated on
  inspection. This is why the Phase 3 harness protocol is specified exactly.

---

## 5. Conventions

This spike lives inside a repository owned by someone else's architecture.
Match it. Read `corpus_builder/` and `trainer/unsloth/` for reference style.

- **Layout:** `src/` layout, `hatchling` build backend, one installable package.
- **CLI:** `click`, a single group with subcommands, options as
  `-i/--input`, `-o/--output-dir`, `click.Path(path_type=Path)`.
- **Errors:** user-facing failures raise `click.ClickException`; library
  failures raise built-ins with a concrete message.
- **Paths:** `pathlib` everywhere, never `os.path`.
- **Logging:** `logger.info("... %s", value)` — printf style, never f-strings in
  log calls.
- **Docstrings:** one line, imperative mood, on every public function.
- **Lint:** the repository root `ruff.toml` governs. Line length 120.
- **Python:** pin to `>=3.14`. `ast.TemplateStr` does not exist before 3.14.
- **Testing:** `pytest`. Unlike the rest of this repository, this spike has
  tests, and every phase below defines what they must assert.

Package name: `satyrn.tstrings`, directory `spikes/tstrings/`.

---

## 6. Architecture

Five stages, each a module, each independently testable:

```
sources.toml  ──▶  mine   ──▶  build   ──▶  gate   ──▶  render  ──▶  train/eval
 (pinned)         seeds       tasks      verified       SFT rows      adapters
                                          tasks                       + scores
```

Everything through `render` runs locally on CPU. Training and evaluation run
locally on Apple MLX. There is no cloud step and no CUDA step.

Data shapes, defined once:

```python
@dataclass(frozen=True, kw_only=True)
class Seed:
    """A t-string usage mined from pinned source."""
    text: str            # the source snippet
    source_id: str       # key into sources.toml
    path: str            # file path within the source
    line: int

@dataclass(frozen=True, kw_only=True)
class Provenance:
    """Where a task came from, for audit and licensing."""
    source_id: str       # key into sources.toml
    path: str
    line: int
    license: str         # SPDX identifier, copied from sources.toml

@dataclass(frozen=True, kw_only=True)
class Check:
    """One assertion a candidate program must satisfy."""
    kind: str            # "expected_value" | "expected_stdout" | "uses_feature"
    expected: str        # for uses_feature, the required module or node name

@dataclass(frozen=True, kw_only=True)
class Task:
    """One teachable unit: a prompt, a known-good solution, and its checks."""
    prompt: str
    reference: str       # a complete, runnable program
    checks: tuple[Check, ...]
    role: str            # "author" | "consumer"
    operation: str       # see the cell table in Phase 2
    provenance: Provenance
    task_id: str         # sha256 over content INCLUDING provenance
    semantic_id: str     # sha256 over content EXCLUDING provenance
```

Compute both IDs as `sha256` over a canonical JSON dump with sorted keys.
`task_id` hashes every field except itself and `semantic_id`. `semantic_id`
hashes the same fields minus `provenance`.

The two IDs are not redundant. `task_id` identifies a specific sourced row;
`semantic_id` identifies *the lesson*. Two rows mined from different files that
teach the identical thing share a `semantic_id` and differ in `task_id`.
Deduplication and train/valid splitting both key on `semantic_id`. Using
`task_id` for either is the documented bug from section 4.

---

## 7. Phases

Each phase is independently verifiable. Do not begin a phase until the previous
phase's acceptance criteria pass. Every acceptance criterion below is
mechanically checkable — a command runs and either passes or fails.

**Splitting this into implementation plans.** Nine phases is more than one plan.
The seams, in order of preference:

- **Primary cut at 5/6.** Phases 0–5 produce a frozen, reviewable corpus
  (`corpus-sft/{train,valid}.jsonl` plus its manifest); phases 6–7 build the
  measurement instrument and consume that corpus. The corpus is a clean handoff.
- **Keep 6 and 7 together.** The preregistration in Phase 7 must name the exact
  metric the Phase 6 harness validates. Split them and the metric gets
  re-derived and drifts from the validated instrument. If they must be split,
  freeze the metric definition to a file at the end of Phase 6 and have Phase 7
  reference it verbatim.
- **Phase 8 is its own plan.** It is gated on a human conversation and depends
  on nothing else here. Bundling it makes the experiment appear to wait on a
  social step it does not actually need.
- **Expect a sub-split at 2/3** if plan size forces it. Phases 0–2 produce
  candidate tasks (`tasks/built.jsonl`, unverified); 3–5 gate, deduplicate, and
  render. Phase 2 is the overload point — see its warning below.

### Phase 0 — Skeleton and inherited artifacts

Create the package skeleton and copy in the frozen benchmark.

- `spikes/tstrings/pyproject.toml`: hatchling, `requires-python = ">=3.14"`,
  deps `click`; dev group `pytest`, `ruff`.
- `src/satyrn/tstrings/__init__.py`, `cli.py` with a `click.group()` and a
  `--help` that lists the subcommands to come.
- Copy the three `benchmark/ood-v2/` files per section 3.
- `tests/test_benchmark_frozen.py`: recompute sha256 over `tasks.jsonl` and
  assert it equals `fingerprint.txt`; assert the file has exactly 100 lines.

**Accept:** `uv sync` succeeds; `ruff check .` clean; `satyrn-tstrings --help`
exits 0; `pytest` passes with the fingerprint test green.

### Phase 1 — Pinned sources and AST-only mining

Mine t-string usages from CPython. **CPython only.** Third-party libraries are
explicitly out of scope for this rebuild — an earlier iteration spent a build
cycle mining a template library and taught that library's API instead of the
language feature.

- `sources.toml`: one entry per source with `repo`, `tag`, `commit` (full SHA),
  `license` (SPDX identifier), and the paths to mine. Pin CPython at tag
  `v3.14.5`. A source without a commit SHA is a hard error.
- `mine.py`: `mine_seeds(source_root: Path, spec: SourceSpec) -> list[Seed]`.
  Parse with `ast.parse`; find `ast.TemplateStr` nodes; capture the enclosing
  statement or function as `Seed.text`. Never import, never `exec`.
- Write `seeds/mined.jsonl`, one `Seed` per line.

**Accept:** a test parses a fixture file containing known t-strings and asserts
the expected count and line numbers; a test asserts `mine_seeds` never calls
`exec`, `eval`, `compile`, or `importlib` (assert by AST-inspecting your own
module, or by monkeypatching those names to raise); a test asserts a source
entry lacking `commit` raises.

### Phase 2 — Seeds to tasks

Turn seeds into teachable tasks. **This is the largest phase and the one where a
context-free implementer most reliably fails**, because it is easy to generate
many rows that are all the same shape.

Define the cell table explicitly in `cells.toml`. Every task occupies one cell:

| role | operation |
|---|---|
| author | `construct` — build a Template from parts |
| consumer | `read_strings` — use `.strings` |
| consumer | `read_values` — use `.values` |
| consumer | `read_interpolations` — use `.interpolations`, incl. `.conversion` and `.format_spec` |
| consumer | `render` — walk a Template to produce output |
| consumer | `negative_control` — a task correctly solved *without* t-strings |

`negative_control` rows are deliberate: a corpus of only t-string-requiring
tasks teaches the model to reach for t-strings unconditionally.

**Amended (measured source reality, 2026-08-18):** the `compose` cell is
dropped. CPython v3.14.5 (the pinned source, 23 mined seeds) never combines
two Templates, so a compose task's reference would have to be invented rather
than mined — against the mine-don't-invent principle. Revisit only with
evidence. Remaining cells, measured: construct 23 seeds, render 10,
read_interpolations 4, read_strings 2, read_values 2, negative_control 6.

Each task needs a **prompt family** — a distinct phrasing template. Write at
least six prompt families and vary which is used, so prompt wording does not
correlate with operation. The prior iteration's benchmark scores were partly
measuring wording response rather than capability because these were coupled.

- `build.py`: `build_tasks(seeds: list[Seed]) -> list[Task]`, plus
  `task_id()` / `semantic_id()` per section 6.
- Write `tasks/built.jsonl` and `reports/dropped.jsonl` (rejected candidates
  with a `reason` field — ground rule 2.3).

A **prompt fingerprint** is `sha256` of the prompt text after normalization:
lowercase, collapse runs of whitespace to one space, and replace every
identifier and literal drawn from the seed with a placeholder token. Two
prompts built from the same family with different variable names must produce
the *same* fingerprint — otherwise the metric measures variable naming rather
than phrasing variety, and reports diversity that is not there.

Set each cell's floor in `cells.toml` as `min_tasks` **by measurement**
(amended 2026-08-18 — the original "start at 15" assumed an unmeasured source
yield). Run the first build, count real tasks per cell, then write floors from
the measured counts — generous where the source is abundant (construct),
honest where thin. A floor is never guessed. The build fails naming any cell
that falls below its floor.

Derivation discipline: one task per seed per *demonstrated* operation. Do not
extend every seed into every cell by re-spinning prompts — that is the shape
collapse this phase exists to prevent (measured 0.037 skeleton ratio in the
prior iteration). The corpus is expected to be small (~50–100 tasks) and
construct-heavy; that is accepted (BRIEF §8, §9).

Measure prompt variety as an **absolute count of distinct fingerprints, not a
ratio**. A ratio against total tasks is coupled to volume with no upper bound:
fingerprints vary by (prompt family × operation), so roughly 6 families × 7
cells ≈ 42 are available regardless of how many tasks you mine. Mining more
aggressively would then *fail* this phase for doing exactly what Phase 4
rewards. Count the numerator; leave the denominator alone.

**Accept:** every cell in `cells.toml` meets its `min_tasks` floor (fail the
build otherwise, naming the starved cell); there are **at least as many distinct
prompt fingerprints as the measured build produces** (amended 2026-08-18 — the
original "at least 35" assumed an unmeasured 7-cell yield; the measured ceiling
for the 23-seed source is 28, achieved 28), and at least 4 distinct fingerprints
within every occupied cell **that has ≥4 tasks; a thinner cell is floored at its
measured count** (amended 2026-08-18 with the total-fingerprint amendment — the
original "4 per occupied cell" also assumed an unmeasured yield, and the two
thinnest cells, `read_interpolations` and `negative_control`, are capped by
their qualifying-seed counts at 3 and 1). Variety must still be spread across
operations rather than concentrated in one; `task_id` is stable across runs for
identical input; two tasks
differing *only* in provenance share a `semantic_id` and differ in `task_id`.

### Phase 3 — Confinement and the anti-vacuity gate

This phase implements ground rule 2.2. Read it again before starting.

A task is **vacuous** if it can be solved without the feature it claims to
teach. To prove non-vacuity, execute a deliberately wrong solution and confirm
it fails *for the right reason*.

First, the execution layer. Run candidate programs in a subprocess with a
timeout, a clean environment, and no network. The subprocess must return a
**structured outcome**, not a blob of text. Wrap the candidate so its last line
of stdout is a JSON verdict, and parse by scanning stdout **backwards** for the
last parseable JSON object.

Scanning backwards is not a stylistic choice. Candidate programs frequently call
`print()` themselves. An earlier implementation parsed forwards, misread user
output as the verdict, misfiled those runs as infrastructure failures, and
manufactured a statistically significant result that was entirely an artifact.

```python
@dataclass(frozen=True)
class Accepted:
    observations: dict

@dataclass(frozen=True)
class Rejection:
    stage: str          # "syntax" | "import_policy" | "runtime" | "semantic_check"
    detail: str

@dataclass(frozen=True)
class InfrastructureFailure:
    detail: str         # timeout, harness crash, unparseable verdict

Outcome = Accepted | Rejection | InfrastructureFailure

def run_candidate(code: str, checks: tuple[Check, ...], *, timeout: int = 10) -> Outcome: ...
```

Then the gate:

```python
@dataclass(frozen=True)
class Qualified:
    """The task is proven to require the feature."""
    degenerates_run: int

@dataclass(frozen=True)
class Vacuous:
    """A degenerate solution was accepted; the task does not require the feature."""
    degenerate: str

@dataclass(frozen=True)
class VacuityUntested:
    """The proof did not run properly. NOT a pass. Reject and record."""
    degenerate: str
    detail: str

Qualification = Qualified | Vacuous | VacuityUntested

def qualify(task: Task) -> Qualification:
    """Return whether task is proven non-vacuous."""
```

Only `Qualified` admits a task to the corpus. Both other outcomes are written
to `reports/dropped.jsonl` with their reason.

`qualify` must:

1. Run `task.reference`; it must return `Accepted`.
2. For each degenerate candidate, run it and require a
   `Rejection(stage="semantic_check")`. A degenerate that is `Accepted` means
   the task is **vacuous** — reject it. A degenerate that fails at any *other*
   stage, times out, or returns `InfrastructureFailure` means the test did not
   run properly: return **`VacuityUntested`**, which is not a pass.

Generate at least these degenerate families, not just one:

- **f-string substitute** — solve with an f-string instead of a Template.
- **repr-as-render** — return `repr(template)` or `str(template)`.
- **static-join** — join `.strings` while ignoring interpolated values.
- **conversion-omission** — render but ignore `!r` / `!s` conversions.
- **hardcoded-output** — `print(<the expected answer>)` with no logic.

The last one matters: an output-equality check alone is passable by a program
that hardcodes the answer.

**Accept:** a known-good fixture task qualifies; a fixture task solvable by
f-string is rejected as vacuous; a fixture whose degenerate crashes at import
returns `VacuityUntested`, not a pass; a candidate printing `{"x": 1}` mid-run
does not corrupt verdict parsing.

### Phase 4 — Deduplicate, diversity floor, composition floor

Everything in this phase exists because of a measured failure in section 4.

- `dedupe.py`: `deduplicate(tasks) -> list[Task]` keying on **`semantic_id`**.
- `diversity.py`: compute a structural skeleton per task (normalize identifier
  names and literals, hash the resulting AST shape) and report distinct
  skeletons. Enforce a floor.
- `composition.py`: report task counts per `role × operation` cell and enforce a
  minimum per cell. This is a report plus a floor — not a sampling planner.

Write `reports/build.md` with the composition table and diversity counts.

Derive the skeleton floor rather than guessing it, using the same
measure-then-set pattern as `min_tasks`. On the first build, record the
measured ratio to `reports/threshold-derivation.json`. Thereafter the floor is
`max(0.25, 0.75 × recorded_pilot_ratio)`. The prior iteration measured 0.336 at
pilot scale, which would set a floor of 0.252 — so 0.25 is a conservative
starting value, not an ambitious one.

**Accept:** zero duplicate `semantic_id`s survive; the distinct-skeleton ratio
meets the derived floor (`>= 0.25` on a first build); no cell falls below its
configured floor (the build fails naming the cell); `reports/build.md` exists
and contains both tables; `reports/threshold-derivation.json` records the
measured ratio.

### Phase 5 — Render, contamination check, lineage split

Render qualified tasks into chat-format SFT rows matching the schema already
used elsewhere in this repository:

```json
{"messages": [
  {"role": "system",    "content": "..."},
  {"role": "user",      "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

Include the deployment system prompt in every row. Prior evidence found system
prompt alignment between training and evaluation to be necessary.

- **Contamination check first, and it hard-fails.** For every rendered row,
  assert neither its `(prompt, reference)` pair nor its bare `reference` string
  appears in `benchmark/ood-v2/tasks.jsonl`. Raise on any overlap. Do not
  filter and continue (ground rule 2.4).
- **Split on lineage.** Group tasks by `semantic_id` *and* originating seed,
  then assign whole groups to train or valid. A random row-level split puts
  near-identical siblings on both sides and makes validation loss meaningless.
- Write `corpus-sft/train.jsonl`, `corpus-sft/valid.jsonl`, and
  `corpus-sft/manifest.json` recording counts, the four fingerprints (dataset,
  rendered, benchmark, system prompt), and the split rule.

**Accept:** a planted row copied from the benchmark causes the build to raise;
no `semantic_id` appears in both `train.jsonl` and `valid.jsonl`; every row
validates against the schema above; `manifest.json` counts match actual line
counts.

### Phase 6 — Evaluation harness

Build the harness that generates completions and scores them. This must exist
and be validated **before** any training run, so that a training result is
measured with an instrument of known behavior.

- Generation via `mlx-lm`, pinned by git commit — Mellum support exists only on
  `mlx-lm` main. Use exactly:
  `rev = "254d153fdeb6f150edd4fc5a54f9828638481fa8"`.
  An unpinned `mlx-lm` silently resolves to a PyPI build that cannot load the
  model, and adapters trained under different builds are not comparable.
- Base model: `jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit`.
- Extract code from completions robustly: strip prose, take fenced blocks,
  handle an unterminated final fence.
- **Score two things, always:** correctness (does it produce the expected
  result) **and** mechanism (does the AST actually reference
  `string.templatelib` / contain a `TemplateStr`). Never report exact match
  alone. A model can score well on correctness while using zero t-strings —
  this was measured, and reporting correctness alone inverted the conclusion.
- Support three arms: untrained base, base with documentation in context, and
  adapter. Claims require all three.

**Reproduction targets.** The previous harness scored the inherited adapters on
this same 100-task benchmark. Those results are in `results/` (copied in
section 3). Reproduce `summary.score` — a 0–1 fraction — **not**
`summary.passed`, which is a different field and does not equal
`score × total`:

| File | `summary.score` |
|---|---|
| `results/eval-v2-base.json` | 0.05 |
| `results/eval-v2-base-docs.json` | 0.61 |
| `results/eval-v2-runA-seed43.json` | 0.52 |
| `results/eval-v2-runA-seed44.json` | 0.47 |
| `results/eval-v2-runA-seed45.json` | 0.54 |
| `results/eval-v2-runA-seed46.json` | 0.58 |
| `results/eval-v2-runA-seed47.json` | 0.52 |

Ignore the `eval-m2i-ood-*` files. Those score a different, 25-task set and are
not the reference.

**Pin every parameter the reference runs used**, or scores will not reproduce
and you will not know whether the cause is your scorer or your settings:

```
model         jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit
benchmark     benchmark/ood-v2/tasks.jsonl   (fingerprint 3a94d381b74c…)
docs block    benchmark/pep750-docs-context-v3.md   (sha256 582c42a688…)
max_tokens    700
decode        greedy, temperature 0
```

Greedy decode matters: sampling noise would otherwise be indistinguishable from
harness disagreement, which is exactly the confusion this check exists to
eliminate. Greedy is appropriate for the released Instruct checkpoint; it is
*not* appropriate for thinking checkpoints, which degenerate at temperature 0,
but those are out of scope here.

**Accept:** scorer unit tests covering correct+mechanism, correct+no-mechanism,
incorrect+mechanism, and unparseable completion; under the pinned settings
above, the harness reproduces within **±0.03** at least one score from **each
of the three tiers** — bare base (0.05), base+docs (0.61), and any one adapter
(0.47–0.58).

One-per-tier is deliberate. Five of the seven reference scores cluster between
0.47 and 0.58, so a harness that scored everything near 0.5 could match three
adapters and pass while being badly wrong about the floor and the ceiling —
the two points that calibrate the instrument's range. Requiring the extremes
also forces the docs block to be wired up correctly during Phase 6, which is
when you want that discovered, rather than during Phase 7 when it silently
moves the bar.

If any tier disagrees by more than ±0.03, stop and find out why. Do not proceed
to training with an unexplained instrument gap.

### Phase 7 — Preregister, train, evaluate, report

- **Write the preregistration first.** Before training, record in
  `PREREGISTRATION.md`: the hypothesis, the arms, the metric, the number of
  seeds, and the decision rule for calling a result positive. Fix it before you
  see any numbers.

  **Preregister against the right comparator.** The bar is not the untrained
  base — it is documentation in the prompt. From the prior iteration's own
  measurements on this benchmark:

  ```
  untrained base          0.05
  base + docs in context  0.61      ← the bar
  best adapter            0.58      ← never cleared it
  adapter mean (5 seeds)  0.526
  ```

  An adapter that beats 0.05 has demonstrated almost nothing; a model shown the
  documentation gets 0.61 for free, with no training at all. The prior
  iteration's adapters did not beat that comparator, and this is the central
  open question the rebuild exists to answer. A decision rule written against
  the bare base would let you declare success while losing to a prompt.

  **Use your own harness's base+docs number as the bar, not the 0.61 above.**
  Run the docs arm in the same session, with the same settings, as the adapter
  arms, and compare against that. The 0.61 is a Phase 6 *reproduction target*
  for validating your instrument; it is not the Phase 7 *bar*. Comparing an
  adapter scored by the new harness against a comparator scored by the old one
  reintroduces exactly the instrument-mismatch error described in section 4,
  where four scoring instruments produced four verdicts on identical
  completions. Both arms must be measured by the same instrument in the same
  run. If your reproduced base+docs score differs materially from 0.61, that is
  a Phase 6 failure to resolve before training — not a bar to adjust after.
- Train LoRA adapters with `mlx-lm`, one per seed, at least five seeds. Report
  the mean and the spread; a single-seed number is not a result.
- Evaluate all arms with the Phase 6 harness.
- Write `REPORT.md`: what was measured, what the numbers were, what is and is
  not supported. State negative results plainly in the verdict line. Do not bury
  them.

**Accept:** `PREREGISTRATION.md` is committed before the first training run
(verify by commit order in `git log`); at least five adapters exist; `REPORT.md`
reports mean and spread per arm and states whether the preregistered decision
rule was met.

### Phase 8 — Upstream contribution

One small pull request to `corpus_builder`, plus a conversation.

The existing `sft.py` verifies generated code by comparing stdout to a predicted
value (`actual.strip() == expected.strip()`). That check is passable by a
program that hardcodes `print(<expected>)`, and nothing verifies the generated
code uses the feature the document describes.

Propose: (a) an AST-level feature-usage assertion, and (b) rejection of trivial
or empty `expected_output`. Roughly forty lines, optional, off by default.

**Framing matters.** Scope the claim to novel-syntax features, where a generator
model's priors predate the final API. Cite precisely: the tagged-template
confabulation is **2.1-checkpoint-specific**; released Instruct confabulates a
different wrong API. Overstating this reads as an attack on a merged design
rather than a contribution to it.

**Do not open the PR without discussing the approach first.** This repository's
data-generation architecture belongs to its author; this is a proposal, not a
correction.

**Accept:** discussion held; PR opened; the change is additive and defaults off.

### Phase 9 — Corpus in Michał's SFT format

Transform the frozen `corpus-sft/` into rows Michał's `corpus_builder`/`trainer`
stack consumes directly. This is the data-handoff half of the upstream
contribution (distinct from Phase 8's code PR).

- `transform.py`: `to_michal_sft(rows, *, system_prompt=False) -> list[dict]` —
  maps the converged rows to Michał's exact shape: `prompt` = `[{"role": "user",
  "content": <idea>}]` (optionally prefixed by the system prompt, aligning with
  PR #24); `completion` = `[{"role": "assistant", "content": fenced code}]`;
  `filename`/`python_version`/`idea`/`code`/`trace`/`expected_output` mapped 1:1.
  Internal fields (`_line`, `semantic_id`) are dropped.
- A `to-michal` CLI command (`-i` corpus-sft dir, `-o` output jsonl,
  `--system-prompt` flag).
- Document the field-by-field mapping (feeds `corpus-builder-convergence.md`).

**Accept:** a fixture row transforms to the exact Michał-shape row; the
`--system-prompt` flag toggles the system entry; the CLI writes a JSONL that
Michał's `load_dataset` (trl `SFTTrainer`) accepts. Content caveats (no
`explanation` preamble; `trace` is mock pending a live key) are documented,
not silently dropped.

### Phase 10 — Broaden sourcing to third-party repositories

Re-open the Phase 1 "CPython only" scope to admit the pinned third-party
repositories the prior iteration sourced (regex-template, t-sql, tdom,
storyville, tdom-svcs, pep750-examples — all MIT, pinned commit SHAs), then
re-run the corpus pipeline over the larger seed pool. Clean-room rule holds:
**pin the repos and run our own AST miner over them** — the prior iteration's
hand-selected seed table is not carried forward.

- `sources.toml` gains the six third-party entries (id, repo, commit, license
  `MIT`, `paths = ["."]`).
- The `mine` CLI resolves **per-source checkouts** (`-i` is a parent dir;
  each `input/<source_id>/` is verified against its own spec and mined).
- Provision each repo at its pinned SHA into a gitignored `.cache/sources/<id>/`.
- Re-run mine → build → gate → dedup → render → freeze; the handoff corpus
  and `datasets/tstrings-sft.jsonl` are regenerated from the larger pool.

**Accept:** each third-party source's checkout SHA verifies; `mine_seeds`
produces non-empty seeds per source; the re-built corpus + Michał dataset
regenerate end-to-end. (Logging was skipped in the prior pass — keep it out.)

---

## 8. Accepted limitations

State these; do not silently carry them as if solved.

- **Contamination detection is exact-match only.** Near-duplicates and
  AST-level overlap are not detected. A paraphrased benchmark task in training
  would pass.
- **CPython-only sourcing** leaves several domains (sql, html, regex, logging)
  uncovered. Adding third-party sources is a later, evidence-backed decision
  with a licensing surface attached.
- **The degenerate families are a fixed list.** The gate is exactly as strong as
  that list. A vacuous task whose shortcut is not in the list passes.
- **CI does not run this spike.** The repository workflow lints only
  `trainer` and `corpus_builder`. Acceptance criteria here run locally. Adding
  the spike to CI requires touching a file owned by someone else.
- **The eval base is 8-bit quantized.** Scores are comparable to this project's
  prior runs and not to published figures on other quantizations.

---

## 9. Caveats for any external claim

If numbers from this spike leave the repository, they carry these conditions:

- Single model family, single quantization, single harness.
- The docs-in-context arm is a strong comparator; an adapter that does not beat
  it has not demonstrated value, regardless of how it compares to the bare base.
- A benchmark of 100 tasks across five seeds detects large effects. Small
  effects are not measurable at this scale, and reporting one as significant
  would repeat a documented error from the prior iteration.
- A negative result is a valid outcome of this spike and is to be reported as
  clearly as a positive one.
