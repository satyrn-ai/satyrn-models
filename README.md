# satyrn-model

Fine-tune Qwen2.5-Coder-7B on PEP 750 template strings (t-strings) using
MLX LoRA on Apple Silicon.

---

## Current work: building a corpus that can actually teach t-strings

> The scripts documented further down are **placeholders awaiting retirement**
> by SP0 R1. They are described here for the moment because they are still what
> the repo contains — not because they are the plan.

### What this is

A pipeline that manufactures verified training examples for a language feature
the model has never seen, and the measurement apparatus to tell whether the
training worked. Two designs govern it:

- [Seed-and-pattern corpus design](docs/superpowers/specs/2026-07-31-seed-and-pattern-corpus-design.md)
  — the primary corpus source.
- [Dataset workflow spec](docs/superpowers/specs/2026-07-30-dataset-workflow-design.md)
  — the surrounding measure → harvest → synthesize sequence.

The [roadmap](docs/superpowers/roadmap.md) sequences the work; the
[spike findings](docs/superpowers/research/2026-07-31-spike-findings.md) record
what a throwaway build already established, and should be read before designing
any rung.

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

**Seeds × patterns, with ground truth from execution.** Real t-string literals
are extracted from open-source projects and hand-authored to fill gaps. Reviewed
*pattern* functions multiply those seeds into exercises. Every expected value is
computed by **running the template on the pinned interpreter** — never produced
by a model.

This inverts the human's role from gate to source. Review effort would scale
with output volume; seeding effort scales only with the diversity needed, and
each seed multiplies across every pattern.

Four properties make a large auto-accept path defensible:

1. **No model in the loop.** Patterns are drafted in conversation but land as
   reviewed source code. Generation is deterministic and offline.
2. **Bad states made unrepresentable where possible.** A prompt, its reference
   solution, and its hidden test are all projections of one intent, so they
   cannot describe different questions. Assertions may reference the candidate's
   output on only one side, so a test cannot compare two candidate-produced
   values and thereby encode no expected answer.
3. **Gates carry adversarial tests.** Where a gate is unavoidable — proving a
   hidden test can actually discriminate a real solution from a fake one — a
   planted defect must be demonstrated failing in a live run. Eight are
   specified, four aimed at the gates themselves, because gates are where this
   bug class re-hosts.
4. **Diversity is measured, not assumed.** 200 seeds × 30 patterns is not 6000
   independent examples. Effective diversity is tracked by structural
   fingerprinting, and the scale sweep plots held-out score against *that*
   rather than against row count.

**Third-party code is a seed source, not an example source.** A literal like
`t"<div class={cls}>{body}</div>"` is 100% stdlib; only the library assertions
around it are not. Literals are extracted and rebuilt into stdlib-only
exercises, which is also what supplies domain diversity — SQL, HTML, logging,
regex, and structured-data literals are shaped nothing alike, and that variety
is the structural counter to correlated output.

A known limitation is recorded rather than papered over: execution-derived
ground truth only defines tasks whose answers are mechanically checkable, and
the current benchmark is drawn from that same restricted distribution. A
separate benchmark sub-project adds naturalistic completion tasks — authored
before any pattern exists, so they cannot be shaped to fit what the corpus finds
easy.

---

## Pipeline

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
