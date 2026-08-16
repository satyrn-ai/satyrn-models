"""Entry point for the satyrn-unsloth trainer CLI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import hydra
import mlflow
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig

from satyrn.trainer.unsloth.config import ExperimentConfig, StageName, log_config, validate_config
from satyrn.trainer.unsloth.log_capture import tee_output
from satyrn.trainer.unsloth.secrets import load_secrets

if TYPE_CHECKING:
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

CONFIG_DIR = str(Path(__file__).resolve().parents[4] / "configs")


def unsloth_init() -> None:
    """Initialize unsloth and patch the training libraries."""
    global Dataset, FastModel, SFTConfig, SFTTrainer, torch

    # Unsloth must be imported first to patch transformers, accelerate, etc.
    from unsloth import FastModel  # noqa: I001
    import torch
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer


def load_dataset(path: str | Path) -> Dataset:
    with open(path) as fh:  # noqa: PTH123
        rows = [json.loads(line) for line in fh if line.strip()]
    return Dataset.from_list(rows)


def run_supervised_tuning(
    name: StageName,
    model: Module,
    tokenizer: PreTrainedTokenizerBase,
    dataset_path: str,
    cfg: ExperimentConfig,
    **sft_kwargs,
) -> None:
    logger.info("Starting %s stage", name)
    stage = getattr(cfg, name)
    dataset = load_dataset(dataset_path)
    split = dataset.train_test_split(test_size=cfg.eval_ratio, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]

    training_args = SFTConfig(
        output_dir=f"outputs/{name}",
        per_device_train_batch_size=stage.batch_size,
        per_device_eval_batch_size=cfg.eval_batch_size,
        gradient_accumulation_steps=stage.gradient_accumulation_steps,
        logging_steps=cfg.logging_steps,
        eval_strategy="steps",
        eval_steps=cfg.eval_steps,
        report_to="mlflow",
        max_length=stage.seq_len,
        num_train_epochs=stage.num_train_epochs,
        max_steps=cfg.max_steps,
        learning_rate=stage.learning_rate,
        packing_strategy="bfd_split",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim=cfg.optim,
        **sft_kwargs,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
    )

    with mlflow.start_run(run_name=name, nested=True):
        mlflow.log_params({"dataset_path": dataset_path, "dataset_train_rows": len(train_dataset)})
        trainer.train()


@hydra.main(config_path=CONFIG_DIR)
def main(cfg: DictConfig) -> None:
    if not cfg:
        print("Usage: satyrn-unsloth --config-name experiment/<name>")
        return

    log_path = Path(HydraConfig.get().runtime.output_dir, "run.log")
    with tee_output(log_path) as log_file:
        unsloth_init()
        load_secrets()
        log_config(cfg)
        config = validate_config(cfg)

        logger.info("Downloading model %s", config.model.name)
        model, tokenizer = FastModel.from_pretrained(
            model_name=config.model.name,
            max_seq_length=config.max_seq_length,
            dtype=None,
            load_in_4bit=config.load_in_4bit,
            text_only=True,
        )
        model = FastModel.get_peft_model(
            model,
            r=config.model.peft.r,
            lora_alpha=config.model.peft.lora_alpha,
            lora_dropout=config.model.peft.lora_dropout,
            target_modules=config.model.peft.target_modules,
            finetune_attention_modules=config.model.peft.finetune_attention_modules,
            finetune_mlp_modules=config.model.peft.finetune_mlp_modules,
            finetune_language_layers=config.model.peft.finetune_language_layers,
            finetune_vision_layers=config.model.peft.finetune_vision_layers,
            finetune_audio_layers=config.model.peft.finetune_audio_layers,
            bias="none",
            use_gradient_checkpointing="unsloth",
        )
        # logger.info("PEFT model %s", model)
        trainable_params, all_params = model.get_nb_trainable_parameters()
        trainable_percentage = 100 * trainable_params / all_params
        logger.info("Trainable params: %s", f"{trainable_params:,}")
        logger.info("All params: %s", f"{all_params:,}")
        logger.info("Trainable: %.4f%%", trainable_percentage)

        mlflow.enable_system_metrics_logging()
        mlflow.set_tracking_uri(config.mlflow.tracking_uri)
        mlflow.set_experiment(config.mlflow.experiment_name)

        with mlflow.start_run(run_name=config.run_name):
            mlflow.log_params(
                {
                    "base_model": config.model.name,
                    "lora_rank": config.model.peft.r,
                    "lora_alpha": config.model.peft.lora_alpha,
                    "lora_dropout": config.model.peft.lora_dropout,
                    "lora_targets": ",".join(config.model.peft.target_modules or []),
                    "finetune_attention_modules": config.model.peft.finetune_attention_modules,
                    "finetune_mlp_modules": config.model.peft.finetune_mlp_modules,
                    "finetune_language_layers": config.model.peft.finetune_language_layers,
                    "finetune_vision_layers": config.model.peft.finetune_vision_layers,
                    "finetune_audio_layers": config.model.peft.finetune_audio_layers,
                    "params_train": trainable_params,
                    "params_total": all_params,
                    "params_train_pct": trainable_percentage,
                }
            )

            if config.datasets.cpt is not None:
                run_supervised_tuning(
                    "cpt",
                    model,
                    tokenizer,
                    config.datasets.cpt,
                    config,
                    packing=config.cpt.packing,
                    dataset_text_field="text",
                )

            if config.datasets.sft is not None:
                run_supervised_tuning(
                    "sft",
                    model,
                    tokenizer,
                    config.datasets.sft,
                    config,
                )

            if config.datasets.rl is not None:
                logger.error("Unimplemented: RL training")

            # Send the Hydra job log to the tracking server
            log_file.flush()
            mlflow.log_text(log_path.read_text(), "train.log")

    mlflow.end_run()


if __name__ == "__main__":
    main()
