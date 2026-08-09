"""Add the frozen evaluation system prompt to an existing chat handoff."""

import argparse
import hashlib
import json
from pathlib import Path

from run_eval import _SYSTEM


def _render_partition(source: Path, destination: Path) -> str:
    rendered: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        messages = row["messages"]
        if messages[0]["role"] == "system":
            raise ValueError(f"{source} already contains a system message")
        row["messages"] = [
            {"role": "system", "content": _SYSTEM},
            *messages,
        ]
        rendered.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
    text = "\n".join(rendered) + "\n"
    destination.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)

    train = _render_partition(
        args.source / "train.jsonl", args.destination / "train.jsonl"
    )
    valid = _render_partition(
        args.source / "valid.jsonl", args.destination / "valid.jsonl"
    )
    source_manifest = json.loads(
        (args.source / "manifest.json").read_text(encoding="utf-8")
    )
    manifest = {
        **source_manifest,
        "rendered_fingerprint": hashlib.sha256(
            (train + valid).encode("utf-8")
        ).hexdigest(),
        "system_prompt": _SYSTEM,
        "system_prompt_fingerprint": hashlib.sha256(_SYSTEM.encode()).hexdigest(),
    }
    (args.destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.destination / "split-manifest.json").write_bytes(
        (args.source / "split-manifest.json").read_bytes()
    )
    print(manifest["rendered_fingerprint"])


if __name__ == "__main__":
    main()
