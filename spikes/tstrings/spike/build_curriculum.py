"""Select a role x capability curriculum from the approved SP5 candidate pool.

The reviewed 500-row curriculum was chosen by a selector that enforces
marginals over property, operation, source kind, role, and domain — all of them
*global*. Nothing constrained the role x capability cell, so a 12% ``strings``
quota could be, and was, filled almost entirely from ``contrast-author-strings``:
44 author rows against 7 consumer rows. Twenty approved patterns were sampled
zero times; fifteen of them have 132 rows each and cover interpolation-field
extraction, typed authoring, and plain rendering. (The other five are
``construct-*`` patterns with one row apiece, and construct was not among the
observed failure modes.) Those fifteen overlap heavily with what the adapter
failed, though they do not explain the API-hallucination failures, whose
sibling patterns were trained on heavily — see ``API_CONTRAST_PATTERNS.md``.

This selector names the cells instead of inferring them. Every cell draws a
fixed number of rows from named patterns, and each cell is filled as
``k`` seeds x 3 prompt families, so capability and framing stay independent in
training as they now are in the benchmark.

Paired contrasts (repair step 4) are built by sharing one seed set across the
members of a contrast group: the same template appears under "return the
tuple", "join only the static strings", and "fully render", so the contrast is
carried by the instruction rather than by the example.

Only rows already present in the approved candidate pool are selectable, and
every pattern used is checked against ``patterns/approvals.jsonl``. Nothing is
hand-authored; see the retired augmentation note in ``build_train_data.py``.
"""

from __future__ import annotations

import argparse
import collections
import json
from dataclasses import dataclass, field
from pathlib import Path

FAMILIES = ("direct", "pep750-request", "python-program")

# Nine patterns answer with the same canonical `def render_template(...)` body.
# That is not a generation bug — it is the correct answer, and no approved
# pattern offers a different one — so the only control available is how often
# the model sees it.
#
# Exposure is measurable in outcomes. Re-scoring the saved `ood-v1` runs
# (`spike/rescore_ood.py`) separates two populations that both surface as
# `NameError`: candidates referencing task inputs the prompt never supplied,
# which is the benchmark's defect, and candidates calling the corpus's renderer
# without defining it, which is ours.
#
#   arm                  undefined renderer
#   bare                 0 / 25
#   + docs               0 / 25
#   + LoRA               1 / 25
#   + LoRA + docs        6 / 25
#
# It appears only on LoRA arms, so it is trained in. The adapter that produced
# the 6 was trained on `repair-v2`, where these patterns supply 51 of 443 rows
# (11.5%) -- so 11.5% is already too much, and `diversity-v1`'s 16.3% is worse.
# No row in either curriculum calls a renderer without defining it, so the model
# is not copying a bad example; repetition alone is making `render_template`
# feel ambient.
BODY_PATTERNS = frozenset(
    {
        "render-template",
        "render-template-explicit-function",
        "render-subskill-render_template",
        "render-subskill-author-template",
        "author-render-template",
        "author-render-explicit-function",
        "contrast-rendered",
        "contrast-author-rendered",
        "compose-then-render",
    }
)

# Mirrors composition.toml profile v5 so deviations are reported rather than
# discovered later. The property and operation targets are *deliberately*
# superseded by the cell table below — see `MARGINAL_NOTES` — but role, domain,
# and source-kind carry no such justification and are held to profile.
DOMAIN_TARGETS = {
    "sql": 0.20,
    "html": 0.20,
    "logging": 0.15,
    "regex": 0.10,
    "text": 0.20,
    "data": 0.15,
}
ROLE_TARGETS = {"consumer": 0.70, "author": 0.30}
SOURCE_KIND_TARGETS = {"extracted": 0.20, "authored": 0.80}
PROPERTY_TARGETS = {
    "select_result": 0.43,
    "render_subskill": 0.45,
    "join_static_parts": 0.04,
    "compose_templates": 0.05,
    "construct": 0.01,
    "negative": 0.02,
}
MANDATORY_STRATA = {
    "property": (
        "select_result",
        "render_subskill",
        "join_static_parts",
        "compose_templates",
        "construct",
        "negative",
    ),
    "source_kind": ("extracted", "authored"),
    "role": ("consumer", "author"),
}
MARGINAL_NOTES = {
    "property": (
        "Deliberately superseded. Profile v5 put 45% of rows in "
        "render_subskill and 43% in select_result; that curriculum is the one "
        "that scored 36/100 while never sampling a single interpolation-field "
        "or typed-authoring row. The cell table replaces those proportions on "
        "purpose. SP5 should ratify a profile v6 rather than treat this as "
        "conformant."
    ),
    "operation": (
        "Deliberately superseded for the same reason, and the cell table adds "
        "the `interpolations` operation, which profile v5 does not target."
    ),
}


@dataclass(frozen=True)
class Cell:
    """One role x capability cell and the approved patterns that may fill it."""

    capability: str
    role: str
    patterns: tuple[tuple[str, int], ...]
    contrast_group: str | None = None
    family_balanced: bool = True

    @property
    def size(self) -> int:
        return sum(count for _, count in self.patterns)


CONSUMER_CELLS: tuple[Cell, ...] = (
    Cell(
        "strings",
        "consumer",
        (("intro-strings", 24), ("contrast-strings", 24)),
        contrast_group="consumer-contrast",
    ),
    Cell(
        "values",
        "consumer",
        (("intro-values", 24), ("contrast-values", 24)),
        contrast_group="consumer-contrast",
    ),
    Cell("interpolation_value", "consumer", (("intro-interpolations", 18),)),
    Cell("interpolation_expression", "consumer", (("intro-expressions", 24),)),
    Cell("interpolation_conversion", "consumer", (("intro-conversions", 18),)),
    Cell("interpolation_format_spec", "consumer", (("intro-format-specs", 18),)),
    Cell(
        "join_static",
        "consumer",
        (
            ("join-static-parts", 6),
            ("join-static-parts-newline", 6),
            ("join-static-parts-pipe", 6),
            ("contrast-joined_static", 24),
        ),
        contrast_group="consumer-contrast",
    ),
    # Render cells are deliberately thinned. Eight patterns emit the *same*
    # canonical `def render_template(...)` body, and at the previous weights
    # that block appeared in 102 of 454 training rows — 22.5% of the
    # curriculum, byte-identical. The seed-42 adapter then answered `.values`
    # prompts with that renderer (4 failures) and called `render_template(...)`
    # without defining it (4 failures). Both are over-exposure, not absence.
    Cell(
        "render_basic",
        "consumer",
        (("render-template", 12), ("contrast-rendered", 6)),
        contrast_group="consumer-contrast",
    ),
    Cell("render_explicit", "consumer", (("render-template-explicit-function", 6),)),
    Cell(
        "compose",
        "consumer",
        (
            ("compose-templates", 6),
            ("compose-then-strings", 6),
            ("compose-then-values", 6),
            ("compose-then-render", 3),
            ("compose-then-interpolations", 6),
        ),
    ),
    Cell("template", "consumer", (("contrast-template", 18),)),
    Cell("subskill_classify", "consumer", (("render-subskill-classify_parts", 18),)),
    Cell("subskill_convert", "consumer", (("render-subskill-convert_value", 18),)),
    Cell("subskill_format", "consumer", (("render-subskill-format_value", 18),)),
    Cell("subskill_iterate", "consumer", (("render-subskill-iterate_parts", 18),)),
    Cell(
        "subskill_render_interpolation",
        "consumer",
        (("render-subskill-render_interpolation", 18),),
    ),
    # Restored. The thinning note above is right that the *byte-identical*
    # renderer body was over-exposed, but it took volume and diversity down
    # together: `render-subskill-render_template` — the one pattern that
    # practises rendering a whole template, 132 approved rows over 44 seeds and
    # 14 distinct shapes — ended up at zero rows. Rendering is then the single
    # capability that failed in every configuration on both base models, and
    # ~11 of the 25 remaining `ood-v1` failures leave `answer = template`
    # unrendered.
    #
    # Sized like its sibling subskill cells. Rows are seeds x 3 families, so
    # 18 rows buys at most 6 shapes, not 18.
    #
    # WARNING, and an earlier version of this comment had it wrong: `--diversify`
    # does NOT prevent the over-exposure the thinning note describes. Skeletons
    # fingerprint the *whole program*, while the duplicate is a sub-program —
    # the canonical `def render_template(...)` body embedded inside otherwise
    # different programs. At these weights that body is byte-identical in 84 of
    # 516 rows (16.3%), against 102 of 454 (22.5%) in the curriculum the
    # thinning repaired, and max shape repeat of 12 coexists with it happily.
    # At three epochs that is ~252 exposures, more in absolute terms than the
    # run that produced the documented failures (answering `.values` prompts
    # with the renderer; calling `render_template` without defining it).
    #
    # Do not raise these weights further without capping that body directly.
    Cell(
        "subskill_render_template",
        "consumer",
        (("render-subskill-render_template", 18),),
    ),
    # Tripled. The seed-42 adapter produced 7 f-string policy failures where
    # the previous run produced none.
    Cell(
        "negative",
        "consumer",
        (("negative-fstring", 9), ("negative-fstring-direct-output", 9)),
    ),
    # Construct rows exist as a single prompt family each, so this cell cannot
    # be family balanced. It is a mandatory stratum in composition.toml.
    Cell(
        "construct",
        "consumer",
        (
            ("construct-convert", 1),
            ("construct-convert-a", 1),
            ("construct-interpolation-basic", 1),
            ("construct-interpolation-expression", 1),
            ("construct-interpolation-format", 1),
            ("construct-interpolation-r", 1),
        ),
        family_balanced=False,
    ),
)

AUTHOR_CELLS: tuple[Cell, ...] = (
    Cell(
        "author_strings",
        "author",
        (("author-static-parts", 24), ("contrast-author-strings", 12)),
        contrast_group="author-contrast",
    ),
    Cell(
        "author_values",
        "author",
        (("author-values", 18), ("contrast-author-values", 12)),
        contrast_group="author-contrast",
    ),
    # Also thinned — see the render note above. Authoring the renderer is a
    # real capability and it passed 6/6 under documentation context, so it does
    # not need 42 rows of the identical body.
    Cell(
        "author_render",
        "author",
        (
            ("author-render-template", 12),
            ("author-render-explicit-function", 6),
            ("contrast-author-rendered", 6),
        ),
        contrast_group="author-contrast",
    ),
    Cell(
        "author_interpolations",
        "author",
        (
            ("author-interpolations", 18),
            ("author-expressions", 18),
            ("author-format-specs", 18),
        ),
    ),
    Cell(
        "author_joined_static",
        "author",
        (("contrast-author-joined_static", 12),),
        contrast_group="author-contrast",
    ),
    Cell("author_render_subskill", "author", (("render-subskill-author-template", 24),)),
)

CELLS: tuple[Cell, ...] = CONSUMER_CELLS + AUTHOR_CELLS

CONTRAST_GROUPS: dict[str, tuple[str, ...]] = {
    "consumer-contrast": (
        "contrast-strings",
        "contrast-values",
        "contrast-joined_static",
        "contrast-rendered",
    ),
    "author-contrast": (
        "contrast-author-strings",
        "contrast-author-values",
        "contrast-author-rendered",
        "contrast-author-joined_static",
    ),
}


class CurriculumError(RuntimeError):
    """A cell cannot be filled from approved rows."""


@dataclass
class Index:
    """Approved candidate rows keyed by pattern, seed, and prompt family."""

    by_pattern: dict[str, dict[str, dict[str, dict]]] = field(default_factory=dict)
    domain_of: dict[tuple[str, str], str] = field(default_factory=dict)
    source_of: dict[tuple[str, str], str] = field(default_factory=dict)
    skeleton_of: dict[tuple[str, str], str] = field(default_factory=dict)

    @classmethod
    def build(cls, rows: list[dict]) -> Index:
        index = cls()
        for row in rows:
            seeds = index.by_pattern.setdefault(row["pattern_id"], {})
            seeds.setdefault(row["seed_id"], {})[row["prompt_family"]] = row
            key = (row["pattern_id"], row["seed_id"])
            index.domain_of[key] = row["domain"]
            index.source_of[key] = row["source_kind"]
            # Falling back to the key itself makes every row its own shape, so
            # `diversify` degrades to plain seed spread rather than collapsing
            # the whole pool onto one bucket when `skeleton` is absent.
            index.skeleton_of[key] = row.get("skeleton") or f"{key[0]}:{key[1]}"
        return index

    def complete_seeds(self, pattern: str) -> list[str]:
        """Seeds offering all three prompt families, in stable ID order.

        Ordering is deliberately neutral: ``Allocator`` decides which seeds a
        cell gets, so that cells do not all receive the same prefix.
        """
        return sorted(
            seed
            for seed, families in self.by_pattern.get(pattern, {}).items()
            if all(family in families for family in FAMILIES)
        )


class Allocator:
    """Spread seed usage across cells instead of giving every cell the same prefix.

    An earlier version ordered each pattern's seeds identically and took
    ``seeds[:wanted]``.  Because most patterns share one seed universe, every
    cell drew the same leading seeds: 504 rows collapsed onto 12 distinct
    seeds, with five seeds supplying 89% of the curriculum.  That reproduced,
    at greater scale, the near-identical-variant problem the review brief
    raised about the benchmark, and it was what actually broke the domain
    marginal.

    Selection is now greedy on least-used seed first, breaking ties toward the
    domain furthest below its ``composition.toml`` share.  It stays fully
    deterministic: no RNG, and ties fall back to seed ID order.
    """

    def __init__(self, index: Index, total_rows: int, diversify: bool = False) -> None:
        self.index = index
        self.total_rows = total_rows
        self.diversify = diversify
        self.seed_usage: collections.Counter[str] = collections.Counter()
        self.skeleton_usage: collections.Counter[str] = collections.Counter()
        self.domain_usage: collections.Counter[str] = collections.Counter()
        self.source_usage: collections.Counter[str] = collections.Counter()
        self.group_seeds: dict[str, list[str]] = {}

    def _domain(self, pattern: str, seed: str) -> str:
        return self.index.domain_of[(pattern, seed)]

    def _source(self, pattern: str, seed: str) -> str:
        return self.index.source_of[(pattern, seed)]

    def _skeleton(self, pattern: str, seed: str) -> str:
        return self.index.skeleton_of[(pattern, seed)]

    def _rank(self, pattern: str, seed: str) -> tuple:
        """Most-owed stratum first, then least-used skeleton, then least-used seed.

        Stratum shortfall leads because the pool's 54 seeds are themselves
        lopsided — 17 text and 16 data against 3 regex and 4 logging, with
        extraction supplying only text and data — so ordering on seed usage
        alone walks the curriculum straight to a text-heavy, authored-heavy
        mix. Seed usage is the tie-break, which keeps content spread wide
        inside each stratum.

        Under ``diversify``, skeleton usage is inserted ahead of seed usage.
        Spreading seeds is not the same as spreading *program shapes*: a
        pattern's seeds collapse onto far fewer skeletons than seeds (
        ``author-render-template`` has 44 complete seeds but 14 shapes), so a
        seed-spread curriculum still repeats structure. The 454-row curriculum
        reached 94 of the pool's 270 shapes, and only 19 of 81 render shapes —
        while rendering is the one capability that failed in every
        configuration on both base models.

        Stratum fill deliberately stays in the lead: shapes are a tie-break,
        not a licence to break the domain and source marginals that the
        repair was about.
        """
        domain = self._domain(pattern, seed)
        source = self._source(pattern, seed)
        fill = self._fill(
            self.domain_usage[domain], DOMAIN_TARGETS.get(domain)
        ) + self._fill(self.source_usage[source], SOURCE_KIND_TARGETS.get(source))
        if self.diversify:
            skeleton = self._skeleton(pattern, seed)
            return (fill, self.skeleton_usage[skeleton], self.seed_usage[seed], seed)
        return (fill, self.seed_usage[seed], seed)

    def _fill(self, used: int, target: float | None) -> float:
        """How full a stratum is, as a fraction of its quota.

        Ratios, not raw shortfalls: subtracting ``target * total`` makes the
        largest quota look the most owed at every step, so ``authored`` (80%)
        would outrank ``extracted`` (20%) forever and the source marginal
        never converged.
        """
        if not target:
            return 1.0
        return used / (target * self.total_rows)

    def take(self, pattern: str, candidates: list[str], wanted: int) -> list[str]:
        """Claim ``wanted`` seeds, preferring the least-used and most-owed."""
        if len(candidates) < wanted:
            raise CurriculumError(
                f"{pattern} offers {len(candidates)} complete seeds, "
                f"cell needs {wanted}"
            )
        pool = list(candidates)
        chosen: list[str] = []
        for _ in range(wanted):
            best = min(pool, key=lambda seed: self._rank(pattern, seed))
            pool.remove(best)
            chosen.append(best)
            self.seed_usage[best] += 1
            self.skeleton_usage[self._skeleton(pattern, best)] += 1
            self.domain_usage[self._domain(pattern, best)] += len(FAMILIES)
            self.source_usage[self._source(pattern, best)] += len(FAMILIES)
        return chosen

    def contrast_seeds(self, group: str, wanted: int) -> list[str]:
        """Allocate one seed set per contrast group, shared by all its members."""
        if group not in self.group_seeds:
            members = CONTRAST_GROUPS[group]
            shared: set[str] | None = None
            for pattern in members:
                seeds = set(self.index.complete_seeds(pattern))
                shared = seeds if shared is None else shared & seeds
            if not shared:
                raise CurriculumError(f"contrast group {group} shares no seed")
            needed = max(
                count // len(FAMILIES)
                for cell in CELLS
                if cell.contrast_group == group
                for pattern, count in cell.patterns
                if pattern in members
            )
            self.group_seeds[group] = self.take(
                members[0], sorted(shared), max(needed, wanted)
            )
        return self.group_seeds[group]


def scaled_cells(
    index: Index, scale: float, body_scale: float = 1.0
) -> list[tuple[Cell, tuple[tuple[str, int], ...]]]:
    """Multiply every cell count by ``scale``, clamped to what the pool holds.

    The volume sweep needs curricula of the same *shape* at different sizes, so
    the cell proportions are preserved and only the magnitude changes. Counts
    stay multiples of three to keep prompt-family balance, and each pattern is
    capped at the rows actually available — most patterns hold 132 rows, i.e.
    44 complete seeds, so scale saturates rather than failing.
    """
    plan: list[tuple[Cell, tuple[tuple[str, int], ...]]] = []
    for cell in CELLS:
        counts: list[tuple[str, int]] = []
        for pattern, count in cell.patterns:
            # `body_scale` thins only the patterns that answer with the shared
            # renderer body, leaving the render *subskill* cells intact: those
            # teach classification, conversion and formatting without emitting
            # the block whose over-exposure is trained in as a bad habit.
            if pattern in BODY_PATTERNS:
                count = max(len(FAMILIES), round(count * body_scale))
            if cell.family_balanced:
                seeds_available = len(index.complete_seeds(pattern))
                wanted = max(1, round(count * scale / len(FAMILIES)))
                counts.append((pattern, min(wanted, seeds_available) * len(FAMILIES)))
            else:
                available = sum(
                    len(families)
                    for families in index.by_pattern.get(pattern, {}).values()
                )
                counts.append((pattern, min(max(1, round(count * scale)), available)))
        plan.append((cell, tuple(counts)))
    return plan


def select(
    rows: list[dict],
    approved: set[str],
    scale: float = 1.0,
    diversify: bool = False,
    body_scale: float = 1.0,
) -> list[dict]:
    """Fill every declared cell, failing closed rather than under-filling."""
    index = Index.build(rows)
    plan = scaled_cells(index, scale, body_scale)
    allocator = Allocator(
        index,
        sum(c for _, counts in plan for _, c in counts),
        diversify=diversify,
    )
    selected: list[dict] = []
    seen: set[str] = set()

    for cell, counts in plan:
        for pattern, count in counts:
            if pattern not in approved:
                raise CurriculumError(f"{pattern} is not an approved pattern")
            picked = _pick(index, allocator, cell, pattern, count)
            for row in picked:
                if row["row_id"] in seen:
                    raise CurriculumError(f"duplicate row {row['row_id']}")
                seen.add(row["row_id"])
                selected.append(
                    {**row, "capability": cell.capability, "cell_role": cell.role}
                )
    return selected


def _pick(
    index: Index,
    allocator: Allocator,
    cell: Cell,
    pattern: str,
    count: int,
) -> list[dict]:
    available = index.by_pattern.get(pattern, {})
    if not available:
        raise CurriculumError(f"{pattern} has no rows in the candidate pool")

    if not cell.family_balanced:
        rows = [
            row
            for seed in sorted(available)
            for _, row in sorted(available[seed].items())
        ]
        if len(rows) < count:
            raise CurriculumError(
                f"{pattern} offers {len(rows)} rows, cell needs {count}"
            )
        return rows[:count]

    if count % len(FAMILIES):
        raise CurriculumError(f"{pattern} count {count} is not a multiple of 3")
    wanted = count // len(FAMILIES)
    in_group = cell.contrast_group and pattern in CONTRAST_GROUPS[cell.contrast_group]
    if in_group:
        seeds = [
            seed
            for seed in allocator.contrast_seeds(cell.contrast_group, wanted)
            if seed in available
        ][:wanted]
        if len(seeds) < wanted:
            raise CurriculumError(
                f"{pattern} shares {len(seeds)} group seeds, cell needs {wanted}"
            )
    else:
        seeds = allocator.take(pattern, index.complete_seeds(pattern), wanted)
    return [available[seed][family] for seed in seeds for family in FAMILIES]


def _marginal(selected: list[dict], key: str, targets: dict[str, float] | None) -> dict:
    """Report one marginal against its declared target, deviations included."""
    counts = collections.Counter(row[key] for row in selected)
    total = len(selected)
    report: dict = {"counts": dict(sorted(counts.items()))}
    if targets is None:
        return report
    report["shares"] = {k: round(v / total, 4) for k, v in sorted(counts.items())}
    report["targets"] = targets
    report["deviations"] = {
        label: round(counts.get(label, 0) / total - target, 4)
        for label, target in sorted(targets.items())
        if abs(counts.get(label, 0) / total - target) > 0.02
    }
    report["untargeted_labels"] = sorted(set(counts) - set(targets))
    missing = [
        label for label in MANDATORY_STRATA.get(key, ()) if not counts.get(label)
    ]
    if missing:
        report["missing_mandatory_strata"] = missing
    return report


def seed_diversity(selected: list[dict]) -> dict:
    """Report content concentration — the defect the cell report used to hide."""
    counts = collections.Counter(row["seed_id"] for row in selected)
    total = len(selected)
    top = counts.most_common(5)
    return {
        "distinct_seeds": len(counts),
        "max_seed_rows": top[0][1] if top else 0,
        "max_seed_share": round(top[0][1] / total, 4) if top else 0.0,
        "top5_share": round(sum(n for _, n in top) / total, 4),
    }


def coverage(selected: list[dict]) -> dict:
    """Report every marginal the pipeline declares, not only the new cells.

    The first version of this function reported roles, families, capabilities,
    patterns and domains — the dimensions the *previous* selector got wrong —
    and nothing the previous selector actually constrained. It therefore
    reported a healthy-looking curriculum while property and operation shares
    were far off profile and 89% of rows came from five seeds.
    """
    contrast_seeds = {
        group: sorted(
            {
                row["seed_id"]
                for row in selected
                if row["pattern_id"] in CONTRAST_GROUPS[group]
            }
        )
        for group in CONTRAST_GROUPS
    }
    return {
        "total": len(selected),
        "seed_diversity": seed_diversity(selected),
        "marginals": {
            "role": _marginal(selected, "cell_role", ROLE_TARGETS),
            "domain": _marginal(selected, "domain", DOMAIN_TARGETS),
            "source_kind": _marginal(selected, "source_kind", SOURCE_KIND_TARGETS),
            "property": _marginal(selected, "property", PROPERTY_TARGETS),
            "operation": _marginal(selected, "operation", None),
            "prompt_family": _marginal(selected, "prompt_family", None),
        },
        "marginal_notes": MARGINAL_NOTES,
        "capabilities": dict(
            sorted(collections.Counter(row["capability"] for row in selected).items())
        ),
        "patterns": dict(
            sorted(collections.Counter(row["pattern_id"] for row in selected).items())
        ),
        "contrast_seed_counts": {
            group: len(seeds) for group, seeds in contrast_seeds.items()
        },
    }


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _render(root: Path, selected: list[dict], destination: Path, benchmark: Path):
    """Render the selection into a chat handoff using the SP5 renderer."""
    import sys

    sys.path.insert(0, str(root / "src"))

    from satyrn_model.training import (
        PYTHON_CODE_SYSTEM_PROMPT,
        LineagedTask,
        render_training_handoff,
    )

    from satyrn_model.contracts import TaskRecord, load_snapshot
    from satyrn_model.policies.registry import TrustedPolicyRegistry
    from satyrn_model.policies.tstring import TStringPolicy

    registry = TrustedPolicyRegistry()
    registry.register(TStringPolicy())
    snapshot = load_snapshot(root / "corpus/tstrings.jsonl", registry=registry)
    tasks = {task.id: task for task in snapshot.tasks}

    seed_ids: dict[str, set[str]] = collections.defaultdict(set)
    for record in _read_jsonl(root / "reports/lineage.jsonl"):
        seed_ids[record["row_id"]].update(record.get("seed_ids", ()))

    rows = [
        LineagedTask(
            task=tasks[item["row_id"]],
            seed_ids=tuple(sorted(seed_ids[item["row_id"]]))
            or (f"seed-independent:{item['row_id']}",),
            prompt_family=item["prompt_family"],
        )
        for item in selected
    ]
    return render_training_handoff(
        rows,
        benchmark=tuple(TaskRecord.from_dict(r) for r in _read_jsonl(benchmark)),
        validation_fraction=0.10,
        split_seed=17,
        output_dir=destination,
        system_prompt=PYTHON_CODE_SYSTEM_PROMPT,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sp5_root", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmark/repair-v1/tasks.jsonl"),
        help="Benchmark the rendered rows are checked against for contamination.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Multiply every cell count; clamped to pool availability.",
    )
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Write the selection and coverage report without rendering.",
    )
    parser.add_argument(
        "--body-scale",
        type=float,
        default=1.0,
        help="Thin the patterns answering with the shared render_template "
        "body. 1.0 keeps current weights; see BODY_PATTERNS for why lower.",
    )
    parser.add_argument(
        "--diversify",
        action="store_true",
        help="Break ties toward unused program shapes rather than unused seeds.",
    )
    args = parser.parse_args()
    root = args.sp5_root.resolve()

    candidates = _read_jsonl(root / "reports/pilot-candidates.jsonl")
    approved = {
        row["pattern_id"] for row in _read_jsonl(root / "patterns/approvals.jsonl")
    }
    selected = select(
        candidates,
        approved,
        scale=args.scale,
        diversify=args.diversify,
        body_scale=args.body_scale,
    )
    report = coverage(selected)

    args.destination.mkdir(parents=True, exist_ok=True)
    (args.destination / "selection.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected)
    )
    if not args.select_only:
        handoff = _render(root, selected, args.destination, args.benchmark)
        report["rendered_fingerprint"] = handoff.rendered_fingerprint
        report["benchmark"] = str(args.benchmark)
    report["scale"] = args.scale
    (args.destination / "coverage.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
