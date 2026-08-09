"""Record accepted review decisions for the 14 seeds added in this batch
(7 data, extracted; 7 logging, authored). See docs/superpowers/specs/
2026-08-09-sp5-data-logging-floors-design.md."""

from pathlib import Path

from satyrn_model.authoring.review import ReviewDecision, read_decisions, write_decisions
from satyrn_model.authoring.seeds import read_seeds_jsonl

NEW_LITERALS = {
    't"Sum: {a + b}"',
    't"Pi: {value:.2f}"',
    't"Object: {obj!s}"',
    't"ASCII: {text!a}"',
    't"Value: {value=}"',
    't"Value: {value=:.2f}"',
    'rt"{path}\\Documents"',
    't"[DEBUG] {msg}"',
    't"[WARNING] slow query took {elapsed:.2f}s"',
    't"[ERROR] request failed with status {status}"',
    't"user={user} action={action} status={status}"',
    't"retrying={retry}"',
    't"{event!r}: id={record_id}"',
    't"correlation_id={cid} duration_ms={dur}"',
}

REASON = (
    "owner-approved recommendation: unique, fully bound, executable PEP "
    "750 seed closing the data/logging domain floor (see "
    "docs/superpowers/specs/2026-08-09-sp5-data-logging-floors-design.md); "
    "approval covers template shape only"
)

FIXED_DECIDED_AT = "2026-08-09T00:00:00+00:00"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    decisions_path = root / "review/decisions.jsonl"

    existing = read_decisions(decisions_path)
    existing_ids = {d.seed_id for d in existing}

    seeds = [
        seed
        for path in (root / "seeds/authored.jsonl", root / "seeds/extracted.jsonl")
        for seed in read_seeds_jsonl(path)
        if seed.literal in NEW_LITERALS
    ]
    assert len(seeds) == 14, f"expected 14 new seeds, found {len(seeds)}"

    new_decisions = [
        ReviewDecision(
            seed_id=seed.id,
            verdict="accepted",
            reason=REASON,
            content_sha256=seed.id,
            decided_at=FIXED_DECIDED_AT,
        )
        for seed in seeds
        if seed.id not in existing_ids
    ]

    write_decisions(existing + new_decisions, decisions_path)
    print(f"appended {len(new_decisions)} review decisions")


if __name__ == "__main__":
    main()
