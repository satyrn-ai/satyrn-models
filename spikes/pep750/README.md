# PEP 750 spike (historical)

The original attempt at fine-tuning a small model on PEP 750
[template strings](https://peps.python.org/pep-0750/) (t-strings). **Superseded
by [`spikes/tstrings/`](../tstrings/README.md)**, which replaced this spike's
evaluation harness and corpus pipeline after finding the defects described
below. Kept here for its original scripts and as the record of what the
newer spike had to fix.

## Known wrong — read this before trusting any number these scripts produce

`DATASET_METHODOLOGY.md` documents two verified defects in this spike's own
evaluation:

1. **Contaminated eval.** 7 of `eval.py`'s 10 built-in prompts are
   byte-identical to `make_data.py`'s training descriptions — any pass rate
   `eval.py` reports is a memorization score, not a learning score.
2. **Blind oracle.** `make_data.py`/`eval.py` validated a candidate by
   executing it and checking it didn't raise. An f-string answering a
   t-string task passes; so does `pass`.

Both are why `spikes/tstrings/` exists with a real verification oracle
(`oracle/verify.py`) and an independently-authored benchmark (`ood-v2`)
instead of reusing this spike's eval.

## What's here

| path | what it is |
| --- | --- |
| `make_data.py` | Generates PEP 750 training examples; each is executed on the current interpreter and only kept if it runs cleanly (see defect 2 above — "runs cleanly" is not "is correct"). |
| `main.py` | Fine-tunes Qwen2.5-Coder-7B on the generated data with MLX LoRA. |
| `eval.py` | Runs the (contaminated) built-in eval prompts against a fine-tuned model. |
| `data/pep750.jsonl` | The generated training data from `make_data.py`. |
| `src/satyrn_model/quarantine.py`, `scripts/quarantine_legacy_examples.py`, `corpus/quarantine/` | A later, unrelated addition: 24 hand-written legacy examples preserved as inert, permanently-`"unverified"` records. They cannot become a corpus row or benchmark task — see the module docstring. Not part of the original spike; kept here because this is where they were added. |
| `docs/superpowers/` | The original SDD roadmap, specs, and research notes for this spike, left as historical record. |

## Stack

- **Base model:** `Qwen/Qwen2.5-Coder-7B` (hardcoded in `main.py`) — chosen
  because it predates PEP 750's acceptance, small enough to fine-tune
  locally, and fast/cheap to iterate on. A proving ground, not the intended
  long-term model — `spikes/tstrings/` later targeted a different, unrelated
  model (Mellum2-12B-A2.5B) with its own harness; nothing here carries over.
- **Fine-tuning:** [Unsloth](https://github.com/unslothai/unsloth) +
  `unsloth_zoo.mlx.trainer` (`MLXTrainer`/`MLXTrainingConfig`) — LoRA on
  Apple's MLX backend, so training runs on-device rather than needing CUDA.
- **Data:** Hugging Face `datasets`, with a Python 3.14 compatibility shim in
  `main.py`/`eval.py` for a `datasets` 4.x/`dill` incompatibility (3.14 changed
  `pickle._Pickler._batch_setitems`'s signature; the shim patches around it —
  see the comment block at the top of either file).
- **Environment:** `uv` + `hatchling`, Python 3.14+ required for t-strings
  themselves, independent of `spikes/tstrings/`'s own environment.

## Methodology

The full literature review and reasoning live in `DATASET_METHODOLOGY.md`
(342 lines) — this is the short version. Three things mattered most, in
order: **fix the eval** (it was measuring memorization, not learning — see
"Known wrong" above), **invert the data pipeline** (generate candidates at
volume and let the interpreter reject them, instead of hand-writing 24
examples), and **re-audit the base model** (a newer base may already
half-know PEP 750, turning knowledge injection into the much easier problem
of reinforcement).

The literature review's central finding: post-cutoff API knowledge is hard to
inject by fine-tuning, and the evidence at the time argued *against*
fine-tuning more than for it — base-model-plus-documentation-in-context
reached 66% executable on a comparable task in one cited paper, against only
negative published fine-tuning results. That's why the doc states an explicit
decision criterion rather than assuming fine-tuning wins by default:

> The fine-tuned model must beat base-model-plus-docs-in-context on the
> held-out eval. If it doesn't, the right answer is a docs/retrieval layer.

`spikes/tstrings/README.md` answers this question with real numbers on a
different base model (Mellum2): documentation-in-prompt beats the adapter,
not the other way around — consistent with what this document predicted
before any of that training happened.

A stdlib-only sourcing rule also came out of this doc the hard way: an
earlier revision spent most of a build cycle mining `tdom` (a third-party
template library) before catching that it teaches the model *tdom's* API
surface, not the PEP 750 language feature itself. See "Ground truth worth
mining" §1 in `DATASET_METHODOLOGY.md` for the full account — it's kept as
the record of that mistake, not as current guidance to follow.

## Running it

```bash
uv sync
uv run python make_data.py          # generate data/pep750.jsonl
uv run python main.py               # fine-tune (requires the HF CLI, a downloaded base model)
uv run python eval.py               # run the eval — contaminated, see above
uv run pytest                       # the quarantine package's own tests (18 passing)
```

Python 3.14+ required (t-strings are a 3.14 feature). There is no relationship
between this spike's Python/dependency setup and `spikes/tstrings/`'s — each
spike owns its own environment.
