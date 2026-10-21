# Datasets

This table records the methodology used to generate each dataset: model and prompt revision.

| File                   | Rows | Generator         | Notes                                                                                                                                        |
|------------------------|------|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `python3.14/cpt.jsonl` | 143  | -                 | Based on CPython documentation - only sections changed with this Python version were extracted.                                              |
| `python3.15/cpt.jsonl` | 154  | -                 | As above.                                                                                                                                    |
| `python3.14/sft.jsonl` | 1537 | deepseek-v4-flash | Using code from [PR #19](https://github.com/satyrn-ai/satyrn-models/pull/19), which improves the `trace` field holding the model's reasoning. |
| `python3.15/sft.jsonl` | 1511 | deepseek-v4-pro   |                                                                                                                                              |
| `agentic/qwen3.8-27b-base-sessions.jsonl` | 16 | Qwen3.8-27B (base, MLX 8-bit) under the Pi 1.0.2 coding agent | Multi-turn tool-use sessions that passed hidden tests in satyrn-evals (2026-10-10, commit `743ac13`). Prompt/completion rows with `tools`; 5.5k–31k tokens each. Best used as a held-out agentic eval; see [findings](../docs/findings/2026-10-11-qwen3.8-py3.15-agentic.md). |
