"""Record the owner-approved review recommendation for active seeds."""

import dataclasses
import json
from pathlib import Path

from satyrn_model.authoring.review import ReviewDecision, seed_content_sha256
from satyrn_model.authoring.seeds import read_seeds_jsonl

DECIDED_AT = "2026-08-03T16:15:00+02:00"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    seeds = [
        seed
        for path in (root / "seeds/authored.jsonl", root / "seeds/extracted.jsonl")
        for seed in read_seeds_jsonl(path)
    ]
    decisions = [
        ReviewDecision(
            seed_id=seed.id,
            verdict="accepted",
            reason=(
                "owner-approved recommendation: unique, fully bound, executable "
                f"PEP 750 {seed.kind} seed; approval covers template shape only"
            ),
            content_sha256=seed_content_sha256(seed),
            decided_at=DECIDED_AT,
        )
        for seed in sorted(seeds, key=lambda item: item.id)
    ]
    destination = root / "review/decisions.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(
            json.dumps(dataclasses.asdict(decision), sort_keys=True) + "\n"
            for decision in decisions
        ),
        encoding="utf-8",
    )
    print(f"recorded {len(decisions)} active seed decisions")


if __name__ == "__main__":
    main()
