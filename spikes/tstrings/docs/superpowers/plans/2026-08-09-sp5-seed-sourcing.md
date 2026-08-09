# SP5 Seed Sourcing (regex/sql/html) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 24 new seeds (8 regex, 8 sql, 8 html) sourced from five newly
admitted third-party repos, bringing those three domains from
3/7/7 distinct seeds to 11/15/15, per `SP5_SCALE_BRIEF.md` Priority 1 and the
approved design at
`docs/superpowers/specs/2026-08-09-sp5-seed-sourcing-design.md`.

**Architecture:** Same pipeline CPython seeds already use — a
`[[source]]` record in `sources.toml` per repo, hand-resolved
`(literal, bindings, line_start, line_end, domain)` tuples wired into
`scripts/rebuild_seed_artifacts.py` (extending the existing `CPYTHON_SEEDS`
pattern with a parallel `THIRD_PARTY_SEEDS` table), producing
`SeedOccurrence` records that normalize into `seeds/extracted.jsonl`
alongside the existing 10 CPython occurrences. No new code paths — every
function used already exists in `authoring/models.py` and
`authoring/seeds.py`.

**Tech Stack:** Python 3.14, the existing `satyrn_model.authoring` package
(`sources.py`, `seeds.py`, `models.py`, `review.py`), pytest.

## Global Constraints

- **Run every command in this plan from `spikes/tstrings/`** — that's where
  `pyproject.toml`, `sources.toml`, and the `seeds/`/`review/` directories
  live. `load_sources()`/`load_policy()` (called with no explicit path by
  the new tests) resolve `Path("sources.toml")` against the process's
  current working directory, matching the convention `test_sources.py`
  already relies on — running from the wrong directory makes those calls
  silently look at (or fail to find) the wrong file.
- Every new `[[source]]` entry's `sha` must be a full 40-character immutable
  commit hash (`sources.py`'s `_FULL_SHA` regex), not a branch or tag name.
- Every new `[[source]]` entry's `license` must be in `sources.toml`'s
  `[policy] allowed_licenses` — all five sources here are MIT, already
  allowed.
- `source_class` for these entries is `"third-party"` (hyphen, not
  underscore — matches the spelling `tests/authoring/test_sources.py`
  already uses in its fixtures; the design doc's underscore spelling is
  superseded by this plan).
- Every new seed's literal text must be copied byte-for-byte from the
  pinned commit — no paraphrasing, no "close enough" quoting. This plan's
  three copies of each literal (script table, Task 2 test, Task 3 script)
  were checked character-for-character against each other; none of them
  were re-verified against the live upstream repos as part of this plan,
  which is parity with how the existing 10 CPython seeds were built, not a
  new gap.
- Logging is out of scope for this plan (see the design doc's "Logging:
  skipped in this pass" section) — do not add logging seeds here.
- **Expect `tests/authoring/test_seed_artifacts.py` to be red between Task
  2's commit and Task 4's commit** — its hardcoded counts (10, 44) don't
  match reality again until Task 4 updates them to (34, 68). This is
  intentional; don't "fix" those assertions early.

---

## The 24 seeds, resolved

These are the exact literals, line spans, and hand-assigned bindings this
plan wires in. They were selected from the pinned commits for
structural-shape novelty against the current 44 seeds (see the design doc's
"Shape verification" section: near-zero overlap in all three domains) and
screened to exclude tdom's own component-interpolation (`<{Component}>`) and
bare attribute-spread (`<tag {attrs}>`) conventions.

### regex (source: `regex-template-2026`, path `tests/test_regex_template.py`)

| literal | bindings | line |
| --- | --- | --- |
| `t"^{filename}$"` | `filename='report.txt'` | 87 |
| `t"{regex_part:safe}_{literal_part}"` | `regex_part='[0-9]+'`, `literal_part='end'` | 94 |
| `t"value_{number:03d}"` | `number=7` | 101 |
| `t"{value:.1f}"` | `value=3.14159` | 108 |
| `t"{value!r}"` | `value='raw'` | 113 |
| `t"{start:safe}{filename}{end:safe}"` | `start='^'`, `filename='log.txt'`, `end='$'` | 120 |
| `t"{digit_pattern:safe}-{word_pattern:safe}"` | `digit_pattern='[0-9]+'`, `word_pattern='[a-z]+'` | 151 |
| `t"^{pattern_template:safe}{{{count}}}$"` | `pattern_template='[a-z]'`, `count=3` | 171 |

### sql (source: `t-sql-2026`, paths as noted)

| literal | bindings | line | path |
| --- | --- | --- | --- |
| `t'SELECT *, ({subquery}) as post_user FROM users'` | `subquery='SELECT id FROM active_users'` | 1490 | `tests/test_query_builder.py` |
| `t'SELECT * FROM users WHERE id = {5} AND post_count > ({subquery})'` | `subquery='SELECT id FROM active_users'` | 1507 | `tests/test_query_builder.py` |
| `t'SELECT id FROM tree UNION ALL SELECT id+1 FROM tree WHERE id < 10'` | *(none)* | 1628 | `tests/test_query_builder.py` |
| `t"SELECT * FROM users WHERE name LIKE {search:%like%}"` | `search='jsmith'` | 14 | `tests/test_like_patterns.py` |
| `t"SELECT username, ({subquery}) as post_count FROM users WHERE id = {user_id}"` | `subquery='SELECT id FROM active_users'`, `user_id=7` | 46 | `tests/test_deep_nesting.py` |
| `t"{cte} SELECT u.username FROM users u JOIN active_users au ON u.id = au.user_id"` | `cte='WITH active_users AS (SELECT user_id, COUNT(*) FROM posts GROUP BY user_id HAVING COUNT(*) > 5)'` | 75 | `tests/test_deep_nesting.py` |
| `t"WITH {cte1}, {cte2} SELECT DISTINCT u.username FROM users u JOIN active_posters ap ON u.id = ap.user_id JOIN active_commenters ac ON u.id = ac.user_id"` | `cte1='active_posters AS (SELECT user_id FROM posts GROUP BY user_id HAVING COUNT(*) > 10)'`, `cte2='active_commenters AS (SELECT user_id FROM comments GROUP BY user_id HAVING COUNT(*) > 5)'` | 91 | `tests/test_deep_nesting.py` |
| `t"SELECT user_id FROM posts WHERE id IN ({innermost})"` | `innermost='SELECT id FROM x'` | 61 | `tests/test_deep_nesting.py` |

### html (sources as noted, all MIT)

| literal | bindings | line | source id | path |
| --- | --- | --- | --- | --- |
| `t"<p>Hello, {name}!</p>"` | `name='Ada'` | 35 | `tdom-svcs-2026` | `tests/test_html_wrapper.py` |
| `t"<div>{title}: {count}</div>"` | `title='Dashboard'`, `count=12` | 78 | `storyville-2026` | `tests/story/test_story_views.py` |
| `t'<div value1="{value1}" value2={value2} />'` | `value1='a'`, `value2='b'` | 301 | `tdom-2026` | `tdom/parser_test.py` |
| `t"<p style={styles1} style={styles2}>Warning!</p>"` | `styles1='color:red'`, `styles2='font-weight:bold'` | 1441 | `tdom-2026` | `tdom/processor_test.py` |
| `t"<style>div {{ background-color: red; }} {content}</style>"` | `content='.text { color: blue; }'` | 633 | `tdom-2026` | `tdom/processor_test.py` |
| `t'<a href="{section_url}">{section_name}</a>'` | `section_url='/docs'`, `section_name='Docs'` | 57 | `storyville-2026` | `src/storyville/components/breadcrumbs/breadcrumbs.py` |
| `t"<div data-range={start}-{end}></div>"` | `start=1`, `end=10` | 1144 | `tdom-2026` | `tdom/processor_test.py` |
| `t"<title>A great story; {bool_value}</title>"` | `bool_value=True` | 719 | `tdom-2026` | `tdom/processor_test.py` |

`tainie` was checked (Apache-2.0, real html usage) but contributed no seed
in this pass — the other four sources already covered the target shapes.
Leave it out of `sources.toml` for now rather than add an unused entry; a
future pass can add it when it actually contributes.

---

## Task 1: Register the five new sources

**Files:**
- Modify: `sources.toml`
- Modify: `CORPUS_MACHINERY.md` (add the one-time-exception note)
- Test: `tests/authoring/test_new_sources.py` (new file)

**Interfaces:**
- Consumes: `satyrn_model.authoring.sources.load_sources`,
  `load_policy`, `SourceRecord.validate` (all existing, no changes).
- Produces: `sources.toml` gains five `[[source]]` records with ids
  `regex-template-2026`, `t-sql-2026`, `tdom-2026`, `storyville-2026`,
  `tdom-svcs-2026` — Task 2 references these ids by name.

- [ ] **Step 1: Write the failing test**

Create `tests/authoring/test_new_sources.py`:

```python
"""Task 1: the five new third-party sources for regex/sql/html seeds."""

from satyrn_model.authoring.sources import load_policy, load_sources

NEW_SOURCE_IDS = {
    "regex-template-2026",
    "t-sql-2026",
    "tdom-2026",
    "storyville-2026",
    "tdom-svcs-2026",
}


def test_new_sources_are_registered_and_valid() -> None:
    """Each new source parses, validates, and is a distinct id."""
    policy = load_policy()
    sources = {s.id: s for s in load_sources()}

    missing = NEW_SOURCE_IDS - set(sources)
    assert not missing, f"sources.toml is missing: {missing}"

    for source_id in NEW_SOURCE_IDS:
        source = sources[source_id]
        source.validate(policy=policy)  # raises on bad sha/license
        assert source.source_class == "third-party"
        assert source.extraction_mode == "ast"
        assert source.license == "MIT"


def test_cpython_source_is_unaffected() -> None:
    """Adding third-party sources doesn't disturb the existing CPython one."""
    sources = {s.id: s for s in load_sources()}
    cpython = sources["cpython-v3.14.5"]
    assert cpython.source_class == "cpython"
    assert cpython.tag == "v3.14.5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_new_sources.py -v`
Expected: FAIL — `missing` is non-empty (`sources.toml` doesn't have these
ids yet).

- [ ] **Step 3: Add the five `[[source]]` records**

Append to `sources.toml`, after the existing `[[source]]` block (keep the
`[source.expected_contribution]` sub-table style already used for cpython):

```toml
[[source]]
id = "regex-template-2026"
url = "https://github.com/treyhunner/regex-template"
sha = "f4ea6979113623760153eb6666a3aacdbe681fa3"
license = "MIT"
attribution = "Trey Hunner (github.com/treyhunner). regex-template, commit f4ea6979113."
source_class = "third-party"
extraction_mode = "ast"

[source.expected_contribution]
literals = ">=0"

[[source]]
id = "t-sql-2026"
url = "https://github.com/nhumrich/t-sql"
sha = "01275e310804ff4409aa206afd4b2ddae5082ecd"
license = "MIT"
attribution = "Nick Humrich (github.com/nhumrich). t-sql, commit 01275e31080."
source_class = "third-party"
extraction_mode = "ast"

[source.expected_contribution]
literals = ">=0"

[[source]]
id = "tdom-2026"
url = "https://github.com/ianjosephwilson/tdom"
sha = "98264091b3154a36f4af2e205ac6c3b7c793fb20"
license = "MIT"
attribution = "Ian Wilson (github.com/ianjosephwilson). tdom, commit 982640913."
source_class = "third-party"
extraction_mode = "ast"

[source.expected_contribution]
literals = ">=0"

[[source]]
id = "storyville-2026"
url = "https://github.com/pauleveritt/storyville"
sha = "5fe71ce49dcf15674dbda063135f8dd4a3a9c954"
license = "MIT"
attribution = "Paul Everitt (github.com/pauleveritt). storyville, commit 5fe71ce49dc."
source_class = "third-party"
extraction_mode = "ast"

[source.expected_contribution]
literals = ">=0"

[[source]]
id = "tdom-svcs-2026"
url = "https://github.com/pauleveritt/tdom-svcs"
sha = "d2f6e3a1f7f0ff9295fe596ea29316e024c3befd"
license = "MIT"
attribution = "Paul Everitt (github.com/pauleveritt). tdom-svcs, commit d2f6e3a1f7f."
source_class = "third-party"
extraction_mode = "ast"

[source.expected_contribution]
literals = ">=0"
```

Note: these TOML tables have no `notice` field. `sources.toml`'s
`require_notice_for_license_text` policy flag only requires `notice` when a
source's license text must be reproduced verbatim (the way PSF-2.0's does
for cpython); MIT attribution is satisfied by the `attribution` line alone,
matching how `SourceRecord.notice` is `None`-able in the dataclass.

Then add this paragraph to `CORPUS_MACHINERY.md`, immediately after the
existing "earlier revision spent most of a build cycle mining a third-party
library (`tdom`)" sentence in the "Sourcing" bullet of "The pipeline, in
order":

```markdown
  **One-time exception (2026-08-09):** five third-party, MIT-licensed
  sources (`regex-template-2026`, `t-sql-2026`, `tdom-2026`,
  `storyville-2026`, `tdom-svcs-2026`) were admitted for regex/sql/html
  seeds, since no stdlib module uses t-strings for those domains yet. Each
  was checked against the same failure mode the `tdom` incident exposed —
  does it teach the language feature or a library's API surface — and two
  near-misses (`pgjones/sql-tstring`, `ilotoki0804/tstr`) were rejected for
  not using real PEP 750 syntax at all. See
  `docs/superpowers/specs/2026-08-09-sp5-seed-sourcing-design.md` for the
  full record. This does not reopen the stdlib-only rule as a standing
  policy — future third-party sources need the same review.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_new_sources.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing source test suite to confirm no regressions**

Run: `uv run python -m pytest tests/authoring/test_sources.py -v`
Expected: PASS (unchanged — most of these tests exercise `SourceRecord`/
`sources.py` directly with in-process fixtures, not the committed manifest.
Two tests — `test_records_all_source_attribution` and
`test_rejects_disallowed_license` — do call `load_sources()`/
`load_policy()` on the committed `sources.toml`, but they're generic over
whatever entries it contains, so the five new ones don't change their
outcome. The network-marked `TestRealManifest` class is skipped by default
and untouched by this task).

- [ ] **Step 6: Commit**

```bash
git add sources.toml CORPUS_MACHINERY.md tests/authoring/test_new_sources.py
git commit -m "Register five third-party sources for regex/sql/html seeds"
```

---

## Task 2: Wire the 24 seed occurrences into the extraction script

**Files:**
- Modify: `scripts/rebuild_seed_artifacts.py`
- Modify (generated by running the script): `seeds/occurrences.jsonl`,
  `seeds/extracted.jsonl`
- Test: `tests/authoring/test_third_party_seeds.py` (new file, created in
  Step 1 below)

Running this task's script also makes `tests/authoring/test_seed_artifacts.py`
fail (its hardcoded counts of 10/44 no longer match reality) — that's
expected per the Global Constraints note above, and is fixed in Task 4, not
here.

**Interfaces:**
- Consumes: `satyrn_model.authoring.models.{SeedOccurrence, SourceOrigin,
  occurrence_id, seed_id}`, `satyrn_model.authoring.seeds.{normalize_seeds,
  write_occurrences_jsonl, write_seeds_jsonl}` — all unchanged, all already
  imported by `rebuild_seed_artifacts.py`.
- Produces: `seeds/extracted.jsonl` grows from 10 to 34 seeds;
  `seeds/occurrences.jsonl` grows from 10 to 34 occurrences. Task 3 and
  Task 4 both depend on this new count (34).

- [ ] **Step 1: Write the failing test**

Create `tests/authoring/test_third_party_seeds.py`:

```python
"""Task 2: the 24 third-party regex/sql/html seeds resolve correctly."""

from pathlib import Path

from satyrn_model.authoring.models import occurrence_id, seed_id
from satyrn_model.authoring.seeds import read_occurrences_jsonl, read_seeds_jsonl

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_NEW_LITERALS = {
    't"^{filename}$"',
    't"{regex_part:safe}_{literal_part}"',
    't"value_{number:03d}"',
    't"{value:.1f}"',
    't"{value!r}"',
    't"{start:safe}{filename}{end:safe}"',
    't"{digit_pattern:safe}-{word_pattern:safe}"',
    't"^{pattern_template:safe}{{{count}}}$"',
    "t'SELECT *, ({subquery}) as post_user FROM users'",
    "t'SELECT * FROM users WHERE id = {5} AND post_count > ({subquery})'",
    "t'SELECT id FROM tree UNION ALL SELECT id+1 FROM tree WHERE id < 10'",
    't"SELECT * FROM users WHERE name LIKE {search:%like%}"',
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_third_party_seeds.py -v`
Expected: FAIL — `seeds/extracted.jsonl` doesn't have these literals yet
(still just the 10 CPython ones).

- [ ] **Step 3: Extend `scripts/rebuild_seed_artifacts.py`**

Add this table and helper after the existing `CPYTHON_SEEDS` constant
(around line 42), and thread it into `main()`:

```python
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
        (
            't"{regex_part:safe}_{literal_part}"',
            (("regex_part", "'[0-9]+'"), ("literal_part", "'end'")),
        ),
        94,
        94,
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
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        (
            't"{start:safe}{filename}{end:safe}"',
            (("start", "'^'"), ("filename", "'log.txt'"), ("end", "'$'")),
        ),
        120,
        120,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        (
            't"{digit_pattern:safe}-{word_pattern:safe}"',
            (("digit_pattern", "'[0-9]+'"), ("word_pattern", "'[a-z]+'")),
        ),
        151,
        151,
        "regex",
    ),
    (
        "regex-template-2026",
        "tests/test_regex_template.py",
        (
            't"^{pattern_template:safe}{{{count}}}$"',
            (("pattern_template", "'[a-z]'"), ("count", "3")),
        ),
        171,
        171,
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
        "tests/test_like_patterns.py",
        (
            't"SELECT * FROM users WHERE name LIKE {search:%like%}"',
            (("search", "'jsmith'"),),
        ),
        14,
        14,
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
)

_THIRD_PARTY_LICENSES = {
    "regex-template-2026": "MIT",
    "t-sql-2026": "MIT",
    "tdom-2026": "MIT",
    "storyville-2026": "MIT",
    "tdom-svcs-2026": "MIT",
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
```

Then update `main()` to combine both occurrence sets:

```python
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
```

- [ ] **Step 4: Run the script**

Run: `uv run python scripts/rebuild_seed_artifacts.py`
Expected output: `rebuilt 34 extracted occurrences; quarantined unresolved
HTML candidates`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_third_party_seeds.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/rebuild_seed_artifacts.py seeds/occurrences.jsonl seeds/extracted.jsonl tests/authoring/test_third_party_seeds.py
git commit -m "Add 24 third-party seed occurrences for regex/sql/html"
```

---

## Task 3: Record review decisions for the 24 new seeds

**Files:**
- Modify: `review/decisions.jsonl`
- Test: `tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content`
  (existing test — this task makes it pass again after Task 2 changed the
  active seed set; no test file changes in this task)

**Interfaces:**
- Consumes: `satyrn_model.authoring.review.{ReviewDecision, write_decisions,
  read_decisions, seed_content_sha256}` (all existing, unchanged).
- Produces: `review/decisions.jsonl` grows from 44 to 68 entries — Task 4's
  count assertions depend on this.

- [ ] **Step 1: Run the existing test to confirm it now fails**

Task 2 already grew the active seed set to 68 (44 + 24), so this
already-existing test should now fail without any edits — confirm that
before writing new code:

Run: `uv run python -m pytest tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content -v`
Expected: FAIL — `set(decisions) == {seed.id for seed in seeds}` fails
because 24 new seed ids have no decision yet.

- [ ] **Step 2: Write a one-off script to append the 24 decisions**

Create `scripts/add_third_party_review_decisions.py`:

```python
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
    't"{regex_part:safe}_{literal_part}"',
    't"value_{number:03d}"',
    't"{value:.1f}"',
    't"{value!r}"',
    't"{start:safe}{filename}{end:safe}"',
    't"{digit_pattern:safe}-{word_pattern:safe}"',
    't"^{pattern_template:safe}{{{count}}}$"',
    "t'SELECT *, ({subquery}) as post_user FROM users'",
    "t'SELECT * FROM users WHERE id = {5} AND post_count > ({subquery})'",
    "t'SELECT id FROM tree UNION ALL SELECT id+1 FROM tree WHERE id < 10'",
    't"SELECT * FROM users WHERE name LIKE {search:%like%}"',
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
```

Note: `seed_content_sha256(seed)` is defined as `seed_id(seed.literal,
seed.bindings)`, which is exactly `Seed.id` already (see
`authoring/models.py`'s `seed_id` and `authoring/review.py`'s
`seed_content_sha256`) — so `content_sha256=seed.id` is correct without
importing `seed_content_sha256` itself.

- [ ] **Step 3: Run the script**

Run: `uv run python scripts/add_third_party_review_decisions.py`
Expected output: `appended 24 review decisions`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add review/decisions.jsonl scripts/add_third_party_review_decisions.py
git commit -m "Record accepted review decisions for the 24 third-party seeds"
```

---

## Task 4: Update the hardcoded seed-count tests and confirm domain floors

**Files:**
- Modify: `tests/authoring/test_seed_artifacts.py`

**Interfaces:**
- Consumes: nothing new — this task only updates assertions in an existing
  test file to match the counts Tasks 2 and 3 already produced.
- Produces: nothing consumed by later tasks — this is the closing task.

- [ ] **Step 1: Run the full existing suite to see the current failures**

Run: `uv run python -m pytest tests/authoring/test_seed_artifacts.py -v`
Expected: two failures —
`test_extracted_seeds_resolve_to_pinned_source_occurrences` (asserts
`len(seeds) == len(occurrences) == 10`, now 34) and
`test_active_seeds_have_explicit_reviewed_domains` (asserts
`len(records) == 44`, now 68). Everything else should already pass (Task 3
fixed the review-decisions test).

- [ ] **Step 2: Update the two failing assertions**

In `tests/authoring/test_seed_artifacts.py`, change:

```python
def test_extracted_seeds_resolve_to_pinned_source_occurrences() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occurrence.id: occurrence
        for occurrence in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }
    sources = {source.id: source for source in load_sources(ROOT / "sources.toml")}

    assert len(seeds) == len(occurrences) == 10
```

to:

```python
def test_extracted_seeds_resolve_to_pinned_source_occurrences() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occurrence.id: occurrence
        for occurrence in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }
    sources = {source.id: source for source in load_sources(ROOT / "sources.toml")}

    assert len(seeds) == len(occurrences) == 34
```

(Keep every line below `assert len(seeds) == ...` unchanged — the loop body
already checks each seed generically, no per-source special-casing needed
since `sources` now includes the five new ids and `occurrence.origin.license
== source.license` holds for all of them.)

And change:

```python
def test_active_seeds_have_explicit_reviewed_domains() -> None:
    records = [
        json.loads(line)
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(records) == 44
```

to:

```python
def test_active_seeds_have_explicit_reviewed_domains() -> None:
    records = [
        json.loads(line)
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(records) == 68
```

- [ ] **Step 3: Add a new test asserting the domain floors this plan exists to hit**

Append to `tests/authoring/test_seed_artifacts.py`:

```python
def test_regex_sql_html_reach_their_domain_floors() -> None:
    """SP5_SCALE_BRIEF.md Priority 1: bring regex/sql/html to 12-15+ seeds.

    This plan brought regex from 3 to 11, sql from 7 to 15, html from 7 to
    15 -- the exact per-domain deltas the design doc's seed table lists.
    """
    import collections

    records = [
        json.loads(line)
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    counts = collections.Counter(record["domain"] for record in records)

    assert counts["regex"] >= 11, counts["regex"]
    assert counts["sql"] >= 15, counts["sql"]
    assert counts["html"] >= 15, counts["html"]
```

- [ ] **Step 4: Run the full test suite to verify everything passes**

Run: `uv run python -m pytest tests/authoring/ -v`
Expected: PASS, all tests including the new
`test_regex_sql_html_reach_their_domain_floors`.

- [ ] **Step 5: Commit**

```bash
git add tests/authoring/test_seed_artifacts.py
git commit -m "Update seed-count assertions and add regex/sql/html domain-floor test"
```

---

## What this plan does not do

Matches the design doc's "What this does not do": no pattern authoring, no
`composition.toml`/`sampling.toml` changes, no `construct`/
`compose_templates` population, no logging seeds. `Domain =
Literal["sql", "html", "logging", "regex", "text", "data"]` in `models.py`
is unchanged — logging stays at its current 4 seeds until a follow-on plan
takes it on.
