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
