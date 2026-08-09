# SP5 Data/Logging Seed Floors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 `kind="extracted"` `data`-domain seeds from CPython's own
`Lib/test/test_tstring.py` and 7 `kind="authored"` `logging`-domain seeds,
bringing both domains from 6 to 13 seeds, per `SP5_SCALE_BRIEF.md`
Priority 1 and the approved design at
`docs/superpowers/specs/2026-08-09-sp5-data-logging-floors-design.md`.

**Architecture:** Data seeds reuse the *existing* `THIRD_PARTY_SEEDS` /
`_third_party_occurrences()` mechanism in `scripts/rebuild_seed_artifacts.py`
(built for the earlier third-party-sourcing branch, but generic — it just
needs a `source_id` + `path` + license) with `source_id="cpython-v3.14.5"`,
the source already registered in `sources.toml`. No new `[[source]]`
entry. Logging seeds are directly authored, appended to
`seeds/authored.jsonl` the same way the original 34 authored seeds were
built — no source, no occurrence resolution, just reviewed literals.

**Tech Stack:** Python 3.14, the existing `satyrn_model.authoring` package,
pytest.

## Global Constraints

- Run every command from `spikes/tstrings/`.
- Every data-seed literal must be copied byte-for-byte from the pinned
  `cpython-v3.14.5` commit — these are real CPython test code, already
  proven to execute correctly in CPython's own CI, so (unlike the
  third-party sourcing branches) no independent format-spec validity check
  is needed.
- Every logging-seed format spec must be real, valid Python — verify with
  `format(value, spec)` before committing, the lesson from the earlier
  `:safe`/`:%like%` bug. All specs in this plan are plain (`.2f` or bare),
  already checked.
- `rt"{path}\Documents"` (data seed #7) contains a literal backslash in its
  source text — when writing this as a Python string literal inside the
  script (not itself a raw string), escape it as `'rt"{path}\\Documents"'`.

---

## The 7 data seeds

| literal | line | bindings |
| --- | --- | --- |
| `t"Sum: {a + b}"` | 38 | `a=10`, `b=20` |
| `t"Pi: {value:.2f}"` | 85 | `value=3.14159` |
| `t"Object: {obj!s}"` | 94 | `obj=42` |
| `t"ASCII: {text!a}"` | 105 | `text='Café'` |
| `t"Value: {value=}"` | 117 | `value=3.14159` |
| `t"Value: {value=:.2f}"` | 124 | `value=3.14159` |
| `rt"{path}\Documents"` | 145 | `path='C:'` |

All from `Lib/test/test_tstring.py` at the pinned `cpython-v3.14.5` commit.

## The 7 logging seeds

| literal | bindings |
| --- | --- |
| `t"[DEBUG] {msg}"` | `msg='cache miss'` |
| `t"[WARNING] slow query took {elapsed:.2f}s"` | `elapsed=1.23` |
| `t"[ERROR] request failed with status {status}"` | `status=500` |
| `t"user={user} action={action} status={status}"` | `user='alice'`, `action='login'`, `status='ok'` |
| `t"retrying={retry}"` | `retry=True` |
| `t"{event!r}: id={record_id}"` | `event='order_created'`, `record_id=42` |
| `t"correlation_id={cid} duration_ms={dur}"` | `cid='abc-123'`, `dur=42` |

---

## Task 1: Add the 7 data seeds via CPython extraction

**Files:**
- Modify: `scripts/rebuild_seed_artifacts.py`
- Modify (generated): `seeds/occurrences.jsonl`, `seeds/extracted.jsonl`
- Test: `tests/authoring/test_data_logging_floors.py` (new file, this task
  adds the data-focused tests; Task 2 extends the same file)

**Interfaces:**
- Consumes: `satyrn_model.authoring.models.{SeedOccurrence, SourceOrigin,
  occurrence_id, seed_id}`, `satyrn_model.authoring.seeds.{normalize_seeds,
  write_occurrences_jsonl, write_seeds_jsonl, read_seeds_jsonl,
  read_occurrences_jsonl}` — all existing.
- Produces: `seeds/extracted.jsonl` grows from 36 to 43. Task 3 depends on
  this count.

- [ ] **Step 1: Write the failing test**

Create `tests/authoring/test_data_logging_floors.py`:

```python
"""7 data seeds (CPython extraction) + 7 logging seeds (authored),
closing both domains to the SP5_SCALE_BRIEF.md 12-15 floor. See
docs/superpowers/specs/2026-08-09-sp5-data-logging-floors-design.md."""

from pathlib import Path

from satyrn_model.authoring.models import occurrence_id, seed_id
from satyrn_model.authoring.seeds import read_occurrences_jsonl, read_seeds_jsonl

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_DATA_LITERALS = {
    't"Sum: {a + b}"',
    't"Pi: {value:.2f}"',
    't"Object: {obj!s}"',
    't"ASCII: {text!a}"',
    't"Value: {value=}"',
    't"Value: {value=:.2f}"',
    'rt"{path}\\Documents"',
}


def test_data_seeds_are_present_and_source_resolved() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occ.id: occ for occ in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }

    literals = {seed.literal for seed in seeds}
    missing = EXPECTED_DATA_LITERALS - literals
    assert not missing, f"seeds/extracted.jsonl is missing: {missing}"

    for seed in seeds:
        if seed.literal not in EXPECTED_DATA_LITERALS:
            continue
        assert seed.domain == "data"
        assert seed.id == seed_id(seed.literal, seed.bindings)
        occ = occurrences[seed.occurrence_ids[0]]
        assert occ.origin.source_id == "cpython-v3.14.5"
        assert occ.origin.path == "Lib/test/test_tstring.py"
        assert occ.origin.license == "PSF-2.0"
        assert occ.id == occurrence_id(
            occ.origin.source_id,
            occ.origin.path,
            occ.origin.line_start,
            occ.origin.line_end,
        )


def test_extracted_seed_count_grew_to_forty_three() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    assert len(seeds) == 43
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_data_logging_floors.py -v`
Expected: FAIL — the 7 literals aren't in `seeds/extracted.jsonl` yet;
count is 36, not 43.

- [ ] **Step 3: Extend `THIRD_PARTY_SEEDS` and `_THIRD_PARTY_LICENSES`**

Add these 7 entries to the end of the `THIRD_PARTY_SEEDS` tuple in
`scripts/rebuild_seed_artifacts.py`:

```python
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
```

Then add `cpython-v3.14.5` to `_THIRD_PARTY_LICENSES` (a dict literal
already in the file):

```python
_THIRD_PARTY_LICENSES = {
    "regex-template-2026": "MIT",
    "t-sql-2026": "MIT",
    "tdom-2026": "MIT",
    "storyville-2026": "MIT",
    "tdom-svcs-2026": "MIT",
    "pep750-examples-2026": "MIT",
    "cpython-v3.14.5": "PSF-2.0",
}
```

- [ ] **Step 4: Run the script**

Run: `uv run python scripts/rebuild_seed_artifacts.py`
Expected output: `rebuilt 43 extracted occurrences; quarantined unresolved
HTML candidates`

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_data_logging_floors.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/rebuild_seed_artifacts.py seeds/occurrences.jsonl seeds/extracted.jsonl tests/authoring/test_data_logging_floors.py
git commit -m "Add 7 data-domain seeds extracted from Lib/test/test_tstring.py"
```

---

## Task 2: Add the 7 logging seeds via hand-authoring

**Files:**
- Create: `scripts/add_data_logging_seeds_batch.py`
- Modify (generated by running the script): `seeds/authored.jsonl`
- Test: `tests/authoring/test_data_logging_floors.py` (extend the file
  from Task 1)

**Interfaces:**
- Consumes: `satyrn_model.authoring.models.{Seed, seed_id}`,
  `satyrn_model.authoring.seeds.{read_seeds_jsonl, write_seeds_jsonl}` —
  all existing.
- Produces: `seeds/authored.jsonl` grows from 34 to 41. Task 3 depends on
  this count.

- [ ] **Step 1: Write the failing test**

Add this test function to the end of
`tests/authoring/test_data_logging_floors.py`:

```python
EXPECTED_LOGGING_LITERALS = {
    't"[DEBUG] {msg}"',
    't"[WARNING] slow query took {elapsed:.2f}s"',
    't"[ERROR] request failed with status {status}"',
    't"user={user} action={action} status={status}"',
    't"retrying={retry}"',
    't"{event!r}: id={record_id}"',
    't"correlation_id={cid} duration_ms={dur}"',
}


def test_logging_seeds_are_present_and_authored() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/authored.jsonl")
    literals = {seed.literal for seed in seeds}
    missing = EXPECTED_LOGGING_LITERALS - literals
    assert not missing, f"seeds/authored.jsonl is missing: {missing}"

    for seed in seeds:
        if seed.literal not in EXPECTED_LOGGING_LITERALS:
            continue
        assert seed.domain == "logging"
        assert seed.kind == "authored"
        assert seed.id == seed_id(seed.literal, seed.bindings)


def test_authored_seed_count_grew_to_forty_one() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/authored.jsonl")
    assert len(seeds) == 41
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_data_logging_floors.py::test_logging_seeds_are_present_and_authored tests/authoring/test_data_logging_floors.py::test_authored_seed_count_grew_to_forty_one -v`
Expected: FAIL — the 7 logging literals aren't in `seeds/authored.jsonl`
yet; count is 34, not 41.

- [ ] **Step 3: Write and run the authoring script**

Create `scripts/add_data_logging_seeds_batch.py`:

```python
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
```

Run: `uv run python scripts/add_data_logging_seeds_batch.py`
Expected output: `appended 7 logging seeds`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_data_logging_floors.py -v`
Expected: PASS, all tests in the file (both data and logging).

- [ ] **Step 5: Commit**

```bash
git add scripts/add_data_logging_seeds_batch.py seeds/authored.jsonl tests/authoring/test_data_logging_floors.py
git commit -m "Add 7 hand-authored logging seeds"
```

---

## Task 3: Review decisions and count/floor test updates

**Files:**
- Create: `scripts/add_data_logging_review_decisions.py`
- Modify (generated): `review/decisions.jsonl`
- Modify: `tests/authoring/test_seed_artifacts.py`

**Interfaces:**
- Consumes: `satyrn_model.authoring.review.{ReviewDecision, read_decisions,
  write_decisions}`, `satyrn_model.authoring.seeds.read_seeds_jsonl` — all
  existing.
- Produces: `review/decisions.jsonl` grows from 70 to 84.

- [ ] **Step 1: Confirm the existing coverage test now fails**

Tasks 1 and 2 already grew the active seed set to 84 (43 extracted + 41
authored), so this pre-existing test should already fail:

Run: `uv run python -m pytest tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content -v`
Expected: FAIL — 14 new seed ids have no decision yet.

- [ ] **Step 2: Write and run the review-decisions script**

Create `scripts/add_data_logging_review_decisions.py`:

```python
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
```

Run: `uv run python scripts/add_data_logging_review_decisions.py`
Expected output: `appended 14 review decisions`

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content -v`
Expected: PASS

- [ ] **Step 4: Update the hardcoded counts and domain floors in `tests/authoring/test_seed_artifacts.py`**

Change `assert len(seeds) == len(occurrences) == 36` (in
`test_extracted_seeds_resolve_to_pinned_source_occurrences`) to
`assert len(seeds) == len(occurrences) == 43`.

Change `assert len(records) == 70` (in
`test_active_seeds_have_explicit_reviewed_domains`) to
`assert len(records) == 84`.

In `test_regex_sql_html_reach_their_domain_floors`, change
`assert counts["logging"] >= 6, counts["logging"]` to
`assert counts["logging"] >= 13, counts["logging"]`, and add a new line:
`assert counts["data"] >= 13, counts["data"]` (no floor assertion for
`data` exists yet — this is the first one). Consider renaming the test
function to something like `test_every_domain_reaches_its_floor` since it
no longer covers only regex/sql/html — your call, not required.

- [ ] **Step 5: Run the full authoring test suite**

Run: `uv run python -m pytest tests/authoring/ -v`
Expected: PASS, all tests, no failures.

- [ ] **Step 6: Commit**

```bash
git add scripts/add_data_logging_review_decisions.py review/decisions.jsonl tests/authoring/test_seed_artifacts.py
git commit -m "Record review decisions for the 14 new seeds; update counts and domain floors"
```

---

## What this plan does not do

No pattern authoring, no `composition.toml`/`sampling.toml` changes.
Priority 4 (new patterns generally) remains deferred, now on firmer
ground: after this plan, every domain is at or above its 12-15 floor and
the corpus's seed:pattern ratio is closer to the brief's own ~150-seed /
~70-pattern target proportions (84 seeds / 57 patterns, vs. today's
70/57).
