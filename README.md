# satyrn-model

Produce versioned training datasets for teaching models Python 3.14 template
strings (t-strings).

---

## Current work: building a corpus that can actually teach t-strings

> The scripts documented further down are **placeholders awaiting retirement**
> by SP0 R1. They are described here for the moment because they are still what
> the repo contains — not because they are the plan.

### What this is

A data project that manufactures verified, reproducible training datasets for
one language feature: Python 3.14 t-strings. It uses the verification,
contamination, benchmark, training, and evaluation provider being rebuilt on
`worktree-tstrings-rebuild`; it does not implement those systems itself.

This worktree owns source manifests, t-string seed extraction, CPython/PEP
source-derived rows, authored seeds, properties, patterns, generated rows,
data-quality reports, and immutable 500/2k/5k dataset snapshots. It stops at
the dataset boundary. Model training,
benchmark scoring, memorization measurement, and the fine-tune-vs-retrieval
verdict belong to the provider effort.

It has a useful independent first milestone: **collection**. SP5 can pin and
license sources, extract safe t-string candidates, retain multi-origin seed
provenance, measure coverage, and author seeds without the provider. Those
artifacts are explicitly unqualified input—not final rows or publishable
snapshots—until provider rendering, execution, qualification, and contamination
checks are available.

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
