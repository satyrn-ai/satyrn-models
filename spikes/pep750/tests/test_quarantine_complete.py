"""Guard the complete legacy archive before the source files are retired."""

from pathlib import Path

from satyrn_model.quarantine import read_jsonl

QUARANTINE = Path("corpus/quarantine/legacy-examples-2025-unverified.jsonl")


def test_all_24_examples_are_quarantined() -> None:
    assert len(read_jsonl(QUARANTINE)) == 24


def test_every_record_has_unique_id() -> None:
    records = read_jsonl(QUARANTINE)
    ids = [record.id for record in records]

    assert len(set(ids)) == len(ids)


def test_every_record_has_content_and_unverified_provenance() -> None:
    for record in read_jsonl(QUARANTINE):
        assert record.description.strip(), f"{record.id}: empty description"
        assert record.code.strip(), f"{record.id}: empty code"
        assert record.provenance == "unverified", f"{record.id}: wrong provenance"


def test_no_record_carries_the_contaminating_header() -> None:
    for record in read_jsonl(QUARANTINE):
        assert "# Python 3.14 t-strings" not in record.code
