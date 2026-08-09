"""Task 2: the 24 third-party regex/sql/html seeds resolve correctly."""

from pathlib import Path

from satyrn_model.authoring.models import occurrence_id, seed_id
from satyrn_model.authoring.seeds import read_occurrences_jsonl, read_seeds_jsonl

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_NEW_LITERALS = {
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


def test_third_party_seeds_are_present_and_source_resolved() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occ.id: occ for occ in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }

    literals = {seed.literal for seed in seeds}
    missing = EXPECTED_NEW_LITERALS - literals
    assert not missing, f"seeds/extracted.jsonl is missing: {missing}"

    third_party_source_ids = {
        "regex-template-2026",
        "t-sql-2026",
        "tdom-2026",
        "storyville-2026",
        "tdom-svcs-2026",
    }
    for seed in seeds:
        if seed.literal not in EXPECTED_NEW_LITERALS:
            continue
        assert seed.id == seed_id(seed.literal, seed.bindings)
        occ = occurrences[seed.occurrence_ids[0]]
        assert occ.origin.source_id in third_party_source_ids
        assert occ.origin.license == "MIT"
        assert occ.id == occurrence_id(
            occ.origin.source_id,
            occ.origin.path,
            occ.origin.line_start,
            occ.origin.line_end,
        )


def test_extracted_seed_count_grew_to_thirty_four() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    assert len(seeds) == 34
