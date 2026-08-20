"""Split rendered rows into train and valid by seed lineage."""

import hashlib
import json
from pathlib import Path

_VALID_BUCKETS = "01234567"


def _is_valid_seed(filename: str, line: int) -> bool:
    """Return True when the seed's stable md5 bucket starts with 0-7."""
    digest = hashlib.md5(f"{filename}:{line}".encode()).hexdigest()
    return digest[0] in _VALID_BUCKETS


def lineage_split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (train, valid) with whole (filename, _line) seed groups on one side."""
    train: list[dict] = []
    valid: list[dict] = []
    for row in rows:
        target = valid if _is_valid_seed(row["filename"], row["_line"]) else train
        target.append(row)
    return train, valid


def write_manifest(
    train: list[dict],
    valid: list[dict],
    fingerprints: dict,
    split_rule: str,
    path: Path,
) -> None:
    """Write a manifest with split counts, the fingerprints, and the split rule."""
    manifest = {
        "train_count": len(train),
        "valid_count": len(valid),
        "fingerprints": fingerprints,
        "split_rule": split_rule,
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
