"""Rebuild reviewed seed candidates from exact, source-resolved inputs."""

import dataclasses
import json
from pathlib import Path

from satyrn_model.authoring.models import (
    Domain,
    SeedOccurrence,
    SourceOrigin,
    occurrence_id,
    seed_id,
)
from satyrn_model.authoring.seeds import (
    normalize_seeds,
    read_seeds_jsonl,
    write_occurrences_jsonl,
    write_seeds_jsonl,
)

CPYTHON_ID = "cpython-v3.14.5"
CPYTHON_PATH = "Lib/test/test_string/test_templatelib.py"

# Exact source literals and spans from sources.toml's pinned CPython revision.
CPYTHON_SEEDS = (
    ("t'Hello, world'", (), 31, 31, "text"),
    ("t'Hello, {name}'", (("name", '"Lys"'),), 96, 96, "text"),
    (
        "t'Hello, {name}, {age} from {country}'",
        (("name", '"Lys"'), ("age", "0"), ("country", '"GR"')),
        101,
        101,
        "text",
    ),
    ("t'With inter {user}'", (("user", "'test'"),), 109, 109, "text"),
    ("t'With ! {user!r}'", (("user", "'test'"),), 110, 110, "text"),
    ("t'With format {1 / 0.3:.2f}'", (), 111, 111, "data"),
    ('t"{1}"', (), 166, 166, "data"),
    ("t'abc {x} yz'", (("x", "1"),), 154, 154, "text"),
    ('t"""Hello,\nworld"""', (), 41, 42, "text"),
    ('t"No values"', (), 108, 108, "text"),
)

# Exact literals, hand-resolved bindings, and spans from the five sources
# registered in Task 1. See docs/superpowers/specs/
# 2026-08-09-sp5-seed-sourcing-design.md for how these were selected.
# Each entry: (source_id, path, (literal, bindings), line_start, line_end, domain)
THIRD_PARTY_SEEDS = (
    # regex-template-2026, tests/test_regex_template.py
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"^{filename}$"', (("filename", "'report.txt'"),)),
        87,
        87,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"{regex_chars}"', (("regex_chars", "'[0-9]+'"),)),
        163,
        163,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"{{{value}}}"', (("value", "'3,5'"),)),
        212,
        212,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"{special_chars}"', (("special_chars", "'.*+?'"),)),
        80,
        80,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        (
            (
                't"""\n'
                "            ^                   # Start of string\n"
                "            {username}          # Username (escaped)\n"
                "            @                   # Literal @\n"
                "            {domain}            # Domain (escaped)\n"
                "            $                   # End of string\n"
                '        """'
            ),
            (("username", "'john_doe'"), ("domain", "'example.com'")),
        ),
        128,
        134,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"value_{number:03d}"', (("number", "7"),)),
        101,
        101,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"{value:.1f}"', (("value", "3.14159"),)),
        108,
        108,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        ('t"{value!r}"', (("value", "'raw'"),)),
        113,
        113,
        "regex",
    ),
    # t-sql-2026
    (
        "t-sql-2026",
        "tests/test_query_builder.py",
        (
            "t'SELECT *, ({subquery}) as post_user FROM users'",
            (("subquery", "'SELECT id FROM active_users'"),),
        ),
        1490,
        1490,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_query_builder.py",
        (
            "t'SELECT * FROM users WHERE id = {5} AND post_count > ({subquery})'",
            (("subquery", "'SELECT id FROM active_users'"),),
        ),
        1507,
        1507,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_query_builder.py",
        (
            "t'SELECT id FROM tree UNION ALL SELECT id+1 FROM tree WHERE id < 10'",
            (),
        ),
        1628,
        1628,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_parameter_names.py",
        (
            't"SELECT * FROM users WHERE name = {user_input}"',
            (("user_input", "'jsmith'"),),
        ),
        13,
        13,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_deep_nesting.py",
        (
            (
                't"SELECT username, ({subquery}) as post_count '
                'FROM users WHERE id = {user_id}"'
            ),
            (
                ("subquery", "'SELECT id FROM active_users'"),
                ("user_id", "7"),
            ),
        ),
        46,
        46,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_deep_nesting.py",
        (
            (
                't"{cte} SELECT u.username FROM users u '
                'JOIN active_users au ON u.id = au.user_id"'
            ),
            (
                (
                    "cte",
                    (
                        "'WITH active_users AS (SELECT user_id, COUNT(*) "
                        "FROM posts GROUP BY user_id HAVING COUNT(*) > 5)'"
                    ),
                ),
            ),
        ),
        75,
        75,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_deep_nesting.py",
        (
            (
                't"WITH {cte1}, {cte2} SELECT DISTINCT u.username FROM users u '
                'JOIN active_posters ap ON u.id = ap.user_id '
                'JOIN active_commenters ac ON u.id = ac.user_id"'
            ),
            (
                (
                    "cte1",
                    (
                        "'active_posters AS (SELECT user_id FROM posts "
                        "GROUP BY user_id HAVING COUNT(*) > 10)'"
                    ),
                ),
                (
                    "cte2",
                    (
                        "'active_commenters AS (SELECT user_id FROM comments "
                        "GROUP BY user_id HAVING COUNT(*) > 5)'"
                    ),
                ),
            ),
        ),
        91,
        91,
        "sql",
    ),
    (
        "t-sql-2026",
        "tests/test_deep_nesting.py",
        (
            't"SELECT user_id FROM posts WHERE id IN ({innermost})"',
            (("innermost", "'SELECT id FROM x'"),),
        ),
        61,
        61,
        "sql",
    ),
    # html: tdom-svcs-2026, storyville-2026, tdom-2026
    (
        "tdom-svcs-2026",
        "tests/test_html_wrapper.py",
        ('t"<p>Hello, {name}!</p>"', (("name", "'Ada'"),)),
        35,
        35,
        "html",
    ),
    (
        "storyville-2026",
        "tests/story/test_story_views.py",
        (
            't"<div>{title}: {count}</div>"',
            (("title", "'Dashboard'"), ("count", "12")),
        ),
        78,
        78,
        "html",
    ),
    (
        "tdom-2026",
        "tdom/parser_test.py",
        (
            't\'<div value1="{value1}" value2={value2} />\'',
            (("value1", "'a'"), ("value2", "'b'")),
        ),
        301,
        301,
        "html",
    ),
    (
        "tdom-2026",
        "tdom/processor_test.py",
        (
            't"<p style={styles1} style={styles2}>Warning!</p>"',
            (("styles1", "'color:red'"), ("styles2", "'font-weight:bold'")),
        ),
        1441,
        1441,
        "html",
    ),
    (
        "tdom-2026",
        "tdom/processor_test.py",
        (
            't"<style>div {{ background-color: red; }} {content}</style>"',
            (("content", "'.text { color: blue; }'"),),
        ),
        633,
        633,
        "html",
    ),
    (
        "storyville-2026",
        "src/storyville/components/breadcrumbs/breadcrumbs.py",
        (
            't\'<a href="{section_url}">{section_name}</a>\'',
            (("section_url", "'/docs'"), ("section_name", "'Docs'")),
        ),
        57,
        57,
        "html",
    ),
    (
        "tdom-2026",
        "tdom/processor_test.py",
        (
            't"<div data-range={start}-{end}></div>"',
            (("start", "1"), ("end", "10")),
        ),
        1144,
        1144,
        "html",
    ),
    (
        "tdom-2026",
        "tdom/processor_test.py",
        (
            't"<title>A great story; {bool_value}</title>"',
            (("bool_value", "True"),),
        ),
        719,
        719,
        "html",
    ),
    # pep750-examples-2026
    (
        "pep750-examples-2026",
        "pep/test_logging.py",
        ('t"Hello, {name}!"', (("name", "'Ada'"),)),
        89,
        89,
        "logging",
    ),
    (
        "pep750-examples-2026",
        "pep/test_logging.py",
        ('t"${amount:0.2f}"', (("amount", "42.5"),)),
        61,
        61,
        "logging",
    ),
    # cpython-v3.14.5, Lib/test/test_tstring.py (data domain)
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"Sum: {a + b}"', (("a", "10"), ("b", "20"))),
        38,
        38,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"Pi: {value:.2f}"', (("value", "3.14159"),)),
        85,
        85,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"Object: {obj!s}"', (("obj", "42"),)),
        94,
        94,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"ASCII: {text!a}"', (("text", "'Café'"),)),
        105,
        105,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"Value: {value=}"', (("value", "3.14159"),)),
        117,
        117,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('t"Value: {value=:.2f}"', (("value", "3.14159"),)),
        124,
        124,
        "data",
    ),
    (
        "cpython-v3.14.5",
        "Lib/test/test_tstring.py",
        ('rt"{path}\\Documents"', (("path", "'C:'"),)),
        145,
        145,
        "data",
    ),
)

_THIRD_PARTY_LICENSES = {
    "regex-template-2026": "MIT",
    "t-sql-2026": "MIT",
    "tdom-2026": "MIT",
    "storyville-2026": "MIT",
    "tdom-svcs-2026": "MIT",
    "pep750-examples-2026": "MIT",
    "cpython-v3.14.5": "PSF-2.0",
}


def _third_party_occurrences() -> list[SeedOccurrence]:
    records: list[SeedOccurrence] = []
    for source_id, path, (literal, bindings), line_start, line_end, domain in (
        THIRD_PARTY_SEEDS
    ):
        sid = seed_id(literal, bindings)
        records.append(
            SeedOccurrence(
                id=occurrence_id(source_id, path, line_start, line_end),
                seed_id=sid,
                literal=literal,
                free_names=tuple(name for name, _ in bindings),
                bindings=bindings,
                kind="extracted",
                domain=domain,
                origin=SourceOrigin(
                    source_id=source_id,
                    path=path,
                    line_start=line_start,
                    line_end=line_end,
                    license=_THIRD_PARTY_LICENSES[source_id],
                ),
            )
        )
    return records


AUTHORED_DOMAINS: dict[str, Domain] = {
    "bb69e18ccc1e75c778a00908fe3b8146275e56510a472339d70e5bd22601c66c": "html",
    "bc41b128e01164728fe54111eef0a6cc1a9fb5ed8f7a71b3be0ada86d7f94716": "html",
    "55be91f6a9c69e55764d154f6a4cfe8b3bd441068e8f10813496cc6567148703": "html",
    "8946730e2ef8a2cc4f302ff232be16046f1e4f48a365c5624c0d504ab440cb76": "html",
    "a296f3e4016bf421215ac80c0b73f688a0c0f944e8994621631499bb905a38cf": "sql",
    "b6e71b772d245604ca215e6a8da9bd78e76e12aece5e3559b72dad34164cc879": "sql",
    "c01d983421444fedcbc3ab14665b618366f579eb14fe14665e7266a599694b43": "sql",
    "9ad1ed9cae138efa150a74eaa6c6ff0c6adc45b953673aa4ca0f11e0c8989d82": "sql",
    "fa1e4bb0df824612c681f4b1d2aa77f24d47094882b27569c7ba3cfec9eab3cf": "sql",
    "0c7ebbc8b52cb34f2bf6d46ebee7f4171643ac846ccacd7b1464675af6553046": "logging",
    "6cede8682fde66e9c30882c8923576000983c2444637ac19b8104fc3e69ddb88": "logging",
    "374f7deebdc02c8fb04e913eb17273e4f927ffb4a34d94bb54abd626598fdf95": "logging",
    "19478db5208c5497a759218fd787ef1f16eb155ffc32c9d8279dcb5819121071": "logging",
    "feb34d6da73ed5a0d871436e8c3f6734501adf83c5562dd41a0fde69f45bb1c0": "logging",
    "5ed02c0af6336ab0726d3ac547192b807bf9ed7e7c99587e6bd4215577f3406b": "logging",
    "22be7e9c0bea0767eefcf8e06d7e5525b2a71829b5b9be65bfe7a5e8ba43cf8d": "logging",
    "eb0f3cce7c4f2e77b109749b254b763ea6bc9bc779e8ca8f8c9412372108ef2d": "logging",
    "800fd438f1e439f0e71f73f1d7c90c405bbafcd2692d16884125027c1f9738fb": "logging",
    "4b52489fd64cbb88d8dd9abf9ecabfef63ddf04fb8fc8ce14e6ea18800e06d93": "regex",
    "0a2266f82a16cf7245da8edf062a5374e795194f9cc6d64c8fa803bc2de2f22c": "html",
    "a02edb14732429777b86c844a43010b4131e5cd1def9649b3f7409306f82ce6d": "html",
    "60327196fc1ff41a786b2adff3b9613741aa536ef9e226149765e76882e688fd": "html",
    "4240bbd4e1eb5a1dc6557a5ef89ce68addfd2aa00a96f242bb4250fff2d808c8": "sql",
    "d3b387c0e99ed3df31829db4030eeef4e29bf79d3f950efcc63ebd44efc70e33": "sql",
    "bdda5c60492401ed0455a5bb7c9ef29ccffc930efa9c77c9ceb5d8bb5d932f74": "logging",
    "25578ad77ce79ec82aaf9e15d09bf599d2b4f9bfa3743305aa168e41c326184d": "logging",
    "58f2e0cdc131afd3aad035de06ae398ec10dfb7f73d0e9e0f5b2e1406a353da7": "regex",
    "16ab3fe03e6a2910454d8158168f483d977fb132c49e09fffb2a157152366668": "regex",
    "cee08bb602f7088957e7e10d9533a03fef911f04e4de2fa484b812126a11026e": "data",
    "44c667b8fa15930244023114d7a31a383b00be437908d56219c3c3d3f4370ee1": "data",
    "5b3ffd828238f24a9f06b04d7c940d104ac86299e6cf81892e00a9e228aaed1c": "data",
    "65134111f96a58e512c3c6611876b92dfeb335a4d65937e531c147a27a669a30": "data",
}


def _occurrences() -> list[SeedOccurrence]:
    records: list[SeedOccurrence] = []
    for literal, bindings, line_start, line_end, domain in CPYTHON_SEEDS:
        sid = seed_id(literal, bindings)
        records.append(
            SeedOccurrence(
                id=occurrence_id(
                    CPYTHON_ID, CPYTHON_PATH, line_start, line_end
                ),
                seed_id=sid,
                literal=literal,
                free_names=tuple(name for name, _ in bindings),
                bindings=bindings,
                kind="extracted",
                domain=domain,
                origin=SourceOrigin(
                    source_id=CPYTHON_ID,
                    path=CPYTHON_PATH,
                    line_start=line_start,
                    line_end=line_end,
                    license="PSF-2.0",
                ),
            )
        )
    return records


def _quarantine_unresolved_html(root: Path) -> None:
    destination = root / "seeds/quarantine/imported-html-candidates.jsonl"
    source = destination if destination.exists() else root / "seeds/extracted.jsonl"
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unresolved = [
        record
        for record in records
        if any(
            occurrence.startswith("occ-tdom-")
            for occurrence in record.get("occurrence_ids", [])
        )
        or record.get("disposition") == "authored_candidate"
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(
            json.dumps(
                {
                    **record,
                    "disposition": "authored_candidate",
                    "quarantine_reason": "no source-resolved occurrence",
                },
                sort_keys=True,
            )
            + "\n"
            for record in unresolved
        ),
        encoding="utf-8",
    )


def _annotate_authored_domains(root: Path) -> None:
    path = root / "seeds/authored.jsonl"
    seeds = read_seeds_jsonl(path)
    write_seeds_jsonl(
        [
            dataclasses.replace(seed, domain=AUTHORED_DOMAINS.get(seed.id, "text"))
            for seed in seeds
        ],
        path,
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    _quarantine_unresolved_html(root)
    _annotate_authored_domains(root)
    occurrences = _occurrences() + _third_party_occurrences()
    write_occurrences_jsonl(occurrences, root / "seeds/occurrences.jsonl")
    write_seeds_jsonl(normalize_seeds(occurrences), root / "seeds/extracted.jsonl")
    print(
        f"rebuilt {len(occurrences)} extracted occurrences; "
        "quarantined unresolved HTML candidates"
    )


if __name__ == "__main__":
    main()
