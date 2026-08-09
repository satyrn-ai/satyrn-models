"""SP5 local data model: occurrences, seeds, task intent, and property variants.

Tuple types throughout because the dataclasses are frozen and hashable; JSONL
round-trips normalize lists back to tuples in ``__post_init__``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Literal

Domain = Literal["sql", "html", "logging", "regex", "text", "data"]


@dataclasses.dataclass(frozen=True)
class SourceOrigin:
    """A specific source location — simplified, single type for all origins."""

    source_id: str  # FK to SourceRecord.id
    path: str
    line_start: int
    line_end: int
    license: str


@dataclasses.dataclass(frozen=True)
class SeedOccurrence:
    """One occurrence of a t-string seed at a specific source location."""

    id: str  # sha256(source_id + path + span)
    seed_id: str  # sha256(literal + bindings)
    literal: str
    free_names: tuple[str, ...]
    bindings: tuple[tuple[str, str], ...]  # (name, python-expr)
    kind: Literal["extracted", "authored"]
    origin: SourceOrigin
    domain: Domain = "text"


# ---------------------------------------------------------------------------
# Property variants (tagged union)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Introspect:
    target: str  # e.g. ".strings", ".values", ".interpolations"
    index: int
    field: str


@dataclasses.dataclass(frozen=True)
class RenderTemplate:
    """Full f-string-equivalent rendering via an explicit template function."""

    renderer: Literal["canonical"] = "canonical"


@dataclasses.dataclass(frozen=True)
class JoinStaticParts:
    """Join ``Template.strings`` while intentionally omitting interpolations."""

    separator: str = ""


@dataclasses.dataclass(frozen=True)
class SelectTemplateResult:
    """Choose one deliberately contrasted result from the same template."""

    outcome: Literal["template", "strings", "values", "joined_static", "rendered"]


@dataclasses.dataclass(frozen=True)
class RenderSubskill:
    """One explicit step in f-string-equivalent template rendering."""

    stage: Literal[
        "iterate_parts",
        "classify_parts",
        "convert_value",
        "format_value",
        "render_interpolation",
        "render_template",
    ]


@dataclasses.dataclass(frozen=True)
class ComposeTemplates:
    """Compose templates with ``+``; later inspection is a separate operation."""

    arity: Literal[2] = 2
    result: Literal[
        "template", "strings", "values", "interpolations", "rendered"
    ] = "template"


@dataclasses.dataclass(frozen=True)
class Construct:
    operation: Literal["Interpolation", "convert"]
    conversion: Literal["s", "r", "a"] | None = None
    expression: str = "name"
    format_spec: str = ""


@dataclasses.dataclass(frozen=True)
class NegativeControl:
    expected_solution_kind: str
    requires_template: bool = False


Property = (
    Introspect
    | RenderTemplate
    | JoinStaticParts
    | SelectTemplateResult
    | RenderSubskill
    | ComposeTemplates
    | Construct
    | NegativeControl
)


# ---------------------------------------------------------------------------
# PolicyIntent (minimal — "aim low")
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PolicyIntent:
    """Versioned, dependency-isolated projection consumed by ``TStringPolicy``.

    Does NOT import authoring internals. The policy derives degenerates from
    these declarative flags alone.
    """

    requires_template: bool
    templatelib_apis_used: frozenset[str]  # {"strings", "values", "convert", ...}


# ---------------------------------------------------------------------------
# TaskIntent, SourceEvidence, SourceExerciseCandidate
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SourceEvidence:
    """Descriptive metadata the extractor found at the source site."""

    function_name: str | None = None
    docstring: str | None = None


@dataclasses.dataclass(frozen=True)
class TaskIntent:
    """Canonical intent for one task, rendered into prompt/ref/checks/policy."""

    id: str
    description: str
    properties: tuple[Property, ...]  # non-empty, ordered
    policy_intent: PolicyIntent
    role: Literal["consumer", "author"] = "consumer"

    def __post_init__(self) -> None:
        if not self.properties:
            raise ValueError("TaskIntent.properties must be non-empty")


# ---------------------------------------------------------------------------
# Post-init normalization: accept lists from JSON deserialization
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Seed:
    """A normalized t-string seed: one literal, possibly from many origins."""

    id: str  # sha256(literal + bindings)
    literal: str
    free_names: tuple[str, ...]
    bindings: tuple[tuple[str, str], ...]  # (name, python-expr)
    occurrence_ids: tuple[str, ...]
    kind: Literal["extracted", "authored"]
    domain: Domain = "text"

    def __post_init__(self) -> None:
        object.__setattr__(self, "free_names", tuple(self.free_names))
        object.__setattr__(self, "bindings", tuple(tuple(p) for p in self.bindings))
        object.__setattr__(self, "occurrence_ids", tuple(self.occurrence_ids))


# ---------------------------------------------------------------------------
# Content-derived IDs (spec §3.1)
# ---------------------------------------------------------------------------


def seed_id(literal: str, bindings: tuple[tuple[str, str], ...]) -> str:
    """Content-derived seed id — stable across extraction runs."""
    payload = f"{literal}\0{json.dumps(bindings, sort_keys=True)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def occurrence_id(
    source_id: str,
    path: str,
    line_start: int,
    line_end: int,
) -> str:
    """Occurrence id — stable per exact source span."""
    payload = f"{source_id}\0{path}\0{line_start}\0{line_end}"
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclasses.dataclass(frozen=True)
class LocalCheckIntent:
    """A declarative check intent mapped to a single source assertion."""

    kind: str  # "equals", "contains", "type_check", etc.
    target: str  # e.g. "template.strings[0]"


@dataclasses.dataclass(frozen=True)
class SourceExerciseCandidate:
    """A candidate exercise extracted from a real source."""

    id: str
    origin: SourceOrigin
    evidence: SourceEvidence
    intent: TaskIntent
    check_intents: tuple[LocalCheckIntent, ...] = ()


@dataclasses.dataclass(frozen=True)
class GeneratedExercise:
    """A pattern-generated exercise intent with arity enforcement."""

    id: str
    pattern_id: str
    seeds: tuple[Seed, ...]
    properties: tuple[Property, ...]
    pattern_fingerprint: str = ""  # same key as patterns/approvals.jsonl
    prompt_family: str = "default"

    def __post_init__(self) -> None:
        if not self.properties:
            raise ValueError("GeneratedExercise.properties must be non-empty")
        if not self.prompt_family:
            raise ValueError("GeneratedExercise.prompt_family must be non-empty")
        n = len(self.seeds)
        for prop in self.properties:
            required = _property_arity(prop)
            if n < required:
                raise ValueError(
                    f"property {prop!r} requires arity {required}, "
                    f"but only {n} seed(s) provided"
                )


def _property_arity(prop: Property) -> int:
    """Return the minimum number of seeds the property variant expects."""
    if isinstance(prop, ComposeTemplates):
        return prop.arity
    if isinstance(prop, Construct):
        return 0
    return 1
