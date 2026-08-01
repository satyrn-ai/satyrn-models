# satyrn-model

Produce versioned training datasets for teaching models Python 3.14 template
strings (t-strings).

## Project context

This repository is an experiment in teaching small local code models
post-cutoff Python features. The evidence phase found that the base model
prefers f-strings, that a 24-example corpus memorizes instead of generalizing,
and that the original workflow could accept examples that were wrong while
passing their own tests. The durable work is split into two efforts:

- `worktree-tstrings-rebuild` is the provider: versioned task contracts,
  reference/candidate verification, contamination checks, benchmark, training,
  and evaluation.
- `worktree-sp5-corpus-brainstorm` is this SP5 consumer: t-string sources,
  seeds, extraction, properties, patterns, generated rows, reports, and
  dataset snapshots.

This branch does not build the provider, train a model, score a benchmark, or
decide whether fine-tuning beats retrieval.

## Start here

Read these in order before changing anything:

1. [Roadmap](docs/superpowers/roadmap.md) — current phase, dependencies, and
   next cycle.
2. [SP5 corpus design](docs/superpowers/specs/2026-07-31-seed-and-pattern-corpus-design.md)
   — scope, data model, threat model, and Definition of Done.
3. [SP5 implementation plan](docs/superpowers/plans/2026-08-01-tstring-training-data.md)
   — TDD tasks and checkpoints.
4. [Provider/consumer boundary](docs/superpowers/research/2026-08-01-roadmap-convergence-brief.md)
   — what belongs in this branch and what belongs in the provider.
5. [Spike findings](docs/superpowers/research/2026-07-31-spike-findings.md)
   — evidence behind the safeguards.
6. [Execution readiness](docs/superpowers/research/2026-08-01-sp5-execution-readiness.md)
   — interpreter pin, source policy, fixtures, and provider blockers.

For the broader experiment, see the [weekend co-development background](https://hackmd.io/@pauleveritt/HJJhQzsSfg),
[How I Use SDD](https://hackmd.io/@pauleveritt/SkNzlMoHMg), and the
[PEP 750 specification](https://peps.python.org/pep-0750/).

## First prompt

Use this as the first prompt when starting work on this branch:

```text
Read docs/superpowers/roadmap.md first. Identify the current SP5 cycle and
required pre-reading, then read the SP5 design, implementation plan, boundary
brief, spike findings, and execution-readiness record. Confirm that the
provider-owned SP0 reset/package baseline has landed on main and that this
worktree consumes it; do not recreate a scaffold or import another worktree.
For the next approved SP5 task, propose the failing fixtures, exact files, and
focused checks before implementing anything. Keep this branch limited to
t-string training-data production.
```

## Setup

This branch is pinned to Python 3.14.5 and uses [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
```

Before Task 1, consume the provider-owned SP0 reset/package baseline on
`main`. Do not recreate its `src/` scaffold or import code from the provider
worktree. The implementation plan names the focused test command for each
task; this branch is currently at the specification, fixture, and readiness
stage.

## Working agreements

- Keep examples stdlib-only; third-party literals may be de-libraryized into
  seeds, but third-party APIs must not appear in published examples.
- Treat provider execution as the source of expected observations; never write
  trusted expected values into a row.
- Preserve source, seed, occurrence, license, pattern, and decision lineage.
- Stop on benchmark contamination or a missing sandbox guarantee.
- Use the SDD cycle: brainstorm, research, spec, plan, implement, review.
- Record false directions and negative results; they are part of the evidence.

---

## Current work: building a corpus that can actually teach t-strings

> The scripts documented further down are **placeholders awaiting retirement**
> by SP0 R1. They are described here for the moment because they are still what
> the repo contains — not because they are the plan.

### What this is

A data project that produces reproducible, provenance-complete training-data
candidates for one language feature: Python 3.14 t-strings. The provider being
rebuilt on `worktree-tstrings-rebuild` verifies and qualifies those candidates;
it owns the contamination, benchmark, training, and evaluation systems. This
branch does not implement those systems itself.

This worktree owns source manifests, t-string seed extraction, CPython/PEP
source-derived rows, authored seeds, properties, patterns, generated rows,
data-quality reports, a versioned composition profile, provenance lineage, and
immutable 500/2k/5k dataset snapshots. It stops at the dataset boundary. Model
training,
benchmark scoring, memorization measurement, and the fine-tune-vs-retrieval
verdict belong to the provider effort.

It has a useful independent first milestone: **collection**. Once the
provider-owned reset/package baseline has landed and this branch has consumed
it, SP5 can pin and license sources, extract safe t-string candidates, retain
multi-origin seed provenance, set its data-owner composition profile, measure
coverage, and author seeds without calling the provider. Those artifacts are
explicitly unqualified input—not final rows or publishable snapshots—until
provider rendering, execution, qualification, and contamination checks are
available.

The current records are:

- [Seed-and-pattern corpus design](docs/superpowers/specs/2026-07-31-seed-and-pattern-corpus-design.md)
  — the primary corpus source.
- [Provider/consumer boundary](docs/superpowers/research/2026-08-01-roadmap-convergence-brief.md)
  — what crosses into the verification/training provider and what stays here.

The [roadmap](docs/superpowers/roadmap.md) sequences the work; the
[spike findings](docs/superpowers/research/2026-07-31-spike-findings.md) record
what a throwaway build already established, and should be read before designing
any rung.

[Execution readiness](docs/superpowers/research/2026-08-01-sp5-execution-readiness.md)
records the exact interpreter pin, source-license policy, fixture inventory,
and the provider release/sandbox requirements that block qualified snapshots.

### Why it is needed

**The model does not know t-strings, and actively prefers the wrong answer.**
Qwen2.5-Coder-7B scores 0/11 on a held-out t-string benchmark — both zero-shot
and with the PEP 750 API supplied in its prompt. Every failure is the same one:
it emits syntactically valid Python and never reaches for `t"..."`. f-strings
are among the most frequent patterns in pretraining, so the competing prior is
enormous and the feature is post-cutoff.

**A small corpus memorizes instead of generalizing.** A LoRA fine-tune on 24
examples reproduces its own training prompts at ~100% while still scoring 0% on
held-out tasks. The pipeline is not the constraint; corpus size is.

**Harvesting real code cannot reach the scale needed.** Training examples must
teach the language feature and the `string.templatelib` stdlib API — not some
library's API surface — so no example may import a third-party package. What
remains admissible is CPython's `test_templatelib.py` (193 lines, 13 test
methods) plus a few dozen PEP 750 examples: one to two orders of magnitude short.

So the corpus has to be *generated*. The difficulty is that generated training
data can be **confidently wrong in ways review does not catch** — the failure
class that dominated the spike, where an example passes its own test while
teaching the wrong thing.

### How it will work

**Seeds × patterns, with observations from provider execution.** Real t-string literals
are extracted from open-source projects and hand-authored to fill gaps. Reviewed
*pattern* functions multiply those seeds into exercises. Emitted rows contain
reference programs and declarative checks, not trusted expected values. The
provider runs each reference on the pinned interpreter and derives its own
comparison observations.

This inverts the human's role from gate to source. Review effort would scale
with output volume; seeding effort scales only with the diversity needed, and
each seed multiplies across every pattern.

Four properties make a large auto-accept path defensible:

1. **No model in the loop.** Patterns are drafted in conversation but land as
   reviewed source code. Generation is deterministic and offline.
2. **Bad states made unrepresentable where possible.** A prompt, its reference
   program, and its checks are projections of one intent. A cross-projection
   gate still checks descriptive drift. The provider wire contract has no
   trusted expected-value field, so candidate-produced data cannot masquerade as
   reference evidence.
3. **Gates carry adversarial tests.** Where a gate is unavoidable — proving a
   check can actually discriminate a real solution from a fake one — a
   planted defect must be demonstrated failing in a live run. Ten are
   specified, four aimed at the gates themselves, because gates are where this
   bug class re-hosts.
4. **Diversity is measured, not assumed.** 200 seeds × 30 patterns is not 6000
   independent examples. Exact repeats are rejected; structural fingerprints
   are diversity metrics, not duplicate proof, and are recorded in every
   published dataset manifest. The
   provider later compares model scores against that metric.

**Third-party code is a seed source, not an example source.** A literal like
`t"<div class={cls}>{body}</div>"` is 100% stdlib; only the library assertions
around it are not. Literals are extracted and rebuilt into stdlib-only
exercises, which is also what supplies domain diversity — SQL, HTML, logging,
regex, and structured-data literals are shaped nothing alike, and that variety
is the structural counter to correlated output.

A known limitation is recorded rather than papered over: execution-derived
ground truth only defines tasks whose answers are mechanically checkable. The
provider's independent benchmark must include naturalistic completion tasks
authored without consulting these patterns. This project records the risk but
does not own the benchmark response.

Implementation sequence: [t-string training-data plan](docs/superpowers/plans/2026-08-01-tstring-training-data.md).

---

## Legacy pipeline (present in the checkout, not SP5 scope)

```bash
# 1. Generate verified training data (requires Python 3.14+)
python make_data.py

# 2. Train
python main.py

# 3. Evaluate the trained model
python eval.py
```

## Scripts

### `make_data.py` — generate and validate training data

Every candidate example is executed on the live interpreter and only written to
`data/pep750.jsonl` if it runs cleanly. Add new examples to the `EXAMPLES` list
at the top of the script.

```bash
python make_data.py                    # validate all examples, write JSONL
python make_data.py --validate-only    # validate all examples, no file write
python make_data.py -c "t'Hello {name}'"            # validate a single snippet
python make_data.py -c "..." -l "my test"           # with a custom label
```

| Flag | Description |
|------|-------------|
| `-v`, `--validate-only` | Run all examples through the interpreter, report pass/fail, don't write JSONL |
| `-c`, `--code` | Validate a single ad-hoc code snippet instead of built-in examples |
| `-l`, `--label` | Label for `--code` output (default: `<snippet>`) |

### `main.py` — train the model

Loads the JSONL via `datasets`, applies LoRA with Unsloth's MLX backend, and
trains with `MLXTrainer`. Saves the adapter to `./qwen2.5-coder-pep750/`.

```bash
python main.py
```

### `eval.py` — evaluate the trained model

Loads the fine-tuned adapter and generates code from prompts, then validates
each completion against the live Python 3.14 interpreter.

```bash
python eval.py                          # run all built-in eval prompts
python eval.py -p "..."                 # single ad-hoc prompt
python eval.py -n 3                     # first 3 built-in prompts only
python eval.py --no-validate            # skip validation, just print generations
python eval.py --max-tokens 512         # increase generation length
```

| Flag | Description |
|------|-------------|
| `-p`, `--prompt` | Single ad-hoc prompt to evaluate |
| `-n`, `--num-prompts` | Number of built-in prompts to evaluate (default: all) |
| `--no-validate` | Skip `exec()` validation — just print generated code |
| `--max-tokens` | Max tokens to generate (default: 256) |
