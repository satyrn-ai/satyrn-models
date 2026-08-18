# Model benchmarking

Use the `satyrn-benchmark` package to benchmark a model with
[evalplus](https://github.com/evalplus/evalplus) (HumanEval+ and MBPP+) on a cloud GPU.

Given a Hugging Face repo of raw safetensors weights, the pipeline:

1. installs and starts an [Ollama](https://ollama.com) server,
2. downloads the checkpoint and converts it to GGUF with llama.cpp,
3. registers the GGUF file as an Ollama model,
4. runs each configured evalplus dataset against it,
5. writes logs, samples, scores and a summary under `results/evalplus/`.

## Run it on molab

1. **Create the notebook.** On [molab](https://molab.marimo.io/notebooks), use the **new notebook**
   dropdown and paste the notebook's GitHub URL:
   `https://github.com/pyrsuit/satyrn-models/blob/$SATYRN_REF/benchmark/notebooks/evalplus.py`
2. **Attach a GPU**. The default is 4 CPUs and
   32 GB RAM with no GPU; pick the GPU is an NVIDIA RTX Pro 6000 Blackwell (96 GB VRAM).
3. **Set `SATYRN_REF` in the notebook.**
4. **Run both cells.**
5. **Collect the results** from the **file sidebar** under `results/evalplus/`.

## Change what gets benchmarked

Configs are composed by Hydra and live inside the package, at
`benchmark/src/satyrn/benchmark/configs/`:

| Experiment | Model |
| --- | --- |
| `experiment/mellum2-humaneval-mbpp` | `hf.co/JetBrains/Mellum2-12B-A2.5B-Instruct` |
| `experiment/qwen3.6-humaneval-mbpp` | `hf.co/Qwen/Qwen3.6-27B` |
| `experiment/gemma-4-humaneval-mbpp` | `hf.co/google/gemma-4-26B-A4B-it` |

## Output

Under `results_dir` (default `results/evalplus/`):

- `<dataset>/<model>_openai_temp_0.0.jsonl` — the generated samples
- `<dataset>/<model>_openai_temp_0.0_eval_results.json` — per-problem scores
- `logs/<model>_<dataset>.log` — the full evalplus output, including `pass@k`
- `<model>_summary.txt` — status, result paths and `pass@k` for every dataset
