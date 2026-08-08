"""Spike: LoRA fine-tune on the t-string corpus with mlx-lm.

Uses --mask-prompt so loss is computed only on the assistant (code) tokens
— the B-LOSS-MASK requirement. Fixed seed for reproducibility.
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE = "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit"


def train(
    data: str,
    adapter: str,
    iters: int = 400,
    batch: int = 8,
    lr: str = "2e-5",
    layers: int = 8,
    max_seq: int = 1024,
    seed: int = 42,
) -> None:
    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", BASE,
        "--train",
        "--data", data,
        "--adapter-path", adapter,
        "--iters", str(iters),
        "--batch-size", str(batch),
        "--num-layers", str(layers),
        "--learning-rate", lr,
        "--mask-prompt",
        "--max-seq-length", str(max_seq),
        "--seed", str(seed),
        "--steps-per-report", "20",
        "--steps-per-eval", "80",
        "--save-every", "200",
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="train_data")
    ap.add_argument("--adapter", default="adapters/tstring-v1")
    ap.add_argument("--iters", type=int, default=400)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", default="2e-5")
    ap.add_argument("--layers", type=int, default=8)
    ap.add_argument("--max-seq", type=int, default=1024)
    args = ap.parse_args()
    train(args.data, args.adapter, args.iters, args.batch, args.lr,
          args.layers, args.max_seq)
