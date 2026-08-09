"""One-off: record accepted review decisions for the 24 third-party seeds
added in scripts/rebuild_seed_artifacts.py. Run once, then delete or keep
as a record — it is idempotent (re-running just re-writes the same content
since ReviewDecision.decided_at is the only non-deterministic field, and
this script pins it explicitly below)."""

from pathlib import Path

from satyrn_model.authoring.review import ReviewDecision, read_decisions, write_decisions
from satyrn_model.authoring.seeds import read_seeds_jsonl

THIRD_PARTY_LITERALS = {
    't"^{filename}$"',
    't"{regex_chars}"',
    't"value_{number:03d}"',
    't"{value:.1f}"',
    't"{value!r}"',
    't"{{{value}}}"',
    't"{special_chars}"',
    (
        't"""\n'
        "            ^                   # Start of string\n"
        "            {username}          # Username (escaped)\n"
        "            @                   # Literal @\n"
        "            {domain}            # Domain (escaped)\n"
        "            $                   # End of string\n"
        '        """'
    ),
    "t'SELECT *, ({subquery}) as post_user FROM users'",
    "t'SELECT * FROM users WHERE id = {5} AND post_count > ({subquery})'",
    "t'SELECT id FROM tree UNION ALL SELECT id+1 FROM tree WHERE id < 10'",
    't"SELECT * FROM users WHERE name = {user_input}"',
    't"SELECT username, ({subquery}) as post_count FROM users WHERE id = {user_id}"',
    't"{cte} SELECT u.username FROM users u JOIN active_users au ON u.id = au.user_id"',
    (
        't"WITH {cte1}, {cte2} SELECT DISTINCT u.username FROM users u '
        'JOIN active_posters ap ON u.id = ap.user_id '
        'JOIN active_commenters ac ON u.id = ac.user_id"'
    ),
    't"SELECT user_id FROM posts WHERE id IN ({innermost})"',
    't"<p>Hello, {name}!</p>"',
    't"<div>{title}: {count}</div>"',
    't\'<div value1="{value1}" value2={value2} />\'',
    't"<p style={styles1} style={styles2}>Warning!</p>"',
    't"<style>div {{ background-color: red; }} {content}</style>"',
    't\'<a href="{section_url}">{section_name}</a>\'',
    't"<div data-range={start}-{end}></div>"',
    't"<title>A great story; {bool_value}</title>"',
}

REASON = (
    "owner-approved recommendation: extracted from an approved one-time "
    "third-party source (see docs/superpowers/specs/"
    "2026-08-09-sp5-seed-sourcing-design.md); unique, fully bound, "
    "executable PEP 750 seed; screened against tdom-specific component "
    "and attribute-spread conventions where applicable"
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
        if seed.literal in THIRD_PARTY_LITERALS
    ]
    assert len(seeds) == 24, f"expected 24 third-party seeds, found {len(seeds)}"

    new_decisions = [
        ReviewDecision(
            seed_id=seed.id,
            verdict="accepted",
            reason=REASON,
            content_sha256=seed.id,  # seed_content_sha256(seed) == seed.id
            decided_at=FIXED_DECIDED_AT,
        )
        for seed in seeds
        if seed.id not in existing_ids
    ]

    write_decisions(existing + new_decisions, decisions_path)
    print(f"appended {len(new_decisions)} review decisions")


if __name__ == "__main__":
    main()
