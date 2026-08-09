"""SP5 generation: pure application of approved patterns to seeds.

Generation is a pure function of committed inputs (patterns + seeds +
approvals). It materializes a transient, gitignored ``build/generated.jsonl``
carrying an input fingerprint (seeds hash + pattern-registry hash + generator
version) and self-invalidating on mismatch — a cache that knows when it
disagrees, never a second source of truth.
"""

import dataclasses
import hashlib
import json
from pathlib import Path

from .models import (
    ComposeTemplates,
    Construct,
    GeneratedExercise,
    Introspect,
    JoinStaticParts,
    NegativeControl,
    Property,
    RenderTemplate,
    Seed,
)
from .patterns.approvals import PatternApproval, require_approval
from .patterns.registry import (
    GENERATOR_VERSION,
    Pattern,
    build_properties,
    pattern_arity,
    pattern_input_fingerprint,
    prompt_variants,
)

__all__ = [
    "apply_pattern",
    "generate_all",
    "generate_cached",
    "generation_fingerprint",
    "read_generated",
    "write_generated",
]


def _exercise_id(
    pattern: Pattern, seeds: tuple[Seed, ...], prompt_family: str = "default"
) -> str:
    material = {
        "pattern_id": pattern.id,
        "seed_ids": [s.id for s in seeds],
        "specs": [dataclasses.asdict(s) for s in pattern.property_specs],
    }
    if prompt_family != "default":
        material["prompt_family"] = prompt_family
    payload = json.dumps(material, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def apply_pattern(
    pattern: Pattern,
    seeds: tuple[Seed, ...],
    *,
    prompt_family: str | None = None,
) -> GeneratedExercise:
    """Emit one exercise intent from *pattern* over *seeds*."""
    variants = prompt_variants(pattern)
    family_ids = {variant.id for variant in variants}
    if prompt_family is None:
        prompt_family = variants[0].id
    if prompt_family not in family_ids:
        raise ValueError(
            f"pattern {pattern.id!r} has no prompt family {prompt_family!r}"
        )
    props = build_properties(pattern.property_specs)
    return GeneratedExercise(
        id=_exercise_id(pattern, seeds, prompt_family),
        pattern_id=pattern.id,
        seeds=tuple(seeds),
        properties=props,
        pattern_fingerprint=pattern_input_fingerprint(pattern),
        prompt_family=prompt_family,
    )


def generate_all(
    patterns: list[Pattern],
    seeds: tuple[Seed, ...],
    approvals: list[PatternApproval],
) -> list[GeneratedExercise]:
    """Apply every approved pattern to *seeds*, one exercise per arity chunk.

    Refuses any pattern whose approval is missing or stale (fingerprint
    mismatch) before emitting a single row.
    """
    rows: list[GeneratedExercise] = []
    for pattern in patterns:
        require_approval(pattern, approvals, pattern_input_fingerprint(pattern))
        n = pattern_arity(pattern)
        variants = prompt_variants(pattern)
        if n == 0:
            rows.append(apply_pattern(pattern, (), prompt_family=variants[0].id))
            continue
        for variant in variants:
            by_source_domain: dict[tuple[str, str], list[Seed]] = {}
            for seed in seeds:
                by_source_domain.setdefault((seed.kind, seed.domain), []).append(seed)
            for grouped_seeds in by_source_domain.values():
                for i in range(0, len(grouped_seeds) - n + 1, n):
                    rows.append(
                        apply_pattern(
                            pattern,
                            tuple(grouped_seeds[i : i + n]),
                            prompt_family=variant.id,
                        )
                    )
    return rows


def generation_fingerprint(patterns: list[Pattern], seeds: tuple[Seed, ...]) -> str:
    """Input fingerprint for the whole generated artifact."""
    material = {
        "patterns": sorted(pattern_input_fingerprint(p) for p in patterns),
        "seeds": sorted(
            ({"id": seed.id, "domain": seed.domain} for seed in seeds),
            key=lambda item: item["id"],
        ),
        "generator_version": GENERATOR_VERSION,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Transient cache round-trip (gitignored build/generated.jsonl)
# ---------------------------------------------------------------------------


def _property_from_dict(data: dict) -> Property:
    kind = data.pop("__kind__")
    if kind == "introspect":
        return Introspect(**data)
    if kind == "render_template":
        return RenderTemplate(**data)
    if kind == "join_static_parts":
        return JoinStaticParts(**data)
    if kind == "compose_templates":
        return ComposeTemplates(**data)
    if kind == "construct":
        return Construct(**data)
    if kind == "negative":
        return NegativeControl(**data)
    raise ValueError(f"unknown property kind {kind!r}")


def _row_to_dict(row: GeneratedExercise) -> dict:
    return {
        "id": row.id,
        "pattern_id": row.pattern_id,
        "pattern_fingerprint": row.pattern_fingerprint,
        "seeds": [dataclasses.asdict(s) for s in row.seeds],
        "properties": [
            {"__kind__": _kind(p), **dataclasses.asdict(p)} for p in row.properties
        ],
        "prompt_family": row.prompt_family,
    }


def _kind(prop: Property) -> str:
    if isinstance(prop, Introspect):
        return "introspect"
    if isinstance(prop, RenderTemplate):
        return "render_template"
    if isinstance(prop, JoinStaticParts):
        return "join_static_parts"
    if isinstance(prop, ComposeTemplates):
        return "compose_templates"
    if isinstance(prop, Construct):
        return "construct"
    if isinstance(prop, NegativeControl):
        return "negative"
    raise ValueError(f"unknown property {prop!r}")


def _row_from_dict(data: dict) -> GeneratedExercise:
    return GeneratedExercise(
        id=data["id"],
        pattern_id=data["pattern_id"],
        seeds=tuple(Seed(**s) for s in data["seeds"]),
        properties=tuple(_property_from_dict(dict(p)) for p in data["properties"]),
        pattern_fingerprint=data["pattern_fingerprint"],
        prompt_family=data.get("prompt_family", "default"),
    )


def write_generated(
    rows: list[GeneratedExercise], fingerprint: str, path: Path
) -> None:
    """Write the generated artifact: fingerprint line + one row per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps({"kind": "generation-fingerprint", "fingerprint": fingerprint})
            + "\n"
        )
        for row in rows:
            f.write(json.dumps(_row_to_dict(row), sort_keys=True) + "\n")


def read_generated(path: Path) -> tuple[str, list[GeneratedExercise]]:
    """Read (fingerprint, rows) from a generated artifact; raises on corrupt."""
    rows: list[GeneratedExercise] = []
    fingerprint: str | None = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("kind") == "generation-fingerprint":
                fingerprint = data["fingerprint"]
                continue
            rows.append(_row_from_dict(data))
    if fingerprint is None:
        raise ValueError(f"{path} is not a generated artifact (no fingerprint)")
    return fingerprint, rows


def generate_cached(
    patterns: list[Pattern],
    seeds: tuple[Seed, ...],
    approvals: list[PatternApproval],
    cache_path: Path,
) -> list[GeneratedExercise]:
    """Return cached rows when the input fingerprint matches, else regenerate
    and rewrite the cache (self-invalidation on any input change)."""
    current = generation_fingerprint(patterns, seeds)
    try:
        cached_fp, cached_rows = read_generated(cache_path)
    except OSError, ValueError:
        cached_fp, cached_rows = None, []

    if cached_fp == current:
        return cached_rows

    rows = generate_all(patterns, seeds, approvals)
    write_generated(rows, current, cache_path)
    return rows
