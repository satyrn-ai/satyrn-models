import dataclasses
import logging
import os
import sys
from pathlib import Path

import click

from satyrn.benchmark import evaluate, model, ollama
from satyrn.benchmark.config import DATASETS, MODELS, BenchmarkConfig, EvalplusConfig

logger = logging.getLogger(__name__)


def run_benchmark(cfg: BenchmarkConfig) -> Path:
    """Benchmark the configured model with evalplus and return the summary path.

    Converts the Hugging Face checkpoint to GGUF, registers it with a local
    Ollama server, runs each configured evalplus dataset against it, and writes
    logs, samples, scores and a summary under the configured results directory.
    """
    # Configured here, not at import time, so the notebook cell captures the log.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger.info("Config: %s", cfg)

    # Ollama ignores the key, but evalplus's OpenAI client demands a non-empty one.
    os.environ.setdefault("OPENAI_API_KEY", "ollama")

    ollama.ensure_server(cfg.install_deps)

    repo = model.format_repo_id(cfg.model.hf_ref)
    outtype = cfg.model.gguf_outtype or model.detect_outtype(repo)
    model_name = f"local/{model.extract_model_name(repo)}:{outtype}"
    gguf_path = model.build_gguf(repo, outtype, Path(cfg.work_dir), cfg.install_deps)
    ollama.create_model(model_name, gguf_path)

    results = {dataset: evaluate.run_dataset(model_name, dataset, cfg) for dataset in cfg.evalplus.datasets}
    failed = [dataset for dataset, (returncode, _) in results.items() if returncode != 0]
    if failed:
        logger.warning("evalplus failed for: %s (see the logs above)", ", ".join(failed))

    summary_path = evaluate.write_summary(model_name, results, cfg)
    logger.info("Done.\n%s", summary_path.read_text())
    logger.info("Summary written to %s", summary_path.resolve())
    return summary_path


@click.command("satyrn-benchmark")
@click.option(
    "--model",
    "model_name",
    type=click.Choice(sorted(MODELS)),
    required=True,
    help="Which of the packaged models to benchmark.",
)
@click.option(
    "--gguf-outtype",
    help="GGUF precision: f32 | f16 | bf16 | q8_0 | tq1_0 | tq2_0. Defaults to the checkpoint's own.",
)
@click.option(
    "--dataset",
    "datasets",
    type=click.Choice(DATASETS),
    multiple=True,
    default=EvalplusConfig.datasets,
    show_default=True,
    help="evalplus dataset to run. Repeat to run several.",
)
@click.option(
    "--results-dir",
    default=BenchmarkConfig.results_dir,
    show_default=True,
    help="Where logs, samples, scores and the summary are written.",
)
@click.option(
    "--work-dir",
    default=BenchmarkConfig.work_dir,
    show_default=True,
    help="Scratch directory for the downloaded checkpoint and the GGUF conversion.",
)
@click.option(
    "--greedy/--no-greedy",
    default=EvalplusConfig.greedy,
    show_default=True,
    help="Sample greedily, which is what pass@1 expects.",
)
@click.option(
    "--install-deps/--no-install-deps",
    default=BenchmarkConfig.install_deps,
    show_default=True,
    help="Install Ollama and the llama.cpp toolchain if missing. Turn off for back-to-back runs.",
)
def main(
    model_name: str,
    gguf_outtype: str | None,
    datasets: tuple[str, ...],
    results_dir: str,
    work_dir: str,
    greedy: bool,
    install_deps: bool,
) -> None:
    """Benchmark a Hugging Face model with evalplus, served by Ollama on the same machine."""
    model_config = MODELS[model_name]
    if gguf_outtype:
        model_config = dataclasses.replace(model_config, gguf_outtype=gguf_outtype)
    cfg = BenchmarkConfig(
        model=model_config,
        results_dir=results_dir,
        work_dir=work_dir,
        install_deps=install_deps,
        evalplus=EvalplusConfig(datasets=datasets, greedy=greedy),
    )
    run_benchmark(cfg)
