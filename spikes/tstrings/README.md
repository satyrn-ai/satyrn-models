# satyrn-model

Build the durable infrastructure for teaching small local code models
post-cutoff Python features, starting with Python 3.14
[template strings](https://peps.python.org/pep-0750/) (t-strings).

## Current status

The current status has two deliberately short-lived tracks:

- `overnight-tstrings-spike` established the evidence.
- `tstrings-rebuild` is rebuilding the provider infrastructure.
- `sp5-corpus-brainstorm` owns the separate t-string-data producer.

Success means learning the workflow, recording decisions and false directions,
and producing trustworthy evidence about the training approach. A negative
result is still a successful result. When this phase ends, we will rebuild the
SDD and restart the project at [`satyrn-ai`](https://github.com/satyrn-ai).

## Why this effort exists

The base model scored 0/11 on held-out t-string tasks, both zero-shot and with
the API in its prompt, consistently falling back to the much stronger
pretraining prior for f-strings. A LoRA run on 24 examples reproduced its
training prompts at about 100% while still scoring 0% held out. The lesson is
that the pipeline is not the binding constraint: trustworthy scale and
independent measurement are.

The spike also found a more dangerous failure mode: examples could be valid
Python and pass their own checks while teaching the wrong thing. The provider
exists to make reference-derived observations, typed rejection stages,
anti-vacuity qualification, contamination halts, and adversarial gate tests
the durable machinery around every future dataset—not to manufacture the
t-string examples itself.

## Provider scope

This branch verifies externally produced datasets, guards an independent
benchmark, trains models, and evaluates results. It replaces the retired
placeholder scripts with versioned provider contracts and reproducible run
artifacts.

It does not harvest CPython, extract literals, author seeds, generate patterns,
or decide corpus composition. The t-string-data project owns those jobs and
publishes versioned dataset snapshots for this provider to ingest.

The throwaway spike proved a small corpus could memorize prompts without
generalizing, and exposed a recurring “wrong, but passes its own test” defect
class. This rebuild makes those failures structurally impossible where it can
and gives every remaining gate an executable adversarial witness. See the
[spike findings](docs/superpowers/research/2026-07-31-spike-findings.md).

Dataset producers provide reference programs, declarative checks, policy IDs,
and provenance—not trusted expected values. The provider executes each
reference in a fail-closed OS-sandboxed subprocess, derives observations, and
verifies candidates with typed failure stages. It owns contamination checks,
the benchmark, model baselines, training rendering and loss masking,
fine-tuning, memorization measurement, and evaluation.

The current design record is the
[SP0–SP2 rebuild spec](docs/superpowers/specs/2026-08-01-sp0-sp2-rebuild-design.md).
The implementation sequence is the
[provider plan](docs/superpowers/plans/2026-08-01-verification-measurement-training.md).

Two **binding obligations** on the provider↔policy boundary, and the record of a
three-effort split that was proposed and reversed, are in the
[effort boundary record](docs/superpowers/research/2026-08-02-effort-split-decision.md):
the cross-boundary adversarial gate (blocking — a stub-only registry run
reproduces the spike's defect class) and the protocol-churn tripwire.

## Start here

- [Weekend co-development: background and setup](https://hackmd.io/@pauleveritt/HJJhQzsSfg)
- [How I Use SDD](https://hackmd.io/@pauleveritt/SkNzlMoHMg)
- [`docs/superpowers/roadmap.md`](docs/superpowers/roadmap.md)
- [`DATASET_METHODOLOGY.md`](DATASET_METHODOLOGY.md)
- [Dataset workflow spec](docs/superpowers/specs/2026-07-30-dataset-workflow-design.md)
- [Provider rebuild spec](docs/superpowers/specs/2026-08-01-sp0-sp2-rebuild-design.md)
- [Provider implementation plan](docs/superpowers/plans/2026-08-01-verification-measurement-training.md)

## Superpowers resources for this phase

These are the authoritative resources for the provider rebuild, in reading
order:

1. [Spike findings](docs/superpowers/research/2026-07-31-spike-findings.md) —
   verified evidence, the recurring defect class, and expired decisions.
2. [Dataset methodology](DATASET_METHODOLOGY.md) — literature review and
   corrections that constrain the workflow.
3. [Dataset workflow spec](docs/superpowers/specs/2026-07-30-dataset-workflow-design.md) —
   parent workflow decisions.
4. [Provider threat-model spec](docs/superpowers/specs/2026-08-01-sp0-sp2-rebuild-design.md) —
   provider boundary, invariants, and adversarial obligations.
5. [Provider implementation plan](docs/superpowers/plans/2026-08-01-verification-measurement-training.md) —
   the executable task sequence; Task 0 is complete in this branch.
6. [Effort boundary record](docs/superpowers/research/2026-08-02-effort-split-decision.md) —
   **read before Task 4.** The cross-boundary adversarial gate is a blocking
   requirement on that task, not optional hardening, plus the protocol-churn
   tripwire on the `FeaturePolicy` seam.
7. [Roadmap](docs/superpowers/roadmap.md) — historical cross-project index;
   use the provider plan for current task order.

The companion `worktree-sp5-corpus-brainstorm` is the producer-side project.
It owns sources, seeds, patterns, composition, and dataset snapshots. Do not
copy its authoring code into this provider package.

## First prompt

Start the next implementation cycle with this prompt from the repository root:

```text
Read README.md, docs/superpowers/research/2026-07-31-spike-findings.md,
docs/superpowers/specs/2026-08-01-sp0-sp2-rebuild-design.md, and
docs/superpowers/plans/2026-08-01-verification-measurement-training.md.

Task 0 is complete in commit 9aad0d4. Implement provider Task 1: the versioned
dataset and policy contracts. Define DatasetSnapshot, TaskRecord, CompletionSpec,
the closed CheckSpec union, FeaturePolicy, Provenance, PolicyRef, and contract
version constants. Add the canonical JSON fixture and TDD ingest-rejection
tests for malformed data, unknown versions, duplicate or mismatched IDs,
unregistered policies, policy-version mismatch, unknown completion modes, and
caller-supplied expected values. Do not import the SP5 authoring package or
implement reference execution yet. Run the focused suite, then ruff, ty, and
the full pytest suite; stop if the plan and repository disagree.
```

## Setup

1. Fork this repository.
2. Clone your fork.
3. Install Python 3.14+, [`uv`](https://docs.astral.sh/uv/), and `pytest`.
4. Set up [Superpowers](https://github.com/obra/superpowers) for your agent.
5. Make the Hugging Face CLI (`hf`) available before the model-baseline rung.

From the repository checkout:

```bash
uv sync
```

Ruff, ty, and [RTK](https://github.com/rtk-ai/rtk) are useful development
tools. There is no required branch naming convention for this experiment.

### Agents, inference, and models

Use the agent you already know. If you are unsure, use Pi with Superpowers;
Codex, Claude Code, and OpenCode are also suitable. Use native inference with
Codex or Claude Code. With Pi or OpenCode, [OpenRouter](https://openrouter.ai/)
is a convenient option; direct DeepSeek access is also fine.

The experiment uses `Qwen2.5-Coder-7B` because it is small, fast, inexpensive
to run, and predates the feature being taught. It is a proving-ground model,
not the intended long-term model:

```bash
hf download Qwen/Qwen2.5-Coder-7B
```

Do not use Anthropic, OpenAI, or another commercial model to generate the
actual training data or participate in model training, except in disposable
experiments that will be thrown away. Commercial models may otherwise be used
for planning, research, coding, critique, and SDD work, subject to their
provider terms.

## Ground rules

- Measure before scaling training work.
- Use SDD: brainstorm, spec, plan, implementation, review.
- Prefer executable tests and evidence over intuition.
- Treat negative results as valid outcomes.
- Keep training examples stdlib-only.
- “Did not raise” is never enough to establish correctness.
- Require provenance for every training example.
- Stop on benchmark contamination; do not explain it away.
- Record false directions and discarded ideas.

## How we use SDD

Work in feature cycles:

1. Brainstorm with the agent.
2. Research open questions and risks.
3. Write a feature spec.
4. Write an implementation plan.
5. Implement the approved plan.
6. Review the result and merge it.

The roadmap is the starting point for every cycle. Before proposing work, read
[`docs/superpowers/roadmap.md`](docs/superpowers/roadmap.md), identify the
current phase and next cycle, and follow its required pre-reading. Use the
roadmap to group cycles into phases; use its backlog for open research and its
archive for completed or discarded work.

SDD artifacts live in:

- [`docs/superpowers/roadmap.md`](docs/superpowers/roadmap.md) — phase and cycle index
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — approved specifications
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — implementation plans
- [`docs/superpowers/research/`](docs/superpowers/research/) — dated findings and decisions

## Prompt starters

Start every prompt by making the roadmap context explicit. Adapt these
examples to the current cycle.

### Brainstorm

```text
Read docs/superpowers/roadmap.md first. Identify the current phase, next cycle,
and required pre-reading. Brainstorm how we should approach [feature]. Do not
implement yet. Surface risks, false directions, evidence we need, and open
questions.
```

### Research

```text
Read the roadmap and the relevant research and spec files before proposing a
design. Investigate [question]. Separate verified facts from assumptions,
record failed directions, and recommend the smallest useful next step.
```

### Spec

```text
Read the roadmap and the completed brainstorm for the current cycle. Turn it
into a feature spec with scope, non-goals, decisions, verification obligations,
and a Definition of Done. Do not write implementation code yet.
```

### Plan

```text
Read the roadmap and the approved spec for the current cycle. Produce an
implementation plan with exact files, tests, checkpoints, and review gates.
Call out anything the spec leaves unresolved.
```

### Implement

```text
Read docs/superpowers/roadmap.md, the current spec, and the implementation plan
before changing code. Implement only the approved cycle. Run the specified
checks, report evidence, and stop if the plan or repository state is
contradictory.
```

### Review

```text
Read the roadmap, spec, plan, and the resulting diff. Review this cycle
adversarially. Look for missing tests, false assumptions, contamination,
unverified expected values, and ways the result could appear to work without
actually working.
```

### Challenge a direction

```text
Read the roadmap and all required pre-reading. Challenge the assumption that
[direction] is the right next step. Look for evidence that it is unnecessary,
contaminated, too small to measure, or solving the wrong problem. Recommend
whether to continue, revise, archive, or replace it.
```

### Put something on the backlog

```text
Read docs/superpowers/roadmap.md first. Evaluate this idea as backlog work:
[idea]. Summarize the motivation, evidence still needed, dependencies, and a
clear trigger for promoting it into a feature cycle. If it is not ready, add a
concise entry to the roadmap backlog rather than starting implementation.
```

## Layout

- `src/satyrn_model/` — provider package
- `corpus/quarantine/` — retired examples of unverified provenance; seed
  material only, never corpus rows or benchmark tasks
- `docs/superpowers/{specs,plans,research}/` — design record
- `tests/` — pytest suite

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ty check
```

Requires Python 3.14+: t-strings do not parse on earlier interpreters.
