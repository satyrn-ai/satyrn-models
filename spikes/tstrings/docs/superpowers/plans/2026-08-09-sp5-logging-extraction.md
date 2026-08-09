# SP5 Logging Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 1 new third-party source and 2 new `kind="extracted"` logging
seeds, closing logging's 0-of-6-domains extraction gap, per
`SP5_SCALE_BRIEF.md` Priority 2 and the approved design at
`docs/superpowers/specs/2026-08-09-sp5-logging-extraction-design.md`.

**Architecture:** Same pattern as the prior seed-sourcing branch — a
`[[source]]` record in `sources.toml`, hand-resolved
`(literal, bindings, line_start, line_end, domain)` tuples appended to
`scripts/rebuild_seed_artifacts.py`'s `THIRD_PARTY_SEEDS` table (now with
two third-party licenses tracked), a matching review-decision append, and
updated hardcoded test counts.

**Tech Stack:** Python 3.14, the existing `satyrn_model.authoring` package,
pytest.

## Global Constraints

- Run every command from `spikes/tstrings/`.
- The `[[source]]` `sha` must be the full 40-character commit hash
  `2e644e624f7fafda964d70d2150af4029a8431e2` — the exact commit the design
  doc verified both literals against, not the repo's current HEAD.
- The `url` field must be `https://github.com/t-strings/pep750-examples` —
  the design doc found the locally-vendored clone's `davepeck/`-org remote
  no longer resolves (`git ls-remote` returns "Repository not found").
  Using the stale URL would register an unreachable source.
- `source_class = "third-party"` (hyphen), `extraction_mode = "ast"`,
  `license = "MIT"` — same conventions as the prior branch's five sources.
- Both literals' format specs were pre-verified render-eligible against
  real Python `format()` in the design doc — no format-spec surprises
  expected here, but Task 2's verification step re-confirms this as cheap
  insurance (the prior branch's final review caught this exact class of
  bug after the fact; this plan checks it before merge instead).

---

## Task 1: Register the pep750-examples source

**Files:**
- Modify: `sources.toml`
- Test: `tests/authoring/test_new_sources.py` (existing file from the prior
  branch — this task extends it, doesn't replace it)

**Interfaces:**
- Consumes: `satyrn_model.authoring.sources.{load_sources, load_policy,
  SourceRecord.validate}` (all existing, unchanged).
- Produces: `sources.toml` gains one `[[source]]` record with id
  `pep750-examples-2026` — Task 2 references this id by name.

- [ ] **Step 1: Write the failing test**

Add this test function to the end of `tests/authoring/test_new_sources.py`
(it already has `NEW_SOURCE_IDS` and two test functions from the prior
branch — leave those untouched, just append):

```python
def test_logging_source_is_registered_and_valid() -> None:
    """The pep750-examples source for logging extraction is present and valid."""
    policy = load_policy()
    sources = {s.id: s for s in load_sources()}

    assert "pep750-examples-2026" in sources
    source = sources["pep750-examples-2026"]
    source.validate(policy=policy)
    assert source.source_class == "third-party"
    assert source.extraction_mode == "ast"
    assert source.license == "MIT"
    assert source.url == "https://github.com/t-strings/pep750-examples"
    assert source.sha == "2e644e624f7fafda964d70d2150af4029a8431e2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_new_sources.py::test_logging_source_is_registered_and_valid -v`
Expected: FAIL — `"pep750-examples-2026" in sources` is false.

- [ ] **Step 3: Add the `[[source]]` record**

Append to `sources.toml`, after the existing `tdom-svcs-2026` block (the
last of the five prior-branch entries):

```toml
[[source]]
id = "pep750-examples-2026"
url = "https://github.com/t-strings/pep750-examples"
sha = "2e644e624f7fafda964d70d2150af4029a8431e2"
license = "MIT"
attribution = "Dave Peck (github.com/davepeck, now published under github.com/t-strings). pep750-examples, commit 2e644e624f7."
source_class = "third-party"
extraction_mode = "ast"
notice = """
Copyright (c) 2024 Dave Peck. Licensed under the MIT License.
"""

[source.expected_contribution]
literals = ">=2"
```

The copyright line above (`Copyright (c) 2024 Dave Peck`) was fetched
directly from the pinned commit's real `LICENSE` file, matching the prior
branch's five sources' notice fields — no placeholder text to fill in.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/authoring/test_new_sources.py -v`
Expected: PASS (all tests in the file, including the two from the prior
branch).

- [ ] **Step 5: Commit**

```bash
git add sources.toml tests/authoring/test_new_sources.py
git commit -m "Register pep750-examples source for logging extraction"
```

---

## Task 2: Wire the 2 logging seed occurrences

**Files:**
- Modify: `scripts/rebuild_seed_artifacts.py`
- Modify: `scripts/add_third_party_review_decisions.py`
- Modify (generated): `seeds/occurrences.jsonl`, `seeds/extracted.jsonl`,
  `review/decisions.jsonl`
- Modify: `tests/authoring/test_seed_artifacts.py` (update hardcoded
  counts)
- Test: `tests/authoring/test_third_party_seeds.py` (existing file from
  the prior branch — extend it, don't replace it)

**Interfaces:**
- Consumes: `satyrn_model.authoring.models.{SeedOccurrence, SourceOrigin,
  occurrence_id, seed_id}`, `satyrn_model.authoring.seeds.{normalize_seeds,
  write_occurrences_jsonl, write_seeds_jsonl}`, `satyrn_model.authoring.
  review.{ReviewDecision, read_decisions, write_decisions}` — all existing.
- Produces: `seeds/extracted.jsonl` grows from 34 to 36; total active seeds
  (authored + extracted) grows from 68 to 70; `review/decisions.jsonl`
  grows from 68 to 70.

- [ ] **Step 1: Write the failing test**

Add this test function to the end of
`tests/authoring/test_third_party_seeds.py` (leave the prior branch's
`EXPECTED_NEW_LITERALS` set and existing test functions untouched — this
is additive):

```python
def test_logging_extraction_seeds_are_present_and_source_resolved() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occ.id: occ for occ in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }

    literals = {seed.literal for seed in seeds}
    assert 't"Hello, {name}!"' in literals
    assert 't"${amount:0.2f}"' in literals

    for seed in seeds:
        if seed.literal not in ('t"Hello, {name}!"', 't"${amount:0.2f}"'):
            continue
        assert seed.domain == "logging"
        assert seed.id == seed_id(seed.literal, seed.bindings)
        occ = occurrences[seed.occurrence_ids[0]]
        assert occ.origin.source_id == "pep750-examples-2026"
        assert occ.origin.license == "MIT"


def test_extracted_seed_count_grew_to_thirty_six() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    assert len(seeds) == 36
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/authoring/test_third_party_seeds.py::test_logging_extraction_seeds_are_present_and_source_resolved tests/authoring/test_third_party_seeds.py::test_extracted_seed_count_grew_to_thirty_six -v`
Expected: FAIL — the two literals aren't in `seeds/extracted.jsonl` yet;
count is 34, not 36.

- [ ] **Step 3: Extend `THIRD_PARTY_SEEDS` in `scripts/rebuild_seed_artifacts.py`**

Add two entries to the end of the `THIRD_PARTY_SEEDS` tuple (after the
existing html entries):

```python
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
```

Then add the new source's license to `_THIRD_PARTY_LICENSES` (a dict
literal already in the file from the prior branch):

```python
_THIRD_PARTY_LICENSES = {
    "regex-template-2026": "MIT",
    "t-sql-2026": "MIT",
    "tdom-2026": "MIT",
    "storyville-2026": "MIT",
    "tdom-svcs-2026": "MIT",
    "pep750-examples-2026": "MIT",
}
```

- [ ] **Step 4: Run the script**

Run: `uv run python scripts/rebuild_seed_artifacts.py`
Expected output: `rebuilt 36 extracted occurrences; quarantined unresolved
HTML candidates`

- [ ] **Step 5: Run test to verify the new tests pass**

Run: `uv run python -m pytest tests/authoring/test_third_party_seeds.py -v`
Expected: PASS (all tests in the file, including the prior branch's).

- [ ] **Step 6: Add the 2 review decisions**

`tests/authoring/test_seed_artifacts.py::test_review_decisions_cover_exactly_the_active_seed_content`
will now fail (68 decisions for 70 active seeds). Extend
`scripts/add_third_party_review_decisions.py`'s `THIRD_PARTY_LITERALS` set
to include the two new literals:

```python
THIRD_PARTY_LITERALS = {
    # ... existing 24 entries, unchanged ...
    't"Hello, {name}!"',
    't"${amount:0.2f}"',
}
```

Update the `assert len(seeds) == 24` line in that script to
`assert len(seeds) == 26` (it now selects 26 third-party seeds, not 24).
The rest of the script's logic (the `existing_ids` skip-guard) is
unchanged — running it again only appends the 2 new decisions, since the
24 from the prior branch already have entries.

Run: `uv run python scripts/add_third_party_review_decisions.py`
Expected output: `appended 2 review decisions`

- [ ] **Step 7: Update `tests/authoring/test_seed_artifacts.py`'s hardcoded counts**

Change line 24's `assert len(seeds) == len(occurrences) == 34` to
`assert len(seeds) == len(occurrences) == 36`.

Change line 60's `assert len(records) == 68` to `assert len(records) == 70`.

Leave the domain-floor assertions (`counts["regex"] >= 11`, etc.) alone —
this task doesn't touch those domains. Optionally add one more assertion
to the same test function confirming logging's extraction floor, since
that's what this whole plan exists to establish:

```python
    assert counts["logging"] >= 6, counts["logging"]
```

- [ ] **Step 8: Run the full authoring test suite**

Run: `uv run python -m pytest tests/authoring/ -v`
Expected: PASS, all tests, no failures.

- [ ] **Step 9: Commit**

```bash
git add scripts/rebuild_seed_artifacts.py scripts/add_third_party_review_decisions.py seeds/occurrences.jsonl seeds/extracted.jsonl review/decisions.jsonl tests/authoring/test_third_party_seeds.py tests/authoring/test_seed_artifacts.py
git commit -m "Add 2 logging extraction seeds from pep750-examples"
```

---

## What this plan does not do

Same boundary as the prior branch and the design doc: no pattern
authoring, no `composition.toml`/`sampling.toml` changes, no `construct`/
`compose_templates` population, no additional hand-authored logging seeds.
Logging ends this plan at 6 seeds (4 authored + 2 extracted) — still below
the eventual 12-15 floor `SP5_SCALE_BRIEF.md` calls for; closing that
remains a separate, already-deferred decision.
