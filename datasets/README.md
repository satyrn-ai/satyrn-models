# Datasets

This table records the methodology used to generate each dataset: model and prompt revision.

| File                   | Rows | Tokens[^1] | Generator         | Notes                                                                                                                                        |
|------------------------|------|------------|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `python3.14/cpt.jsonl` | 143  | 430k   | -                 | Based on CPython documentation - only sections changed with this Python version were extracted.                                              |
| `python3.15/cpt.jsonl` | 154  | 650k   | -                 | As above.                                                                                                                                    |
| `python3.14/sft.jsonl` | 1537 | 650k   | deepseek-v4-flash | Using code from [PR #19](https://github.com/satyrn-ai/satyrn-models/pull/19), which improves the `trace` field holding the model's reasoning. |
| `python3.15/sft.jsonl` | 1511 | 750k   | deepseek-v4-pro   |                                                                                                                                              |
| `python3.15/sft2.jsonl` | 1902 | 1.7M   | deepseek-v4-flash |                                                                                                                                             |
| `python3.14/sft-agentic.jsonl` | 696 | 1.8M | deepseek-v4-flash, deepseek-v4-pro | Using code from [PR #79](https://github.com/satyrn-ai/satyrn-models/pull/79). Tasks written by deepseek-v4-flash and solved by deepseek-v4-pro in the Pi coding agent. C API topics skipped. Rows over 16k tokens or 20 tool calls were removed. |
| `python3.15/sft-agentic.jsonl` | 873 | 2.0M | deepseek-v4-flash, deepseek-v4-pro | As above. |
| `cpt/web.jsonl` | 1679 | 3.4M | - | Curated Python and Markdown files from web GitHub repositories. |
| `cpt/datasci.jsonl` | 1237 | 3.3M | - | Curated Python and Markdown files from data science GitHub repositories. |
| `cpt/misc.jsonl` | 598 | 2.5M | - | Curated Python and Markdown files from CLI, testing, and CPython stdlib repositories. |

[^1]: Tokens the model learns from, counted with the Qwen3.8 tokenizer. They exclude the prompts and tool results.
