# Satyrn Model Labbook

## Agentic SFT experiments

### Adding CPT to agentic SFT training

2026-11-23 · @postrational

Added a gentle 1-epoch CPT stage (Python docs plus curated `web` and `misc` repos) at reduced learning rates before SFT, compared against SFT-only baselines.

| Run | CPT epochs | CPT LR | Post-CPT HE | Post-SFT HE | Post-SFT PE | Satyrn Score |
|---|---:|---:|---:|---:|---:|---:|
| **Qwen3.8-27B** | | | | | | |
| SFT-only (`5c78fa40`) | -- | -- | -- | 91.5% | **72.4%** | **78.8%** |
| CPT+SFT (`46cd5d05`) | 3 | 1e-4 | 95.1% | 93.3% | 64.1% | 73.8% |
| CPT+SFT (`8cc300d7`) | 1 | 5e-5 | **97.0%** | **95.1%** | **70.1%** | **78.5%** |
| **Mellum2.1-12B-A2.5B-Thinking** | | | | | | |
| SFT-only (`c75f1e67`) | -- | -- | -- | 76.2% | **60.7%** | **65.9%** |
| CPT+SFT (`ac4e4071`) | 3 | 1e-4 | 29.9% | 71.3% | 48.1% | 55.9% |
| CPT+SFT (`a749e970`) | 2 | 1e-4 | 57.9% | 78.0% | 44.3% | 55.6% |
| CPT+SFT (`026b0f3b`) | 1 | 3e-5 | **87.2%** | **84.1%** | **58.3%** | **66.9%** |

- Multi-epoch CPT at `1e-4` caused a severe post-CPT HumanEval crash on Mellum (`29.9%` at `3` epochs, `57.9%` at `2` epochs), which SFT never fully recovered from.
- Cutting CPT to `1` epoch at lower learning rates prevented Mellum's post-CPT HumanEval collapse.
- Gentle CPT lifted post-SFT HumanEval, adding `7.9` points on Mellum and slightly improving Qwen.
- Post-SFT PythonEval slipped slightly on both models relative to SFT-only.
- Overall Satyrn Score improved slightly on Mellum (`66.9%`) and matched SFT-only on Qwen.

## Future ideas

### Training dataset improvements

- Add SFT examples showing module-level `lazy import` (and `exec` in a namespace when wrapped in a function) for `PEP810`, since `lazy import` inside `def` raises `SyntaxError`.
- Generate additional SFT and agentic-SFT examples from Python 3.14's final `concurrent.interpreters` documentation to address `PEP734` API errors.

### Evaluation improvements

- Update `4` `PEP649` PythonEval prompts that ask for `"the new standard library annotations module"` instead of `annotationlib` (causing `ModuleNotFoundError: No module named 'annotations'`).
