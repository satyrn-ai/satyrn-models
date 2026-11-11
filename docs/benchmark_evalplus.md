# Model benchmarking

Use the `satyrn-benchmark` package to benchmark a model with
[evalplus](https://github.com/evalplus/evalplus) (HumanEval+ and MBPP+) on a cloud GPU.

Given a Hugging Face repo of raw safetensors weights, the pipeline:

1. starts the [Ollama](https://ollama.com) server if it isn't running,
2. downloads the checkpoint and converts it to GGUF with llama.cpp,
3. registers the GGUF file as an Ollama model,
4. runs each configured evalplus dataset against it,
5. writes logs, samples, scores and a summary under `results/evalplus/`.

## Prerequisites

[Ollama](https://ollama.com/download) has to be installed on the machine before running the benchmark;
the tool starts the server but never installs it.

## Run it

Install the package on the GPU machine and call the CLI:

```sh
pip install -e ./benchmark
satyrn-benchmark --hf-ref hf.co/JetBrains/Mellum2-12B-A2.5B-Instruct
```

The llama.cpp toolchain is installed on the first run. For back-to-back runs on
the same machine, pass `--no-install-deps` to skip that step:

```sh
satyrn-benchmark --hf-ref hf.co/google/gemma-4-26B-A4B-it --no-install-deps
```

## pass@k

The default run is greedy, which evalplus scores as pass@1. To sample instead, pass a
positive `--temperature` together with `--no-greedy` and `--nsamples`.

```sh
pip install -e ./benchmark
satyrn-benchmark --hf-ref hf.co/Qwen/Qwen3.6-27B --temperature=0.8 --no-greedy --nsamples=10
```

## Output

Under `results_dir` (default `results/evalplus/`):

- `<dataset>/<model>_openai_temp_0.0.jsonl` — the generated samples
- `<dataset>/<model>_openai_temp_0.0_eval_results.json` — per-problem scores
- `logs/<model>_<dataset>.log` — the full evalplus output, including `pass@k`
- `<model>_summary.txt` — status, result paths and `pass@k` for every dataset
