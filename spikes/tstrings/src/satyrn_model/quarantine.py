"""Retired examples of unverified provenance.

The legacy examples are F-CONTAM source material. They are intentionally a
different type from provider task records: a quarantine record has no check or
policy fields and its provenance is fixed to ``"unverified"``.
"""

import dataclasses
import json
from pathlib import Path
from typing import Literal


@dataclasses.dataclass(frozen=True)
class QuarantineRecord:
    """An inert, preserved legacy example that cannot be a provider task."""

    id: str
    description: str
    code: str
    reason: str
    provenance: Literal["unverified"] = dataclasses.field(
        default="unverified",
        init=False,
    )


def write_jsonl(path: Path, records: list[QuarantineRecord]) -> None:
    """Write quarantine records as deterministic JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(dataclasses.asdict(record), sort_keys=True))
            output.write("\n")


def read_jsonl(path: Path) -> list[QuarantineRecord]:
    """Read and validate quarantine records, ignoring blank lines."""
    records: list[QuarantineRecord] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.pop("provenance", None) != "unverified":
                raise ValueError("quarantine provenance must be 'unverified'")
            records.append(QuarantineRecord(**data))
    return records
