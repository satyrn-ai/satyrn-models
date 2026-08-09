"""Append 7 hand-authored logging seeds. See docs/superpowers/specs/
2026-08-09-sp5-data-logging-floors-design.md for why these are
hand-authored rather than extracted (real usage is exhausted)."""

from pathlib import Path

from satyrn_model.authoring.models import Seed, seed_id
from satyrn_model.authoring.seeds import read_seeds_jsonl, write_seeds_jsonl

NEW_LOGGING_SEEDS = (
    ('t"[DEBUG] {msg}"', (("msg", "'cache miss'"),)),
    (
        't"[WARNING] slow query took {elapsed:.2f}s"',
        (("elapsed", "1.23"),),
    ),
    (
        't"[ERROR] request failed with status {status}"',
        (("status", "500"),),
    ),
    (
        't"user={user} action={action} status={status}"',
        (
            ("user", "'alice'"),
            ("action", "'login'"),
            ("status", "'ok'"),
        ),
    ),
    ('t"retrying={retry}"', (("retry", "True"),)),
    (
        't"{event!r}: id={record_id}"',
        (("event", "'order_created'"), ("record_id", "42")),
    ),
    (
        't"correlation_id={cid} duration_ms={dur}"',
        (("cid", "'abc-123'"), ("dur", "42")),
    ),
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "seeds/authored.jsonl"
    existing = read_seeds_jsonl(path)
    existing_literals = {seed.literal for seed in existing}

    next_occ = max(
        (
            int(occ_id.removeprefix("occ-auth-"))
            for seed in existing
            for occ_id in seed.occurrence_ids
            if occ_id.startswith("occ-auth-")
        ),
        default=-1,
    ) + 1

    new_seeds = []
    for i, (literal, bindings) in enumerate(NEW_LOGGING_SEEDS):
        if literal in existing_literals:
            continue
        new_seeds.append(
            Seed(
                id=seed_id(literal, bindings),
                literal=literal,
                free_names=tuple(name for name, _ in bindings),
                bindings=bindings,
                occurrence_ids=(f"occ-auth-{next_occ + i}",),
                kind="authored",
                domain="logging",
            )
        )

    write_seeds_jsonl(existing + new_seeds, path)
    print(f"appended {len(new_seeds)} logging seeds")


if __name__ == "__main__":
    main()
