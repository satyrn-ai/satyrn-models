"""Train LoRA adapters on the rendered corpus."""

import json
import sys
from pathlib import Path

import click

_DEFAULT_MODEL = "jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit"


def to_mlxlm_messages(input_path: Path, output_dir: Path) -> Path:
    """Convert converged rows to mlx-lm's `messages` chat format."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "train.mlxlm.jsonl"
    rows = []
    for line in input_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows.append({"messages": row["prompt"] + row["completion"]})
    out.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return out


@click.command("train")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="SFT train jsonl to train on.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="adapters",
    show_default=True,
    help="Directory to write trained adapters into.",
)
@click.option("--model", default=_DEFAULT_MODEL, show_default=True, help="Base model to fine-tune.")
@click.option("--seed", type=int, required=True, help="Training seed (one adapter per seed).")
@click.option("--iters", type=int, default=200, show_default=True, help="Iterations to train for.")
def main(input: Path, output_dir: Path, model: str, seed: int, iters: int) -> None:
    """Train a LoRA adapter on the corpus for one seed."""
    train_data = to_mlxlm_messages(input, output_dir)
    adapter_path = output_dir / f"seed{seed}" / "adapters.safetensors"
    adapter_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        "mlx_lm.lora",
        "--model",
        model,
        "--train",
        str(train_data),
        "--seed",
        str(seed),
        "--iters",
        str(iters),
        "--adapter-path",
        str(adapter_path),
    ]
    import mlx_lm.lora as lora

    old_argv = sys.argv
    sys.argv = argv
    try:
        lora.main()
    finally:
        sys.argv = old_argv
