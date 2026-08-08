import json
from collections import Counter
from pathlib import Path

from satyrn_model.authoring.composition import (
    capacity_deficits,
    capacity_report,
    load_composition_profile,
    select_composed_pilot,
    target_counts,
)
from satyrn_model.authoring.sampling import SampleRow


def _row(row_id: str, *, domain: str, property: str) -> SampleRow:
    return SampleRow(
        row_id=row_id,
        source_kind="authored",
        role="consumer",
        domain=domain,
        property=property,
        pattern_id=f"pattern-{property}",
        seed_id=f"seed-{row_id}",
    )


def test_capacity_gate_reports_each_unfillable_marginal(tmp_path: Path) -> None:
    profile_path = tmp_path / "composition.toml"
    profile_path.write_text(
        """\
[profile]
version = 2

[targets.property]
introspect = 0.50
construct = 0.50

[targets.domain]
html = 0.50
sql = 0.50
""",
        encoding="utf-8",
    )
    profile = load_composition_profile(profile_path)
    rows = [
        _row("1", domain="html", property="introspect"),
        _row("2", domain="html", property="introspect"),
        _row("3", domain="sql", property="introspect"),
    ]

    deficits = capacity_deficits(rows, profile, target_rows=4)

    observed = [
        (item.dimension, item.stratum, item.required, item.available)
        for item in deficits
    ]
    assert observed == [
        ("pool", "unique_rows", 4, 3),
        ("property", "construct", 2, 0),
        ("domain", "sql", 2, 1),
    ]
    report = capacity_report(rows, profile, 4)
    assert "property.construct: requires 2, available 0, short 2" in report


def test_capacity_gate_accepts_a_fillable_pool(tmp_path: Path) -> None:
    profile_path = tmp_path / "composition.toml"
    profile_path.write_text(
        """\
[profile]
version = 1

[targets.domain]
html = 0.50
sql = 0.50
""",
        encoding="utf-8",
    )
    profile = load_composition_profile(profile_path)
    rows = [
        _row("1", domain="html", property="introspect"),
        _row("2", domain="html", property="introspect"),
        _row("3", domain="sql", property="introspect"),
        _row("4", domain="sql", property="introspect"),
    ]

    assert capacity_deficits(rows, profile, target_rows=4) == []


def test_committed_profile_sets_exact_failed_operation_floors() -> None:
    root = Path(__file__).resolve().parents[2]
    profile = load_composition_profile(root / "composition.toml")

    assert profile.version == 5
    assert target_counts(500, profile.targets["operation"])["strings"] == 60
    assert target_counts(500, profile.targets["operation"])["values"] == 60
    assert target_counts(500, profile.targets["operation"])["render_template"] == 60


def test_selector_matches_all_marginals_exactly(tmp_path: Path) -> None:
    profile_path = tmp_path / "composition.toml"
    profile_path.write_text(
        """\
[profile]
version = 1

[targets.property]
introspect = 0.50
render_template = 0.50

[targets.domain]
html = 0.50
sql = 0.50
""",
        encoding="utf-8",
    )
    profile = load_composition_profile(profile_path)
    rows = [
        _row(f"h-i-{i}", domain="html", property="introspect")
        for i in range(4)
    ]
    rows += [
        _row(f"h-r-{i}", domain="html", property="render_template")
        for i in range(4)
    ]
    rows += [
        _row(f"s-i-{i}", domain="sql", property="introspect")
        for i in range(4)
    ]
    rows += [
        _row(f"s-r-{i}", domain="sql", property="render_template")
        for i in range(4)
    ]

    selected = select_composed_pilot(rows, profile, target_rows=8)

    assert sum(row.domain == "html" for row in selected) == 4
    assert sum(row.domain == "sql" for row in selected) == 4
    assert sum(row.property == "introspect" for row in selected) == 4
    assert sum(row.property == "render_template" for row in selected) == 4


def test_committed_pilot_matches_profile_v5_exactly() -> None:
    root = Path(__file__).resolve().parents[2]
    profile = load_composition_profile(root / "composition.toml")
    rows = [
        SampleRow(**json.loads(line))
        for line in (root / "reports/pilot.jsonl").read_text().splitlines()
        if line
    ]

    assert len(rows) == len({row.row_id for row in rows}) == 500
    for dimension, proportions in profile.targets.items():
        assert Counter(getattr(row, dimension) for row in rows) == target_counts(
            500, proportions
        )
