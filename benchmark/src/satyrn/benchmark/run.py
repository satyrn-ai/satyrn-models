import logging
import os
import sys
from pathlib import Path

import click

from satyrn.benchmark import evaluate, model, ollama
from satyrn.benchmark.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_NAME = "experiment/mellum2-humaneval-mbpp"


def run_benchmark(config_name: str = DEFAULT_CONFIG_NAME, overrides: list[str] | None = None) -> Path:
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
    cfg = load_config(config_name, overrides)

    # Ollama ignores the key, but evalplus's OpenAI client demands a non-empty one.
    os.environ.setdefault("OPENAI_API_KEY", "ollama")

    ollama.ensure_server()

    repo = model.repo_id(cfg.model.hf_ref)
    outtype = cfg.model.gguf_outtype or model.detect_outtype(repo)
    model_name = f"local/{model.model_slug(repo)}:{outtype}"
    gguf_path = model.build_gguf(repo, outtype, Path(cfg.work_dir))
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
    "--config-name",
    default=DEFAULT_CONFIG_NAME,
    show_default=True,
    help="Config to compose from the packaged configs.",
)
@click.argument("overrides", nargs=-1)
def main(config_name: str, overrides: tuple[str, ...]) -> None:
    """Benchmark a Hugging Face model with evalplus, served by Ollama on the same machine.

    OVERRIDES are Hydra overrides, e.g. "evalplus.datasets=[humaneval]" "model.gguf_outtype=q8_0".
    """
    run_benchmark(config_name, list(overrides))
