"""Provenance: source-kind-tagged union for harvested and generated rows.

Each provenance kind carries only the fields that genuinely apply to it. A
harvested row records where it came from and under which interpreter it was
verified; a generated row records which generator and seed produced it. There
is no single ``Provenance`` dataclass padded with optional "just in case"
fields, because such padding is exactly how a fictional field (e.g. an upstream
ref on a synthetic row) would slip through review as plausible-looking noise.

This union is closed: a new source kind is a contract change, not a free
parameter, and ingest rejects unknown kinds.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from ._common import (
    ContractError,
    reject_unknown_keys,
    require_fields,
    require_object,
    require_str,
)

HARVESTED = "harvested"
GENERATED = "generated"


@dataclasses.dataclass(frozen=True, kw_only=True)
class HarvestedProvenance:
    """A row harvested from real, pinned source material."""

    kind: Literal["harvested"] = dataclasses.field(default=HARVESTED)
    source_file: str
    upstream_ref: str  # upstream tag or commit, e.g. "v3.14.5"
    interpreter_version: str  # the verifying interpreter version, e.g. "3.14.5"

    @classmethod
    def from_dict(cls, data: object) -> HarvestedProvenance:
        data = require_object(data, "harvested provenance")
        require_fields(
            data,
            ("source_file", "upstream_ref", "interpreter_version"),
            "harvested provenance",
        )
        reject_unknown_keys(
            data,
            frozenset({"kind", "source_file", "upstream_ref", "interpreter_version"}),
            "harvested provenance",
        )
        return cls(
            source_file=require_str(data["source_file"], "source_file"),
            upstream_ref=require_str(data["upstream_ref"], "upstream_ref"),
            interpreter_version=require_str(
                data["interpreter_version"], "interpreter_version"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_file": self.source_file,
            "upstream_ref": self.upstream_ref,
            "interpreter_version": self.interpreter_version,
        }


@dataclasses.dataclass(frozen=True, kw_only=True)
class GeneratedProvenance:
    """A row produced by a generator, optionally seeded from a known seed."""

    kind: Literal["generated"] = dataclasses.field(default=GENERATED)
    generator: str
    generator_version: str
    seed_id: str | None = None

    @classmethod
    def from_dict(cls, data: object) -> GeneratedProvenance:
        data = require_object(data, "generated provenance")
        require_fields(data, ("generator", "generator_version"), "generated provenance")
        reject_unknown_keys(
            data,
            frozenset({"kind", "generator", "generator_version", "seed_id"}),
            "generated provenance",
        )
        seed_id = data.get("seed_id")
        if seed_id is not None and (not isinstance(seed_id, str) or not seed_id):
            raise ContractError("seed_id must be a non-empty string when present")
        return cls(
            generator=require_str(data["generator"], "generator"),
            generator_version=require_str(
                data["generator_version"], "generator_version"
            ),
            seed_id=seed_id,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "generator": self.generator,
            "generator_version": self.generator_version,
        }
        if self.seed_id is not None:
            result["seed_id"] = self.seed_id
        return result


Provenance = HarvestedProvenance | GeneratedProvenance


def provenance_from_dict(data: object) -> Provenance:
    d = require_object(data, "provenance")
    if "kind" not in d:
        raise ContractError("provenance must be an object with a 'kind'")
    kind = d["kind"]
    if kind == HARVESTED:
        return HarvestedProvenance.from_dict(d)
    if kind == GENERATED:
        return GeneratedProvenance.from_dict(d)
    raise ContractError(f"unknown provenance kind: {kind!r}")


__all__ = [
    "HARVESTED",
    "GENERATED",
    "HarvestedProvenance",
    "GeneratedProvenance",
    "Provenance",
    "provenance_from_dict",
]
