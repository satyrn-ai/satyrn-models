# Datasets

This table records the methodology used to generate each dataset: model and prompt revision.

| File                   | Rows | Tokens | Completion[^1] | Generator         | Notes                                                                                                                                        |
|------------------------|------|--------|----------------|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `python3.14/cpt.jsonl` | 143  | 430k   | 430k   | -                 | Based on CPython documentation - only sections changed with this Python version were extracted.                                              |
| `python3.15/cpt.jsonl` | 154  | 650k   | 650k   | -                 | As above.                                                                                                                                    |
| `python3.14/sft.jsonl` | 1537 | 700k   | 650k   | deepseek-v4-flash | Using code from [PR #19](https://github.com/satyrn-ai/satyrn-models/pull/19), which improves the `trace` field holding the model's reasoning. |
| `python3.15/sft.jsonl` | 1511 | 800k   | 750k   | deepseek-v4-pro   | **DEPRECATED**. The `trace` field describes the example, not reasoning in the first person.                                                 |
| `python3.15/sft2.jsonl` | 1902 | 1.8M  | 1.7M   | deepseek-v4-flash | -                                                                                                                                            |
| `python3.14/sft3.jsonl` | 1650 | 830k  | 770k   | deepseek-v4-flash | Combined `python3.14/sft.jsonl` + `python3.14/sft-PEP750.jsonl` with reasoning traces rewritten to 80–200 words grounded in reference docs, no prose bloat. |
| `python3.15/sft3.jsonl` | 3413 | 2.4M  | 2.2M   | deepseek-v4-flash, deepseek-v4-pro | Combined `python3.15/sft.jsonl` + `python3.15/sft2.jsonl` with reasoning traces rewritten as above. |
| `python3.14/sft-agentic.jsonl` | 696 | 3.2M | 1.8M | deepseek-v4-flash, deepseek-v4-pro | Using code from [PR #79](https://github.com/satyrn-ai/satyrn-models/pull/79). Tasks written by deepseek-v4-flash and solved by deepseek-v4-pro in the Pi coding agent. C API topics skipped. Rows over 16k tokens or 20 tool calls were removed. |
| `python3.15/sft-agentic.jsonl` | 873 | 3.8M | 2.0M | deepseek-v4-flash, deepseek-v4-pro | As above. |

[^1]: Tokens the model learns from, counted with the Qwen3.8 tokenizer (`add_special_tokens=False`). They exclude the prompts and tool results.
