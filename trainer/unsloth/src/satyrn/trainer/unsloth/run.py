"""Entry point for the satyrn-unsloth trainer CLI."""

from pathlib import Path

import hydra
from omegaconf import DictConfig

from satyrn.trainer.unsloth.config import validate_config

CONFIG_DIR = str(Path(__file__).resolve().parents[4] / "configs")


@hydra.main(config_path=CONFIG_DIR)
def main(cfg: DictConfig) -> None:
    if not cfg:
        print("Usage: satyrn-unsloth --config-name experiment/<name>")
        return

    config = validate_config(cfg)

    from pprint import pprint

    pprint(config.model_dump())


if __name__ == "__main__":
    main()
