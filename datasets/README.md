# Datasets

This table records the methodology used to generate each dataset: model and
prompt revision.

| File                          | Generator         | Notes                                                                                                                                        |
|-------------------------------|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `python3.14/cpt.jsonl`        | -                 | Based on CPython documentation - only sections changed with this Python version were extracted.                                              |
| `python3.15/cpt.jsonl`        | -                 | As above.                                                                                                                                    |
| `python3.14/sft.jsonl`        | deepseek-v4-flash | Using code from [PR #19](https://github.com/satyrn-ai/satyrn-models/pull/19), which improves the `trace` field holding the model's reasoning. |
| `python3.15/sft.jsonl`        | deepseek-v4-pro   |                                                                                                                                              |
| `python3.14/sft-PEP750.jsonl` | deepseek-v4-flash | Covers PEP 750 t-strings. Using code from [PR #25](https://github.com/satyrn-ai/satyrn-models/pull/25), whose prompt names the older idiom each feature replaces. |
