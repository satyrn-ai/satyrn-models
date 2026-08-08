"""Quarantine records keep retired examples inert and provenance-marked."""

import dataclasses
from pathlib import Path

from satyrn_model.quarantine import QuarantineRecord, read_jsonl, write_jsonl


def make_record(record_id: str = "example-one") -> QuarantineRecord:
    return QuarantineRecord(
        id=record_id,
        description="create a template string and check its type",
        code='name = "World"\ntemplate = t"Hello {name}"\n',
        reason="legacy hand-written example, F-CONTAM source",
    )


def test_provenance_defaults_to_unverified() -> None:
    assert make_record().provenance == "unverified"


def test_record_is_frozen() -> None:
    assert QuarantineRecord.__dataclass_params__.frozen


def test_record_has_no_hidden_test_field() -> None:
    field_names = {field.name for field in dataclasses.fields(QuarantineRecord)}

    assert "hidden_test" not in field_names


def test_jsonl_round_trip(tmp_path: Path) -> None:
    records = [make_record("example-one"), make_record("example-two")]
    path = tmp_path / "quarantine.jsonl"

    write_jsonl(path, records)

    assert read_jsonl(path) == records


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "quarantine.jsonl"
    write_jsonl(path, [make_record()])
    path.write_text(path.read_text() + "\n\n")

    assert len(read_jsonl(path)) == 1
