"""SP5 coverage analysis: measure what the corpus covers and where gaps are.

Runs on extraction candidates and authored seeds alone — no provider API calls.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from .models import (
    ComposeTemplates,
    Construct,
    Introspect,
    JoinStaticParts,
    NegativeControl,
    Property,
    RenderTemplate,
    Seed,
    SourceExerciseCandidate,
)

__all__ = ["CoverageReport", "analyze_coverage", "skeleton_of", "write_coverage_md"]


def _property_name(prop: Property) -> str:
    """Return a stable string key for a Property variant."""
    if isinstance(prop, Introspect):
        return "introspect"
    if isinstance(prop, RenderTemplate):
        return "render_template"
    if isinstance(prop, JoinStaticParts):
        return "join_static_parts"
    if isinstance(prop, Construct):
        return "construct"
    if isinstance(prop, ComposeTemplates):
        return "compose_templates"
    if isinstance(prop, NegativeControl):
        return "negative"
    return "unknown"


_ALL_KEYS = (
    "introspect",
    "render_template",
    "join_static_parts",
    "compose_templates",
    "construct",
    "negative",
)


@dataclasses.dataclass
class CoverageReport:
    """Coverage summary from extraction candidates and authored seeds."""

    property_counts: dict[str, int]
    source_counts: dict[str, int]
    gaps: list[str]
    skeleton_buckets: int
    rows_are_provider_qualified: bool = False


def skeleton_of(seed: Seed) -> str:
    """Structural fingerprint: shape retained, identifiers and constants erased."""
    s = seed.literal
    # String literals → "..."
    s = re.sub(r"'[^']*'|\"[^\"]*\"", '"..."', s)
    # Interpolated expressions → x
    s = re.sub(r"\{[^}]+\}", "{x}", s)
    return s


def analyze_coverage(
    candidates: list[SourceExerciseCandidate],
    seeds: list[Seed],
) -> CoverageReport:
    """Produce a coverage report from available data."""
    prop_counts: dict[str, int] = {k: 0 for k in _ALL_KEYS}
    source_counts: dict[str, int] = {"extracted": 0, "authored": 0}
    skeletons: set[str] = set()

    for c in candidates:
        for prop in c.intent.properties:
            prop_counts[_property_name(prop)] += 1
    source_counts["extracted"] = len(candidates)
    source_counts["authored"] = len(seeds)

    for seed in seeds:
        skeletons.add(skeleton_of(seed))

    gaps = [k for k in _ALL_KEYS if prop_counts[k] == 0]

    return CoverageReport(
        property_counts=prop_counts,
        source_counts=source_counts,
        gaps=gaps,
        skeleton_buckets=len(skeletons),
    )


def write_coverage_md(report: CoverageReport, path: Path) -> None:
    """Write ``reports/coverage.md`` from a coverage report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SP5 Coverage Report",
        "",
        "> **Not provider-qualified.** No row in this report has been ",
        "> verified, executed, or qualified by the provider.  This is a ",
        "> collection checkpoint only.",
        "",
        "## Property Coverage",
        "",
        "| Property | Count |",
        "|---|---|",
    ]
    for key in _ALL_KEYS:
        lines.append(f"| {key} | {report.property_counts[key]} |")
    lines += [
        "",
        "## Source Coverage",
        "",
        f"- Extracted: {report.source_counts['extracted']}",
        f"- Authored:  {report.source_counts['authored']}",
        "",
        "## Gaps",
        "",
    ]
    if report.gaps:
        for gap in report.gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("_No property gaps detected._")
    lines += [
        "",
        "## Structural Diversity",
        "",
        f"- Distinct skeletons: {report.skeleton_buckets}",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
