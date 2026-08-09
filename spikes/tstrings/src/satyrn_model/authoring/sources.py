"""Source manifest, exact pins, and license policy (SP5 Task 1).

A source record is the committed contract for an admissible t-string source:
an immutable remote URL, a full commit SHA, an allowed SPDX license,
attribution, a source class, an extraction mode, and an expected-contribution
schema. ``sources.toml`` is the committed manifest; this module loads and
validates it.

Two distinct checks live here by design (spec §2.2):

- ``SourceRecord.validate`` / ``assert_source_pin`` validate a *general* source
  pin via the declared SHA (and, for ``assert_source_pin``, the clone cache's
  ``git rev-parse HEAD``). This generalizes to third-party repos.
- ``assert_cpython_verifier`` is the global CPython tag ↔ interpreter
  precondition. It does not generalize to third-party repos and is asserted
  once per run, not per source.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

__all__ = [
    "CpythonVerificationError",
    "SourceRecord",
    "SourcePolicy",
    "SourceValidationError",
    "assert_cpython_verifier",
    "assert_source_pin",
    "emit_inventory",
    "load_policy",
    "load_sources",
    "write_inventory",
]


class SourceValidationError(ValueError):
    """A source record violates the manifest policy."""


class CpythonVerificationError(ValueError):
    """The declared CPython tag does not match the verifying interpreter."""


_CPYTHON_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclasses.dataclass(frozen=True)
class SourcePolicy:
    """The ``[policy]`` block from ``sources.toml``."""

    allowed_licenses: frozenset[str]


def _load_toml(path: Path) -> dict[str, Any]:
    """Read and parse ``sources.toml`` once."""
    resolved = path if path is not None else Path("sources.toml")
    return tomllib.loads(resolved.read_text(encoding="utf-8"))


def load_policy(path: Path | None = None) -> SourcePolicy:
    """Load the ``[policy]`` block from ``sources.toml``."""
    policy = _load_toml(path).get("policy", {})
    return SourcePolicy(
        allowed_licenses=frozenset(policy.get("allowed_licenses", [])),
    )


def load_sources(path: Path | None = None) -> list[SourceRecord]:
    """Load ``[[source]]`` records from ``sources.toml``."""
    source_entries: list[dict[str, Any]] = _load_toml(path).get("source", [])
    return [_source_from_toml(entry) for entry in source_entries]


def _source_from_toml(entry: dict[str, Any]) -> SourceRecord:
    """Build a ``SourceRecord`` from a single TOML ``[[source]]`` entry."""
    return SourceRecord(
        id=entry["id"],
        url=entry["url"],
        sha=entry["sha"],
        license=entry["license"],
        attribution=entry["attribution"],
        source_class=entry["source_class"],
        extraction_mode=entry["extraction_mode"],
        expected_contribution=dict(entry.get("expected_contribution", {})),
        notice=entry.get("notice"),
        tag=entry.get("tag"),
    )


def emit_inventory(
    sources: list[SourceRecord],
) -> dict[str, Any]:
    """Produce a source-inventory dict from validated source records.

    The ``skeletons`` field is ``None`` until populated by extraction (Task 3).
    """
    inventory_sources: dict[str, dict[str, Any]] = {}
    for source in sources:
        inventory_sources[source.id] = {
            "id": source.id,
            "url": source.url,
            "sha": source.sha,
            "license": source.license,
            "attribution": source.attribution,
            "source_class": source.source_class,
            "extraction_mode": source.extraction_mode,
            "expected_contribution": source.expected_contribution,
            "skeletons": None,
        }
    return {
        "sources": inventory_sources,
        "_notice": "\n\n".join(s.notice for s in sources if s.notice),
    }


def write_inventory(
    sources: list[SourceRecord],
    output_dir: Path,
) -> Path:
    """Write ``reports/source-inventory.json`` and return the path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "source-inventory.json"
    path.write_text(
        json.dumps(emit_inventory(sources), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def assert_cpython_verifier(tag: str) -> None:
    """Assert the declared CPython tag matches the verifying interpreter.

    This is the runtime gate that closes F-STALE-CPYTHON: the harvest checkout
    tag (e.g. ``v3.14.5``) must agree with the resolved interpreter version
    (``sys.version_info[:3]``). A minor-only pin is not sufficient (spec §2.2).

    Raises *CpythonVerificationError* on mismatch.
    """
    match = _CPYTHON_TAG.match(tag)
    if match is None:
        raise CpythonVerificationError(
            f"CPython tag {tag!r} does not match expected pattern "
            f"v<major>.<minor>.<patch>"
        )
    declared = (int(match[1]), int(match[2]), int(match[3]))
    running = sys.version_info[:3]
    if declared != running:
        raise CpythonVerificationError(
            f"CPython tag {tag!r} declares {declared!r}, "
            f"but the verifying interpreter is {running!r}"
        )


def assert_source_pin(root: Path, expected_sha: str) -> None:
    """Assert a local clone's HEAD matches the declared immutable SHA.

    Runs ``git -C <root> rev-parse HEAD`` and compares the result to
    *expected_sha*. This is the general pin check; it does **not** perform
    the CPython tag ↔ interpreter check (that is ``assert_cpython_verifier``).

    Raises *SourceValidationError* on mismatch.
    """
    if not _FULL_SHA.match(expected_sha):
        raise SourceValidationError(
            f"expected SHA must be a 40-char hex commit, got {expected_sha!r}"
        )
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    actual_sha = result.stdout.strip()
    if actual_sha != expected_sha:
        raise SourceValidationError(
            f"repo at {root}: HEAD is {actual_sha!r}, "
            f"but the source pin expects {expected_sha!r}"
        )


@dataclasses.dataclass(frozen=True)
class SourceRecord:
    """An admissible, pinned t-string source."""

    id: str
    url: str
    sha: str
    license: str
    attribution: str
    source_class: str
    extraction_mode: str
    expected_contribution: dict[str, Any]
    notice: str | None = None
    tag: str | None = None

    def validate(self, *, policy: SourcePolicy | None = None) -> None:
        """Validate this record against the manifest policy."""
        if not _FULL_SHA.match(self.sha):
            raise SourceValidationError(
                f"source {self.id!r}: sha must be an immutable 40-char commit "
                f"SHA, got {self.sha!r}"
            )
        if policy is not None and self.license not in policy.allowed_licenses:
            raise SourceValidationError(
                f"source {self.id!r}: license {self.license!r} is not in "
                f"the allowed set {sorted(policy.allowed_licenses)!r}"
            )
