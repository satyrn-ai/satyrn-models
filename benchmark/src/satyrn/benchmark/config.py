import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import MISSING, OmegaConf

logger = logging.getLogger(__name__)

# The configs ship inside the package because molab installs it straight from
# git and never sees the repository checkout.
CONFIG_DIR = Path(__file__).resolve().parent / "configs"


@dataclass
class ModelConfig:
    hf_ref: str = MISSING
    # None matches the checkpoint's native precision. Override with
    # f32 | f16 | bf16 | q8_0 (quantized) | tq1_0 | tq2_0.
    gguf_outtype: str | None = None


@dataclass
class EvalplusConfig:
    datasets: list[str] = MISSING
    greedy: bool = MISSING
    backend: str = MISSING
    base_url: str = MISSING


@dataclass
class BenchmarkConfig:
    results_dir: str = MISSING
    work_dir: str = MISSING
    model: ModelConfig = field(default_factory=ModelConfig)
    evalplus: EvalplusConfig = field(default_factory=EvalplusConfig)


def load_config(config_name: str, overrides: list[str] | None = None) -> BenchmarkConfig:
    """Compose `config_name` from the packaged configs and type-check it.

    Merging against the structured schema rejects unknown keys, missing values
    and wrong types.
    """
    with initialize_config_dir(config_dir=str(CONFIG_DIR), job_name="satyrn-benchmark"):
        cfg = compose(config_name=config_name, overrides=overrides or [])
    cfg = OmegaConf.merge(OmegaConf.structured(BenchmarkConfig), cfg)
    logger.info("Config:\n%s", OmegaConf.to_yaml(cfg))
    return cast(BenchmarkConfig, OmegaConf.to_object(cfg))
