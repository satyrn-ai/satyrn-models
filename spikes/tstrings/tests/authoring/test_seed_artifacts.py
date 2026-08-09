"""Committed seed artifacts remain source-resolved and reproducible."""

import collections
import json
from pathlib import Path

from satyrn_model.authoring.models import occurrence_id, seed_id
from satyrn_model.authoring.review import read_decisions, seed_content_sha256
from satyrn_model.authoring.seeds import read_occurrences_jsonl, read_seeds_jsonl
from satyrn_model.authoring.sources import load_sources

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = {"sql", "html", "logging", "regex", "text", "data"}


def test_extracted_seeds_resolve_to_pinned_source_occurrences() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    occurrences = {
        occurrence.id: occurrence
        for occurrence in read_occurrences_jsonl(ROOT / "seeds/occurrences.jsonl")
    }
    sources = {source.id: source for source in load_sources(ROOT / "sources.toml")}

    assert len(seeds) == len(occurrences) == 34
    for seed in seeds:
        assert seed.id == seed_id(seed.literal, seed.bindings)
        assert len(seed.occurrence_ids) == 1
        occurrence = occurrences[seed.occurrence_ids[0]]
        assert occurrence.seed_id == seed.id
        assert occurrence.literal == seed.literal
        assert occurrence.bindings == seed.bindings
        assert occurrence.id == occurrence_id(
            occurrence.origin.source_id,
            occurrence.origin.path,
            occurrence.origin.line_start,
            occurrence.origin.line_end,
        )
        source = sources[occurrence.origin.source_id]
        assert occurrence.origin.license == source.license


def test_exact_source_spelling_and_multiline_literal_are_preserved() -> None:
    seeds = read_seeds_jsonl(ROOT / "seeds/extracted.jsonl")
    literals = {seed.literal for seed in seeds}

    assert 't"{1}"' in literals
    assert 't"No values"' in literals
    assert 't"""Hello,\nworld"""' in literals
    assert 't"""Hello,\\nworld"""' not in literals


def test_active_seeds_have_explicit_reviewed_domains() -> None:
    records = [
        json.loads(line)
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(records) == 68
    assert all(record.get("domain") in DOMAINS for record in records)
    assert {record["domain"] for record in records} == DOMAINS


def test_unresolved_html_records_are_quarantined_as_authored_candidates() -> None:
    path = ROOT / "seeds/quarantine/imported-html-candidates.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines() if line]

    assert len(records) == 25
    assert {record["disposition"] for record in records} == {"authored_candidate"}
    assert {record["quarantine_reason"] for record in records} == {
        "no source-resolved occurrence"
    }


def test_review_decisions_cover_exactly_the_active_seed_content() -> None:
    seeds = [
        seed
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for seed in read_seeds_jsonl(path)
    ]
    decisions = {
        decision.seed_id: decision
        for decision in read_decisions(ROOT / "review/decisions.jsonl")
    }

    assert set(decisions) == {seed.id for seed in seeds}
    for seed in seeds:
        decision = decisions[seed.id]
        assert decision.verdict == "accepted"
        assert decision.content_sha256 == seed_content_sha256(seed)


def test_regex_sql_html_reach_their_domain_floors() -> None:
    """SP5_SCALE_BRIEF.md Priority 1: bring regex/sql/html to 12-15+ seeds.

    This plan brought regex from 3 to 11, sql from 7 to 15, html from 7 to
    15 -- the exact per-domain deltas the design doc's seed table lists.
    """
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
