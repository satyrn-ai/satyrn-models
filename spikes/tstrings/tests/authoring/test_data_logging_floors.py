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
