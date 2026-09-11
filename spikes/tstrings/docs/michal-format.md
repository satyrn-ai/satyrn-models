# Corpus in Michał's SFT format

`to-michal` (Phase 9) converts the frozen `corpus-sft/` into rows Michał's
`corpus_builder`/`trainer` stack consumes directly. The mapping is 1:1 with the
converged schema; two content caveats are documented below.

## Field mapping

| Michał's field | Source |
|---|---|
| `prompt` | `[{"role": "user", "content": <idea>}]` — optionally prefixed by the deployment system prompt (`--system-prompt`, aligning with PR #24) |
| `completion` | `[{"role": "assistant", "content": "```python\n<code>\n```"}]` |
| `filename` | `filename` |
| `python_version` | `"3.14"` |
| `idea` | `idea` |
| `code` | `code` |
| `trace` | `trace` |
| `expected_output` | `expected_output` |

Internal fields (`_line`, `semantic_id`) are dropped.

## Caveats (not silently filled)

1. **No `explanation` preamble.** Michał's `completion` is
   `"<explanation>\n\n```python\n<code>\n```"`; ours is the fenced code alone.
   We don't generate an explanation (ground rule 2.1 forbids LLM content in the
   corpus), so this gap is explicit.
2. **`trace` is mock.** The corpus was frozen with a deterministic mock trace
   pending a live `DEEPSEEK_API_KEY` re-freeze. A live re-freeze produces real
   first-person reasoning traces.

## Usage

```sh
uv run satyrn-tstrings to-michal -i corpus-sft -o datasets/tstrings-sft.jsonl
uv run satyrn-tstrings to-michal -i corpus-sft -o datasets/tstrings-sft.jsonl --system-prompt
```
