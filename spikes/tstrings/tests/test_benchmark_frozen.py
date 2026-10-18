"""Verify the frozen benchmark artifacts have not changed."""

import hashlib
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"
OOD_V2_DIR = BENCHMARK_DIR / "ood-v2"

DOCS_CONTEXT_SHA256 = "582c42a688a406abe9494705dde670964a23d5512b8d0d11a6679c60c2f50f31"


def _sha256(path: Path) -> str:
    """Return the lowercase hex sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_tasks_fingerprint_matches() -> None:
    """The tasks.jsonl sha256 must equal fingerprint.txt."""
    fingerprint = (OOD_V2_DIR / "fingerprint.txt").read_text().strip()
    assert _sha256(OOD_V2_DIR / "tasks.jsonl") == fingerprint


def test_tasks_has_exactly_100_lines() -> None:
    """The benchmark is exactly 100 tasks."""
    assert len((OOD_V2_DIR / "tasks.jsonl").read_text().splitlines()) == 100


def test_docs_context_is_frozen() -> None:
    """The docs-in-context block is byte-identical to its pinned sha256."""
    docs = BENCHMARK_DIR / "pep750-docs-context-v3.md"
    assert docs.stat().st_size == 5588
    assert _sha256(docs) == DOCS_CONTEXT_SHA256
