"""Migrate retired legacy training data into the inert quarantine store.

Run once from the repository root:

    uv run python -m scripts.quarantine_legacy_examples
"""

import json
import re
from pathlib import Path

from satyrn_model.quarantine import QuarantineRecord, write_jsonl

HEADER_PREFIX = "# Python 3.14 t-strings: "
REASON = (
    "Legacy hand-written example from the retired make_data.py. F-CONTAM "
    "source: these descriptions were byte-identical to prompts in the retired "
    "eval.py, so any pass rate measured against them was a memorization score. "
    "Seed material only -- never a corpus row, never a benchmark task."
)
SOURCE = Path("data/pep750.jsonl")
DESTINATION = Path("corpus/quarantine/legacy-examples-2025-unverified.jsonl")


def slugify(description: str) -> str:
    """Return the stable, human-readable ID for a legacy description."""
    return re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")


def parse_legacy_line(line: str) -> QuarantineRecord:
    """Turn one historical training row into an inert quarantine record."""
    text = json.loads(line)["text"]
    header, separator, code = text.partition("\n")
    if not separator or not header.startswith(HEADER_PREFIX):
        raise ValueError(f"unexpected header: {header!r}")
    description = header.removeprefix(HEADER_PREFIX)
    return QuarantineRecord(
        id=slugify(description),
        description=description,
        code=code,
        reason=REASON,
    )


def migrate(
    *, source: Path = SOURCE, destination: Path = DESTINATION
) -> list[QuarantineRecord]:
    """Read every historical row, reject ID loss, and write all records."""
    records = [
        parse_legacy_line(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [record.id for record in records]
    duplicates = sorted({record_id for record_id in ids if ids.count(record_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate quarantine ids: {duplicates}")
    write_jsonl(destination, records)
    return records


def main() -> int:
    records = migrate()
    print(f"Quarantined {len(records)} records to {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
