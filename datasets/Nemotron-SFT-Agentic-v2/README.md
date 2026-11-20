# Nemotron-SFT-Agentic-v2 (Search Subset)

- **Source:** [nvidia/Nemotron-SFT-Agentic-v2](https://huggingface.co/datasets/nvidia/Nemotron-SFT-Agentic-v2) (`data/search.jsonl` split)
- **Original license:** CC-BY-4.0, Apache-2.0, MIT (commercial use permitted)
- **Derived file:** `sft-search-programming.jsonl` — 112 programming/CS rows (≤ 16,384 tokens) filtered from `search.jsonl`.

Each `web-search` tool response was trimmed from 10 results down to the top 3 using `all-mpnet-base-v2` cosine similarity against the following assistant turn's reasoning and response.
