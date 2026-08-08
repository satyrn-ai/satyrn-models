"""SP5 pilot sampling and calibrated thresholds.

A nested, stratified selection plan (``sampling.toml``) allocates the pilot
by source kind → property → pattern → seed, prioritizing distinct seeds at
the leaf. Calibration derives report-only thresholds (diversity, composition
tolerance, review budget) and is committed; finalizing a 500-row selection
requires a calibration record whose profile version and target agree — an
old pilot is never declared to match a new composition profile.

SP5 never selects contamination thresholds; those belong to the provider.
"""

import dataclasses
import datetime
import json
import math
import tomllib
from pathlib import Path

__all__ = [
    "CalibrationError",
    "CalibrationRecord",
    "PlanValidationError",
    "SampleRow",
    "SamplingPlan",
    "derive_calibration",
    "finalize_500",
    "load_composition_version",
    "read_calibration",
    "select_pilot",
    "write_calibration",
]


class PlanValidationError(ValueError):
    """The sampling plan is malformed (bad strata, proportions, or order)."""


class CalibrationError(RuntimeError):
    """A final selection lacks a matching committed calibration record."""


@dataclasses.dataclass(frozen=True)
class SampleRow:
    """One pilot candidate with its stratum attributes (single label per
    level — the five property kinds, not the authoring/consuming report
    dimension)."""

    row_id: str
    source_kind: str  # "extracted" | "authored"
    property: str  # introspect | render | transform | construct | negative
    pattern_id: str
    seed_id: str
    prompt_family: str = "default"
    role: str = "consumer"  # "consumer" | "author"
    domain: str = "text"  # sql | html | logging | regex | text | data
    skeleton: str = ""
    prompt: str = ""
    operation: str = "unspecified"


class SamplingPlan:
    """Nested stratified plan loaded from ``sampling.toml``."""

    # nested_order level name -> SampleRow attribute
    _LEVEL_ATTR = {
        "source_kind": "source_kind",
        "role": "role",
        "domain": "domain",
        "property": "property",
        "pattern": "pattern_id",
        "prompt_family": "prompt_family",
        "seed": "seed_id",
    }

    def __init__(self, target_rows: int, nested_order: list[str], strata: dict) -> None:
        self.target_rows = target_rows
        self.nested_order = tuple(nested_order)
        self.strata = strata  # level -> {stratum: proportion}
        self._validate()

    @classmethod
    def load(cls, path: Path, *, text: str | None = None) -> SamplingPlan:
        if text is None:
            text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
        plan = data["plan"]
        raw_strata = plan.get("strata", {})
        strata = {
            level: dict(raw_strata[level])
            for level in plan["nested_order"]
            if level in raw_strata
        }
        return cls(
            target_rows=plan["target_rows"],
            nested_order=list(plan["nested_order"]),
            strata=strata,
        )

    def _validate(self) -> None:
        if self.target_rows <= 0:
            raise PlanValidationError("target_rows must be positive")
        for level in self.nested_order:
            if level not in self._LEVEL_ATTR:
                raise PlanValidationError(f"unknown nested level {level!r}")
        for level, strata in self.strata.items():
            if level == "pattern":
                # Pattern allocation is nested under the preceding stratum.
                for parent, patterns in strata.items():
                    total = sum(patterns.values())
                    if abs(total - 1.0) > 1e-6:
                        raise PlanValidationError(
                            f"patterns for {parent!r} sum to {total}, not 1.0"
                        )
                continue
            total = sum(strata.values())
            if abs(total - 1.0) > 1e-6:
                raise PlanValidationError(
                    f"strata for {level!r} sum to {total}, not 1.0"
                )

    def quota(
        self, level: str, target: int, *, parent: str | None = None
    ) -> dict[str, int]:
        strata = self.strata.get(level)
        if strata is None:
            return {}
        if level == "pattern":
            strata = strata.get(parent or "", {})
        raw = {stratum: target * proportion for stratum, proportion in strata.items()}
        quotas = {stratum: math.floor(value) for stratum, value in raw.items()}
        remainder = target - sum(quotas.values())
        ranked = sorted(
            raw,
            key=lambda stratum: (raw[stratum] - quotas[stratum], stratum),
            reverse=True,
        )
        for stratum in ranked[:remainder]:
            quotas[stratum] += 1
        return quotas


def _distinct_seeds_first(rows: list[SampleRow]) -> list[SampleRow]:
    """Order *rows* to surface distinct seed_ids before repeat seeds."""
    seen: set[str] = set()
    distinct: list[SampleRow] = []
    repeats: list[SampleRow] = []
    for r in rows:
        if r.seed_id not in seen:
            seen.add(r.seed_id)
            distinct.append(r)
        else:
            repeats.append(r)
    return distinct + repeats


def select_pilot(
    rows: list[SampleRow], *, plan: SamplingPlan, target_rows: int
) -> list[SampleRow]:
    """Nested, stratified selection in the plan's declared order.

    Recursive: each stratum's quota is itself selected by descending into the
    next level, so level-2 picks come only from level-1 selections. At the
    leaf level distinct seeds are prioritized.
    """
    selected = _select_level(rows, 0, plan, target_rows)
    selected_ids = {row.row_id for row in selected}
    target = min(target_rows, len({row.row_id for row in rows}))
    if len(selected) < target:
        for row in _distinct_seeds_first(rows):
            if row.row_id in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(row.row_id)
            if len(selected) == target:
                break
    return selected[:target]


def _select_level(
    rows: list[SampleRow], level_index: int, plan: SamplingPlan, target: int
) -> list[SampleRow]:
    if target <= 0 or not rows:
        return []
    if level_index >= len(plan.nested_order):
        return rows[:target]

    level = plan.nested_order[level_index]
    if level == "pattern":
        parent_level = plan.nested_order[level_index - 1]
        parent = getattr(rows[0], plan._LEVEL_ATTR[parent_level]) if rows else None
        quotas = plan.quota(level, target, parent=parent)
    else:
        quotas = plan.quota(level, target)
    result: list[SampleRow] = []
    is_leaf = level_index == len(plan.nested_order) - 1

    if not quotas:
        # No explicit strata at this level: take distinct seeds up to target.
        return _distinct_seeds_first(rows)[:target] if is_leaf else rows[:target]

    for stratum, quota in quotas.items():
        attr = plan._LEVEL_ATTR[level]
        subset = [r for r in rows if getattr(r, attr) == stratum]
        if is_leaf:
            picks = _distinct_seeds_first(subset)[:quota]
        else:
            picks = _select_level(subset, level_index + 1, plan, quota)
        result.extend(picks)
    return result


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CalibrationRecord:
    """Committed threshold derivations for one pilot selection."""

    profile_version: int
    target_rows: int
    derived_at: str
    diversity: dict
    composition_tolerance: dict
    review_budget: float
    semantic_near_gate: str | None = None  # SP5 never selects this


def derive_calibration(
    selected: list[SampleRow],
    *,
    profile_version: int,
    target_rows: int,
    review_budget: float = 0.10,
) -> CalibrationRecord:
    """Derive report-only thresholds from the pilot's actuals."""
    skeletons = {r.skeleton for r in selected if r.skeleton}
    prompts = {r.prompt for r in selected if r.prompt}
    by_property: dict[str, int] = {}
    for r in selected:
        by_property[r.property] = by_property.get(r.property, 0) + 1
    n = len(selected) or 1
    tolerance = {
        prop: [round(count / n - 0.05, 3), round(count / n + 0.05, 3)]
        for prop, count in sorted(by_property.items())
    }
    return CalibrationRecord(
        profile_version=profile_version,
        target_rows=target_rows,
        derived_at=datetime.datetime.now(datetime.UTC).isoformat(),
        diversity={
            "distinct_skeletons": len(skeletons),
            "distinct_prompts": len(prompts),
        },
        composition_tolerance=tolerance,
        review_budget=review_budget,
    )


def finalize_500(
    selected: list[SampleRow],
    calibration: CalibrationRecord | None,
    *,
    profile_version: int,
) -> None:
    """Refuse to finalize a selection without a matching calibration record.

    An old pilot is never declared to match a new composition profile: both
    the profile version and the target row count must agree.
    """
    if calibration is None:
        raise CalibrationError(
            "final selection requires a committed calibration record; "
            "run `authoring pilot` first"
        )
    if calibration.profile_version != profile_version:
        raise CalibrationError(
            f"calibration profile version v{calibration.profile_version} "
            f"does not match current profile version v{profile_version}; "
            "rerun calibration"
        )
    if calibration.target_rows != len(selected):
        raise CalibrationError(
            f"calibration targets {calibration.target_rows} rows, "
            f"selection has {len(selected)}"
        )


def write_calibration(record: CalibrationRecord, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dataclasses.asdict(record), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def read_calibration(path: Path) -> CalibrationRecord:
    return CalibrationRecord(**json.loads(path.read_text(encoding="utf-8")))


def load_composition_version(path: Path) -> int:
    """Read the ``[profile] version`` from composition.toml."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return int(data["profile"]["version"])
    except KeyError as exc:
        raise PlanValidationError(f"{path} is missing [profile] version") from exc
