# satyrn-model

Build the long-term infrastructure and training method for teaching small
local code models post-cutoff Python features, starting with Python 3.14
[template strings](https://peps.python.org/pep-0750/) (t-strings).

## Current status

The current status has two deliberately short-lived tracks:

- `overnight-tstrings-spike` established the evidence.
- `tstrings-rebuild` is rebuilding the durable infrastructure.

The roadmap on `main` is now historical coordination context. Active work is
split between `tstrings-rebuild` for provider infrastructure and
`worktree-sp5-corpus-brainstorm` for training-data production.

Success means learning the workflow, recording decisions and false directions,
and producing trustworthy evidence about the training approach. A negative
result is still a successful result. When this phase ends, we will rebuild the
SDD and restart the project at [`satyrn-ai`](https://github.com/satyrn-ai).

## Start here

- [Weekend co-development: background and setup](https://hackmd.io/@pauleveritt/HJJhQzsSfg)
- [How I Use SDD](https://hackmd.io/@pauleveritt/SkNzlMoHMg)
- [`docs/superpowers/roadmap.md`](docs/superpowers/roadmap.md) — historical context and current-worktree pointers
- [`DATASET_METHODOLOGY.md`](DATASET_METHODOLOGY.md)
- [Superseded dataset workflow spec](docs/superpowers/specs/2026-07-30-dataset-workflow-design.md)

## Setup

1. Fork this repository.
2. Clone your fork.
3. Install Python 3.14+, [`uv`](https://docs.astral.sh/uv/), and `pytest`.
4. Make the Hugging Face CLI (`hf`) available.
5. Set up [Superpowers](https://github.com/obra/superpowers) for your agent.

From the repository checkout:

```bash
uv sync
```

Ruff, Pyrefly, and [RTK](https://github.com/rtk-ai/rtk) are useful optional
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
current worktree and next cycle, and follow its required pre-reading. On
`main`, the roadmap is a signpost to the active worktrees; use the active
worktree's roadmap to group cycles into phases, track backlog research, and
record completed or discarded work.

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

## The original scripts

The current checkout still contains the original `make_data.py`, `main.py`, and
`eval.py` placeholders. They are historical seed material, not evidence that
the training pipeline works and not the project plan. Follow the roadmap and
the rebuild worktree for current development.
