"""Tests for the role x capability curriculum selector (repair steps 3 and 4).

The superseded selector enforced only global marginals, so a 12% ``strings``
quota was filled 44/7 in favour of author rows and twenty approved patterns
were never sampled.  These tests pin the cell structure that replaces it.
"""

import collections
import json
from pathlib import Path

import pytest
from spike.build_curriculum import (
    CELLS,
    CONTRAST_GROUPS,
    DOMAIN_TARGETS,
    FAMILIES,
    ROLE_TARGETS,
    SOURCE_KIND_TARGETS,
    CurriculumError,
    coverage,
    seed_diversity,
    select,
)

SP5_ROOT = Path(__file__).resolve().parents[2] / "sp5-corpus-brainstorm"
CANDIDATES = SP5_ROOT / "reports/pilot-candidates.jsonl"

DOMAINS = ("sql", "html", "logging", "regex", "text", "data")


def _pool() -> list[dict]:
    """A synthetic pool with *overlapping but unequal* seed universes.

    Giving every pattern the same seeds makes seed sharing behaviourally
    identical to each pattern independently taking the same prefix, so no
    assertion on the output can tell them apart — an earlier version of this
    fixture did exactly that and the contrast test passed with the sharing
    mechanism removed. Punching pattern-specific holes in the universe makes
    the property observable: only a genuinely shared allocation lands every
    group member on the same seeds.
    """
    rows = []
    patterns = sorted({pattern for cell in CELLS for pattern, _ in cell.patterns})
    for pattern_index, pattern in enumerate(patterns):
        for seed_index in range(40):
            if (seed_index + pattern_index) % 7 == 0:
                continue
            seed = f"seed-{seed_index:03d}"
            for family in FAMILIES:
                rows.append(
                    {
                        "row_id": f"{pattern}:{seed}:{family}",
                        "pattern_id": pattern,
                        "seed_id": seed,
                        "prompt_family": family,
                        "domain": DOMAINS[seed_index % len(DOMAINS)],
                        "source_kind": (
                            "extracted" if seed_index % 5 == 0 else "authored"
                        ),
                        "role": "author" if "author" in pattern else "consumer",
                        "operation": pattern,
                        "property": "select_result",
                    }
                )
    return rows


def _real_inputs() -> tuple[list[dict], set[str]]:
    """The approved pool and approval ledger from the sibling SP5 worktree."""
    candidates = [json.loads(line) for line in CANDIDATES.read_text().splitlines()]
    approved = {
        json.loads(line)["pattern_id"]
        for line in (SP5_ROOT / "patterns/approvals.jsonl").read_text().splitlines()
    }
    return candidates, approved


def _approved() -> set[str]:
    return {pattern for cell in CELLS for pattern, _ in cell.patterns}


def test_every_declared_cell_is_filled_exactly() -> None:
    selected = select(_pool(), _approved())

    counts = collections.Counter(row["pattern_id"] for row in selected)
    expected = collections.Counter()
    for cell in CELLS:
        for pattern, count in cell.patterns:
            expected[pattern] += count

    assert counts == expected
    assert len(selected) == sum(cell.size for cell in CELLS)
    assert len({row["row_id"] for row in selected}) == len(selected)


def test_balanced_cells_are_split_evenly_across_prompt_families() -> None:
    """Capability must not correlate with framing in training either."""
    selected = select(_pool(), _approved())
    by_capability = collections.defaultdict(collections.Counter)
    for row in selected:
        by_capability[row["capability"]][row["prompt_family"]] += 1

    balanced = {cell.capability for cell in CELLS if cell.family_balanced}
    for capability in balanced:
        families = by_capability[capability]
        assert set(families) == set(FAMILIES)
        assert len(set(families.values())) == 1, capability


def test_contrast_groups_share_one_seed_set() -> None:
    """The contrast is carried by the instruction, not by a different example.

    The fixture gives group members overlapping but unequal seed universes, so
    a selector that takes each pattern's own prefix lands them on different
    seeds and fails here. See `_pool` for why an equal-universe fixture cannot
    detect that regression.
    """
    selected = select(_pool(), _approved())
    seeds_by_pattern = collections.defaultdict(set)
    for row in selected:
        seeds_by_pattern[row["pattern_id"]].add(row["seed_id"])

    for group, members in CONTRAST_GROUPS.items():
        present = [seeds_by_pattern[p] for p in members if seeds_by_pattern[p]]
        assert len(present) > 1, group
        smallest = min(present, key=len)
        for seeds in present:
            assert smallest <= seeds, group
        union = set().union(*present)
        assert union == max(present, key=len), group


def test_curriculum_does_not_collapse_onto_a_few_seeds() -> None:
    """Prefix-taking put 89% of a 504-row curriculum on five seeds."""
    selected = select(_pool(), _approved())

    report = seed_diversity(selected)

    assert report["distinct_seeds"] >= 20
    assert report["max_seed_share"] < 0.10
    assert report["top5_share"] < 0.35


def test_contrast_seeds_do_not_monopolise_the_curriculum() -> None:
    """Sharing seeds across a contrast group must not shrink overall content."""
    selected = select(_pool(), _approved())

    contrast_members = {p for members in CONTRAST_GROUPS.values() for p in members}
    contrast_seeds = {
        row["seed_id"] for row in selected if row["pattern_id"] in contrast_members
    }
    other_seeds = {
        row["seed_id"] for row in selected if row["pattern_id"] not in contrast_members
    }

    assert other_seeds - contrast_seeds, "non-contrast cells reused only group seeds"


def test_unapproved_patterns_are_refused() -> None:
    approved = _approved() - {"intro-strings"}

    with pytest.raises(CurriculumError, match="not an approved pattern"):
        select(_pool(), approved)


def test_a_cell_that_cannot_be_filled_fails_closed() -> None:
    """Under-filling silently is what produced the original skew."""
    thin = [row for row in _pool() if row["seed_id"] < "seed-002"]

    with pytest.raises(CurriculumError, match="complete seeds"):
        select(thin, _approved())


@pytest.mark.skipif(
    not CANDIDATES.exists(), reason="SP5 candidate pool worktree not present"
)
def test_real_pool_fixes_the_role_by_capability_skew() -> None:
    """Against the real pool, the cells the review named are no longer lopsided."""
    selected = select(*_real_inputs())
    report = coverage(selected)
    cells = collections.Counter(
        (row["cell_role"], row["operation"]) for row in selected
    )

    # The reviewed curriculum was 7 consumer / 44 author on `strings` and
    # 13 / 41 on `values`. Assert the property that was broken — the consumer
    # side is no longer starved relative to the author side — rather than the
    # exact counts, which are a tuning decision and change between iterations.
    for operation in ("strings", "values"):
        consumer = cells[("consumer", operation)]
        author = cells[("author", operation)]
        assert consumer >= author, (operation, consumer, author)
        assert consumer > 0 and author > 0

    # Interpolation-field extraction had no rows at all.
    assert cells[("consumer", "interpolations")] > 0

    roles = report["marginals"]["role"]["counts"]
    assert roles["consumer"] + roles["author"] == sum(cell.size for cell in CELLS)
    assert 0.25 <= roles["author"] / sum(roles.values()) <= 0.33


@pytest.mark.skipif(
    not CANDIDATES.exists(), reason="SP5 candidate pool worktree not present"
)
def test_enforceable_marginals_stay_on_profile() -> None:
    """Fixing the capability cells must not quietly wreck the other strata.

    The first cut of this selector left domain at 9.5% sql against a 20%
    target and 89% of rows on five seeds, and `coverage()` reported neither.
    Property and operation are deliberately off profile and are excluded here.

    `role` was excluded too, with no justification, and drifted to -2.8pp
    unpoliced while both other dimensions were held. It is checked now: the
    render cells are role-skewed, so every change to their weights moves it.
    """
    selected = select(*_real_inputs())
    report = coverage(selected)

    for dimension, targets in (
        ("domain", DOMAIN_TARGETS),
        ("source_kind", SOURCE_KIND_TARGETS),
        ("role", ROLE_TARGETS),
    ):
        shares = report["marginals"][dimension]["shares"]
        for label, target in targets.items():
            assert abs(shares.get(label, 0.0) - target) <= 0.03, (dimension, label)

    diversity = report["seed_diversity"]
    assert diversity["distinct_seeds"] >= 40
    assert diversity["top5_share"] <= 0.30


@pytest.mark.skipif(
    not CANDIDATES.exists(), reason="SP5 candidate pool worktree not present"
)
def test_no_approved_pattern_is_left_unsampled() -> None:
    """Twenty approved patterns were sampled zero times by the old selector."""
    selected = select(*_real_inputs())
    sampled = {row["pattern_id"] for row in selected}

    previously_unsampled = {
        "author-static-parts",
        "author-values",
        "author-render-template",
        "author-render-explicit-function",
        "author-interpolations",
        "author-expressions",
        "author-format-specs",
        "contrast-strings",
        "contrast-values",
        "intro-interpolations",
        "intro-expressions",
        "intro-conversions",
        "intro-format-specs",
        "render-template",
        "render-template-explicit-function",
    }
    assert previously_unsampled <= sampled


@pytest.mark.skipif(
    not CANDIDATES.exists(), reason="SP5 candidate pool worktree not present"
)
def test_no_approved_render_pattern_is_left_unsampled() -> None:
    """The hardcoded list above never named `render-subskill-render_template`.

    So the cell table could drop the one pattern that practises rendering a
    whole template — 132 approved rows over 44 seeds — and every test still
    passed. Rendering is the single capability that failed in every
    configuration on both base models, which makes that the most expensive
    gap the suite could have missed. Assert the property instead of a list.
    """
    candidates, approved = _real_inputs()
    sampled = {row["pattern_id"] for row in select(candidates, approved)}
    render = {
        row["pattern_id"]
        for row in candidates
        if row.get("property") == "render_subskill"
    }

    assert render <= sampled, f"unsampled render patterns: {sorted(render - sampled)}"


@pytest.mark.skipif(
    not CANDIDATES.exists(), reason="SP5 candidate pool worktree not present"
)
def test_diversify_widens_program_shape_coverage() -> None:
    """`diversify` must spread *shapes*, which spreading seeds does not do.

    A pattern's seeds collapse onto far fewer skeletons than seeds, so a
    seed-spread curriculum still repeats structure: the shipped selector
    reached 103 of the pool's 270 shapes with one shape repeated 30 times.
    """
    candidates, approved = _real_inputs()

    def shapes(rows: list[dict]) -> collections.Counter:
        return collections.Counter(row["skeleton"] for row in rows)

    plain = shapes(select(candidates, approved))
    wide = shapes(select(candidates, approved, diversify=True))

    assert len(wide) > len(plain)
    # The point is fewer heavy repeats, not merely a larger set.
    assert max(wide.values()) < max(plain.values())
    # Absolute floors as well as a relative gain: without them a future cell
    # edit could halve both numbers and still satisfy `wide > plain`.
    assert len(wide) >= 130, len(wide)
    assert max(wide.values()) <= 12, max(wide.values())
