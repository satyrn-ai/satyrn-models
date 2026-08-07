"""Fine-tune Qwen2.5-Coder-7B on PEP 750 template strings (t-strings) with MLX LoRA.

Run `python make_data.py` first to generate data/pep750.jsonl (all examples
are verified against the current Python 3.14+ interpreter).
"""

import json

# ---------------------------------------------------------------------------
# Python 3.14 compat shim for `datasets`.
#
# datasets 4.x (utils/_dill.py) overrides Pickler._batch_setitems with a
# 2-arg signature (self, items), assuming the pre-3.14 pickle API.  Python
# 3.14 changed pickle._Pickler._batch_setitems to a 3-arg signature
# (self, items, obj) and save_dict now calls it with 3 args, so the 2-arg
# override raises "takes 2 positional arguments but 3 were given" on every
# fingerprint/dill serialization.  Patch it to forward `obj` through to the
# parent while preserving datasets' key-sorting for deterministic hashes.
# Drop this block once datasets ships a 3.14-compatible _dill.py.
# ---------------------------------------------------------------------------
import dill
import datasets.utils._dill as _hf_dill


def _patched_batch_setitems(self, items, obj=None):
    if getattr(self, "_legacy_no_dict_keys_sorting", False):
        return dill.Pickler._batch_setitems(self, items, obj)
    try:
        items = sorted(items)
    except Exception:
        from datasets.fingerprint import Hasher

        items = sorted(items, key=lambda x: Hasher.hash(x[0]))
    return dill.Pickler._batch_setitems(self, items, obj)


_hf_dill.Pickler._batch_setitems = _patched_batch_setitems
# ---------------------------------------------------------------------------

from datasets import Dataset
from unsloth import FastLanguageModel
from unsloth_zoo.mlx.trainer import MLXTrainer, MLXTrainingConfig

DATA_FILE = "data/pep750.jsonl"
MODEL_NAME = "Qwen/Qwen2.5-Coder-7B"
OUTPUT_DIR = "./qwen2.5-coder-pep750"


def _resolve_local_model(model_id: str) -> str:
    """Return the local snapshot path for a cached HuggingFace model.

    Falls back to the repo id if the model isn't cached (triggers a
    download on first call).
    """
    from pathlib import Path

    from huggingface_hub import try_to_load_from_cache

    path = try_to_load_from_cache(model_id, "config.json")
    if path is not None:
        return str(Path(path).parent)
    return model_id


def main():
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=_resolve_local_model(MODEL_NAME),
        max_seq_length=2048,
        dtype=None,  # Auto-detect bfloat16/float16 (do NOT use "auto" — crashes the MLX loader)
        load_in_4bit=False,  # ~15 GB in bf16; set True if memory-constrained
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing=True,
    )

    with open(DATA_FILE) as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    dataset = Dataset.from_list(rows)

    training_args = MLXTrainingConfig(
        output_dir="./results",
        per_device_train_batch_size=2,
        num_train_epochs=3,
        max_steps=0,  # 0 → honour num_train_epochs (default 60 overrides otherwise)
        learning_rate=2e-4,
        logging_steps=10,
        report_to="none",
        max_seq_length=2048,
    )

    trainer = MLXTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        dataset_text_field="text",
    )
    trainer.train()

    # Inference: model.generate() returns a token-id tensor (HF-compatible), not a str
    prompt = "# Python 3.14 t-strings: greet a user by name with a reusable template\n"
    output = model.generate(prompt, max_new_tokens=150)
    print(tokenizer.decode(output[0], skip_special_tokens=True))

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)


if __name__ == "__main__":
    main()
