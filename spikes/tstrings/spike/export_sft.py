"""Emit a curriculum in the Mellum 2 SFT schema, for handover to JetBrains.

The Mellum 2 technical report (arXiv:2605.31268, section 5.1.1) stores every
supervised fine-tuning example in one schema: a ``messages`` list of
role/content turns, an optional ``tools`` list of function-call signatures, and
an optional ``reasoning`` field holding the chain of thought for the final
assistant turn. The Instruct variant **discards** ``reasoning``; the Thinking
variant trains on it and drops conversations that lack one.

Our rows already carry ``messages``, so this is mostly a projection: strip the
training-harness bookkeeping (``task_id``, ``semantic_id``, ``seed_ids``,
``partition``, ``prompt_family``) that means nothing outside this repo, and
keep the fields their loader reads.

We emit no ``tools`` and no ``reasoning``. Neither is a gap to fill later: the
corpus teaches a language feature through direct code answers, so there are no
function-call signatures to declare, and inventing chain-of-thought traces we
never verified would be fabricating supervision. The corpus belongs in their
**single-turn coding** category — their *agentic coding* split is long-horizon
interactive trajectories and SWE-style repository edits, which is not what this
generates.

Provenance travels beside the data rather than inside it, in ``manifest.json``,
so the JSONL stays exactly the shape their loader expects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# Everything the training harness needs and their loader does not.
HARNESS_KEYS = frozenset(
    {"task_id", "semantic_id", "seed_ids", "partition", "prompt_family"}
)


def project(row: dict) -> dict:
    """Keep the schema's fields, drop our bookkeeping."""
    exported = {"messages": row["messages"]}
    for key in ("tools", "reasoning"):
        if row.get(key):
            exported[key] = row[key]
    return exported


def unexpected_keys(rows: list[dict]) -> set[str]:
    """Row keys that are neither schema fields nor known harness bookkeeping.

    A new field added upstream would otherwise be dropped in silence, and the
    handover would quietly ship less than the curriculum holds.
    """
    seen: set[str] = set()
    for row in rows:
        seen |= set(row)
    return seen - HARNESS_KEYS - {"messages", "tools", "reasoning"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("curriculum", type=Path, help="Directory of *.jsonl splits.")
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--category",
        default="single-turn-coding",
        help="The report's SFT data category this corpus belongs to.",
    )
    args = parser.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"category": args.category, "splits": {}}

    for split in sorted(args.curriculum.glob("*.jsonl")):
        if split.name == "selection.jsonl":
            continue
        rows = [
            json.loads(line) for line in split.read_text().splitlines() if line.strip()
        ]
        if not rows:
            continue
        surprises = unexpected_keys(rows)
        if surprises:
            raise SystemExit(
                f"{split.name} carries unrecognised keys {sorted(surprises)}; "
                "decide whether they belong in the handover before exporting."
            )
        out = args.destination / split.name
        with out.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(project(row), sort_keys=True) + "\n")
        manifest["splits"][split.stem] = {
            "rows": len(rows),
            "fingerprint": hashlib.sha256(out.read_bytes()).hexdigest(),
        }
        print(f"{split.stem}: {len(rows)} rows -> {out}")

    (args.destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
