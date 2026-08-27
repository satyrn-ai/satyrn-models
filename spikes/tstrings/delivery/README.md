# Michał-format t-string dataset (delivery)

`delivery/sft.jsonl` — **589 rows** in the exact schema of
`datasets/python3.14/sft.jsonl`, generated from the clean-room t-strings corpus.

## Files

- `sft.jsonl` — 589 delivered rows.
- `manifest.json` — row count, train/valid split by `semantic_id`, input
  fingerprints, pinned source repos, model.
- `_checkpoint.jsonl` — transient resume state (gitignored).

## Schema

Matches Michał's 8 keys exactly: `prompt` (user-only), `completion` (prose +
fenced code), `filename`, `python_version`, `idea`, `code`, `trace`,
`expected_output`.

## How it was generated

`deliver` (`../src/satyrn/tstrings/deliver.py`) wraps the deterministic corpus
with LLM prose: per row it generates a first-person reasoning `trace`, then a
natural `prompt` question + `explanation` (deepseek-v4-flash, thinking mode).
The `code` is never altered — it is mined from real source and gated.

## Comparison vs the existing t-string rows in `datasets/python3.14/sft.jsonl`

| | This dataset | Existing t-string rows |
|---|---|---|
| Rows | 589 | ~76 of 1537 |
| Code origin | mined from 7 real repos | LLM-generated from PEP docs |
| Provenance | tdom 229, t-sql 136, storyville 85, cpython 53, pep750-examples 46, tdom-svcs 22, regex-template 18 | PEP750.rst, lexical_analysis.rst, token.rst, ast.rst, templatelib.rst |
| Verification | anti-vacuity gate (wrong solutions must fail) | output-match only |
| Code style | short/idiomatic (median ~107 chars) | teaching-style (median ~359, asserts) |
| Trace | median ~815 chars | median ~884 chars |

**Pros (ours):** real usage provenance; anti-vacuity guarantee; 7.75× volume
with 7-source diversity and enforced composition floors; idiomatic code.

**Cons (ours):** `idea`/`prompt` are generic — the corpus's prompt families
produce ~35 distinct ideas, and the top six "build a Template" variants cover
~90% of rows — so they under-describe the code's domain; volume depends on a
finite mined pool plus third-party repos.

**Pros (existing):** `idea`/`prompt`/`code` are mutually consistent (code is
generated *from* the idea); self-contained single pipeline; scales arbitrarily.

**Cons (existing):** synthetic code; output-match verification passes vacuous
programs; only ~76 t-string rows; no real-source provenance.

## Caveats

1. **Generic ideas.** `idea` is carried over verbatim from the corpus's prompt
   families, so it reads "build a Template" even when the mined `code` is a
   domain-specific usage (SQL/HTML/DOM). The generated question is anchored to
   the idea, so rows are internally consistent, but the prompt under-describes
   the code's domain.
2. **Prose is LLM-generated** (deepseek-v4-flash). Treat as reviewable output,
   not a hand-checked canonical artifact.

## Regenerate

```sh
uv run satyrn-tstrings deliver --workers 16   # resumable; add --fresh to restart
```
