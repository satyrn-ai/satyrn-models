import logging
import subprocess
from pathlib import Path

from satyrn.benchmark.config import BenchmarkConfig

logger = logging.getLogger(__name__)


def build_command(model_name: str, dataset: str, cfg: BenchmarkConfig) -> list[str]:
    command = [
        "evalplus.evaluate",
        "--model",
        model_name,
        "--dataset",
        dataset,
        "--backend",
        cfg.evalplus.backend,
        "--base_url",
        cfg.evalplus.base_url,
        "--root",
        cfg.results_dir,
        "--n_samples",
        str(cfg.evalplus.nsamples),
        "--temperature",
        str(cfg.evalplus.temperature),
    ]
    if cfg.evalplus.greedy:
        command.append("--greedy")
    return command


def run_dataset(model_name: str, dataset: str, cfg: BenchmarkConfig) -> tuple[int, Path]:
    """Run one evalplus dataset, teeing its output to a log file."""
    log_dir = Path(cfg.results_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{model_name}_{dataset}.log".replace("/", "--")

    command = build_command(model_name, dataset, cfg)
    logger.info("[%s] running: %s (logging to %s)", dataset, " ".join(command), log_path)
    with log_path.open("w") as log_file:
        completed = subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, check=False)

    status = "OK" if completed.returncode == 0 else f"FAILED (exit {completed.returncode})"
    logger.info("[%s] %s -- see %s", dataset, status, log_path)
    return completed.returncode, log_path


def result_paths(model_name: str, dataset: str, cfg: BenchmarkConfig) -> list[Path]:
    """The sample and score files evalplus writes for a run.

    Named after the model, backend and temperature, with "/" replaced by "--".
    """
    identifier = f"{model_name.strip('./').replace('/', '--')}_{cfg.evalplus.backend}_temp_{cfg.evalplus.temperature}"
    dataset_dir = Path(cfg.results_dir) / dataset
    return [dataset_dir / f"{identifier}.jsonl", dataset_dir / f"{identifier}_eval_results.json"]


def pass_at_k_lines(log_path: Path) -> list[str]:
    """The pass@k scores evalplus printed, pulled back out of its log."""
    if not log_path.is_file():
        return []
    with log_path.open(errors="ignore") as log_file:
        return [line.strip() for line in log_file if "pass@" in line]


def write_summary(model_name: str, results: dict[str, tuple[int, Path]], cfg: BenchmarkConfig) -> Path:
    """Collect per-dataset status, result paths and scores into one summary file."""
    lines = [f"Model: {model_name}"]
    for dataset, (returncode, log_path) in results.items():
        status = "OK" if returncode == 0 else f"FAILED (exit {returncode})"
        lines.append(f"  Dataset: {dataset} [{status}]")
        lines += [
            f"    - {path} ({'found' if path.is_file() else 'missing'})"
            for path in result_paths(model_name, dataset, cfg)
        ]
        lines += [f"    {line}" for line in pass_at_k_lines(log_path)]

    summary_path = Path(cfg.results_dir) / f"{model_name.replace('/', '--')}_summary.txt"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n")
    return summary_path
