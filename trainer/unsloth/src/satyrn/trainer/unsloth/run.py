"""Entry point for the satyrn-unsloth trainer CLI."""

import json
import logging
from pathlib import Path

import unsloth  # noqa: F401 Required at top of file

import hydra
import mlflow
import torch
from datasets import Dataset
from omegaconf import DictConfig
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel

from satyrn.trainer.unsloth.config import ExperimentConfig, validate_config
from satyrn.trainer.unsloth.secrets import load_secrets

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

CONFIG_DIR = str(Path(__file__).resolve().parents[4] / "configs")


def _load_dataset(path: str) -> Dataset:
    with open(path) as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return Dataset.from_list(rows)


def run_supervised_tuning(name: str, model, tokenizer, dataset_path: str, cfg: ExperimentConfig, **sft_kwargs) -> None:
    logger.info("Starting %s stage", name)
    dataset = _load_dataset(dataset_path)

    training_args = SFTConfig(
        output_dir=f"outputs/{name}",
        per_device_train_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.gradient_accumulation_steps,
        logging_steps=cfg.logging_steps,
        report_to="mlflow",
        max_seq_length=cfg.max_seq_length,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim=cfg.optim,
        **sft_kwargs,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    with mlflow.start_run(run_name=name, nested=True):
        mlflow.log_params({"dataset_path": dataset_path, "dataset_rows": len(dataset)})
        trainer.train()


@hydra.main(config_path=CONFIG_DIR)
def main(cfg: DictConfig) -> None:
    if not cfg:
        print("Usage: satyrn-unsloth --config-name experiment/<name>")
        return

    load_secrets()
    config = validate_config(cfg)

    logger.info("Downloading model %s", config.model.name)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model.name,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=config.model.lora.rank,
        target_modules=config.model.lora.target_modules,
        lora_alpha=config.model.lora.alpha,
        lora_dropout=config.model.lora.dropout,
        bias="none",
        use_gradient_checkpointing=True,
    )

    mlflow.enable_system_metrics_logging()
    mlflow.set_tracking_uri(config.mlflow.tracking_uri)
    mlflow.set_experiment(config.mlflow.experiment_name)

    with mlflow.start_run(run_name=config.run_name):
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        mlflow.log_params({
            "base_model": config.model.name,
            "lora_rank": config.model.lora.rank,
            "lora_alpha": config.model.lora.alpha,
            "lora_dropout": config.model.lora.dropout,
            "lora_targets": ",".join(config.model.lora.target_modules),
            "params_train": trainable,
            "params_total": total,
            "params_train_pct": trainable / total * 100,
        })

        if config.datasets.cpt is not None:
            run_supervised_tuning(
                "cpt", model, tokenizer, config.datasets.cpt, config,
                num_train_epochs=config.cpt.num_train_epochs,
                learning_rate=config.cpt.learning_rate,
                packing=config.cpt.packing,
                dataset_text_field="text",
            )

        if config.datasets.sft is not None:
            run_supervised_tuning(
                "sft", model, tokenizer, config.datasets.sft, config,
                num_train_epochs=config.sft.num_train_epochs,
                learning_rate=config.sft.learning_rate,
            )

        if config.datasets.rl is not None:
            logger.error("Unimplemented: RL training")

    mlflow.end_run()


if __name__ == "__main__":
    main()
