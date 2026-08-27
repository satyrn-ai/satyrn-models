"""Tests for the deterministic lineage split and manifest writer."""

import hashlib
import json
from pathlib import Path

from satyrn.tstrings.split import lineage_split, write_manifest

FINGERPRINTS = {
    "dataset": "d" * 64,
    "rendered": "r" * 64,
    "benchmark": "b" * 64,
    "system-prompt": "s" * 64,
}

SEEDS = [
    ("Lib/test/a.py", 10),
    ("Lib/test/b.py", 20),
    ("Lib/test/c.py", 30),
    ("Lib/test/d.py", 40),
    ("src/lib.rs", 3),
    ("Modules/_string.c", 7),
]


def _row(filename: str, line: int, **extra: object) -> dict:
    return {"filename": filename, "_line": line, "idea": "Render this template.", **extra}


def _is_valid_seed(filename: str, line: int) -> bool:
    digest = hashlib.md5(f"{filename}:{line}".encode()).hexdigest()
    return digest[0] in "01234567"


def _fixture() -> list[dict]:
    rows = [_row(path, line) for path, line in SEEDS]
    rows.append(_row("Lib/test/a.py", 10, code="print('twin')"))
    rows.append(_row("src/lib.rs", 3, code="println!()"))
    return rows


def test_lineage_split_keeps_each_seed_on_one_side() -> None:
    """Rows sharing a (filename, _line) seed never span both train and valid."""
    train, valid = lineage_split(_fixture())
    train_seeds = {(row["filename"], row["_line"]) for row in train}
    valid_seeds = {(row["filename"], row["_line"]) for row in valid}
    assert train_seeds.isdisjoint(valid_seeds)


def test_lineage_split_follows_stable_hash_rule() -> None:
    """A seed's rows land in valid exactly when its md5 bucket starts 0-7."""
    train, valid = lineage_split(_fixture())
    for path, line in SEEDS:
        rows = [row for row in train + valid if (row["filename"], row["_line"]) == (path, line)]
        assert rows, f"seed {path}:{line} vanished from the split"
        assert len(rows) >= 1
        for row in rows:
            if _is_valid_seed(path, line):
                assert row in valid
            else:
                assert row in train
    assert train and valid


def test_lineage_split_deterministic_across_calls() -> None:
    """Repeated splits of the same rows return identical train and valid lists."""
    rows = _fixture()
    first = lineage_split(rows)
    second = lineage_split(rows)
    assert first == second
    assert len(first[0]) + len(first[1]) == len(rows)


def test_write_manifest_counts_and_fingerprints(tmp_path: Path) -> None:
    """The manifest records matching counts, all four fingerprints, and the rule."""
    train = [_row("Lib/test/a.py", 10), _row("Lib/test/a.py", 10)]
    valid = [_row("Lib/test/b.py", 20)]
    rule = "md5(f'{path}:{line}').hexdigest()[0] in '01234567' -> valid"
    path = tmp_path / "manifest.json"
    write_manifest(train, valid, FINGERPRINTS, rule, path)
    data = json.loads(path.read_text())
    assert data["train_count"] == len(train) == 2
    assert data["valid_count"] == len(valid) == 1
    assert data["fingerprints"] == FINGERPRINTS
    assert set(data["fingerprints"]) == {"dataset", "rendered", "benchmark", "system-prompt"}
    assert data["split_rule"] == rule
