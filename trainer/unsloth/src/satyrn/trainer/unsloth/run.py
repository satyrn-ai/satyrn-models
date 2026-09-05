"""Entry point for the satyrn-unsloth trainer CLI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import hydra
import mlflow
from datasets import Dataset
from hydra.core.hydra_config import HydraConfig
from inspect_evals.humaneval import humaneval
from omegaconf import DictConfig

from satyrn.trainer.unsloth.config import ExperimentConfig, StageName, log_config, validate_config
from satyrn.trainer.unsloth.dataset_packing import pack_documents
from satyrn.trainer.unsloth.eval.inspect_runner import run_inspect_eval
from satyrn.trainer.unsloth.eval.python_eval import python_eval
from satyrn.trainer.unsloth.eval.qa import run_eval_qa
from satyrn.trainer.unsloth.log_capture import tee_output
from satyrn.trainer.unsloth.secrets import load_secrets

if TYPE_CHECKING:
    from torch.nn import Module
    from transformers import PreTrainedTokenizerBase

logger = logging.getLogger(__name__)
logging.getLogger("satyrn").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

CONFIG_DIR = str(Path(__file__).resolve().parents[4] / "configs")


def unsloth_init() -> None:
    """Initialize unsloth and patch the training libraries."""
    global FastModel, FastVisionModel, SFTConfig, SFTTrainer, torch, train_on_responses_only

    # Unsloth must be imported first to patch transformers, accelerate, etc.
    from unsloth import FastModel, FastVisionModel  # noqa: I001
    from unsloth.chat_templates import train_on_responses_only
    import torch
    from trl import SFTConfig, SFTTrainer

    # In notebooks, NotebookProgressCallback logs loss to an IPython handle we cannot capture in the logs
    import transformers.trainer
    from transformers.trainer_callback import ProgressCallback

    transformers.trainer.DEFAULT_PROGRESS_CALLBACK = ProgressCallback


def load_dataset(paths: str | list[str]) -> Dataset:
    """Read one or more JSONL files into a single dataset."""
    if isinstance(paths, str):
        paths = [paths]

    rows = []
    for path in paths:
        with Path(path).open() as fh:
            rows += [json.loads(line) for line in fh if line.strip()]
    return Dataset.from_list(rows)


def render_conversations_into_text_field(
    dataset: Dataset, tokenizer: PreTrainedTokenizerBase, enable_thinking: bool
) -> Dataset:
    """Render each prompt+completion row into the text column the trainer tokenizes."""

    def render(row: dict) -> dict:
        assistant = dict(row["completion"][0])
        if enable_thinking:
            assistant["reasoning_content"] = row["trace"]
        return {"text": tokenizer.apply_chat_template(row["prompt"] + [assistant], tokenize=False)}

    # A row still holding prompt and completion columns takes the trainer's prompt-completion
    # path, which masks by prompt length and ignores the text column.
    return dataset.map(render, remove_columns=dataset.column_names)


def build_trainer(
    name: StageName,
    model: Module,
    tokenizer: PreTrainedTokenizerBase,
    dataset: Dataset,
    cfg: ExperimentConfig,
    packing: bool = False,
    packing_strategy: str = "bfd",  # best-fit, decreasing document size order; truncates over max_length
) -> SFTTrainer:
    """Split the dataset and build the trainer for one stage."""
    stage = getattr(cfg, name)
    split = dataset.train_test_split(test_size=cfg.eval_ratio, seed=42)
    train_dataset, eval_dataset = split["train"], split["test"]

    training_args = SFTConfig(
        output_dir=f"outputs/{name}",
        per_device_train_batch_size=stage.batch_size,
        per_device_eval_batch_size=stage.eval_batch_size,
        gradient_accumulation_steps=stage.gradient_accumulation_steps,
        logging_steps=cfg.logging_steps,
        eval_strategy="steps",
        eval_steps=stage.eval_steps,
        report_to="mlflow",
        max_length=stage.seq_len,
        num_train_epochs=stage.num_train_epochs,
        max_steps=cfg.max_steps,
        learning_rate=stage.learning_rate,
        shuffle_dataset=True,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim=cfg.optim,
        packing=packing,
        packing_strategy=packing_strategy,
        dataset_text_field="text",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
    )

    return trainer


def evaluate_model(stage_name: StageName, model: Module, tokenizer: PreTrainedTokenizerBase) -> None:
    """Run every eval against the model as it stands after stage_name."""
    run_eval_qa(stage_name, model, tokenizer)
    run_inspect_eval(stage_name, model, tokenizer, humaneval(sandbox="local"))
    run_inspect_eval(stage_name, model, tokenizer, python_eval())


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
        model, tokenizer = FastVisionModel.from_pretrained(
            model_name=config.model.name,
            max_seq_length=config.max_seq_length,
            dtype=None,
            load_in_4bit=config.load_in_4bit,
        )
        # Multimodal models return a Processor; text-only training uses its tokenizer.
        tokenizer = getattr(tokenizer, "tokenizer", tokenizer)

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
            try:
                mlflow.log_params(
                    {
                        "torch_version": torch.__version__,
                        "cuda_version": torch.version.cuda,
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

                logger.info("Model evaluation before training")
                evaluate_model("pre", model, tokenizer)

                if config.datasets.cpt is not None:
                    logger.info("Starting Continuous Pre-Training (CPT) stage")
                    dataset = load_dataset(config.datasets.cpt)
                    packing = config.cpt.packing

                    if packing and config.cpt.prepack_dataset:
                        packed = pack_documents(dataset, tokenizer, config.cpt.seq_len)
                        logger.info("Packed cpt: %d documents into %d sequences", len(dataset), len(packed))
                        dataset = packed
                        logger.warning("Prepacking done, setting packing=false to avoid double packing")
                        packing = False

                    trainer = build_trainer(
                        "cpt",
                        model,
                        tokenizer,
                        dataset,
                        config,
                        packing=packing,
                        packing_strategy="bfd_split",  # best-fit, decreasing doc size order; splits over max_length
                    )

                    with mlflow.start_run(run_name="cpt", nested=True):
                        mlflow.log_params(
                            {"dataset_path": config.datasets.cpt, "dataset_train_rows": len(trainer.train_dataset)}
                        )
                        trainer.train()

                    logger.info("Model evaluation after Continuous Pre-Training (CPT)")
                    evaluate_model("cpt", model, tokenizer)

                if config.datasets.sft is not None:
                    logger.info("Starting Supervised Fine-Tuning (SFT) stage")
                    dataset = load_dataset(config.datasets.sft)
                    dataset = render_conversations_into_text_field(dataset, tokenizer, config.model.enable_thinking)

                    trainer = build_trainer("sft", model, tokenizer, dataset, config)
                    trainer = train_on_responses_only(
                        trainer,
                        instruction_part=config.model.template.instruction_part,
                        response_part=config.model.template.response_part,
                    )

                    with mlflow.start_run(run_name="sft", nested=True):
                        mlflow.log_params(
                            {"dataset_path": config.datasets.sft, "dataset_train_rows": len(trainer.train_dataset)}
                        )
                        trainer.train()

                    logger.info("Model evaluation after Supervised Fine-Tuning (SFT)")
                    evaluate_model("sft", model, tokenizer)

                if config.datasets.rl is not None:
                    logger.error("Unimplemented: Reinforcement Learning (RL) training")

            except Exception:
                logger.exception("Run failed")
                raise
            finally:
                # Send the Hydra job log to the tracking server
                log_file.flush()
                mlflow.log_text(log_path.read_text(), "train.log")

    mlflow.end_run()


if __name__ == "__main__":
    main()
