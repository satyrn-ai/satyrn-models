"""End-to-end behavior of the SP5 authoring commands."""

import dataclasses
import json

import pytest

from satyrn_model.authoring.cli import cmd_build, cmd_pilot
from satyrn_model.authoring.models import Seed, seed_id
from satyrn_model.authoring.sampling import SampleRow
from satyrn_model.authoring.seeds import write_seeds_jsonl


def test_cmd_build_refuses_extracted_seeds_without_occurrence_ledger(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    bindings = (("name", '"World"'),)
    seed = Seed(
        id=seed_id('t"Hello {name}"', bindings),
        literal='t"Hello {name}"',
        free_names=("name",),
        bindings=bindings,
        occurrence_ids=("occ-unresolved",),
        kind="extracted",
    )
    write_seeds_jsonl([seed], tmp_path / "seeds/extracted.jsonl")

    with pytest.raises(SystemExit):
        cmd_build()

    assert "occurrences.jsonl is missing" in capsys.readouterr().out


def test_cmd_pilot_selects_built_rows_and_writes_calibration(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "sampling.toml").write_text(
        """\
[plan]
target_rows = 2
nested_order = ["source_kind"]

[plan.strata.source_kind]
authored = 0.50
extracted = 0.50
""",
        encoding="utf-8",
    )
    (tmp_path / "composition.toml").write_text(
        "[profile]\nversion = 3\n", encoding="utf-8"
    )
    candidates = [
        SampleRow(
            row_id="authored-row",
            source_kind="authored",
            property="introspect",
            pattern_id="intro-strings",
            seed_id="seed-a",
        ),
        SampleRow(
            row_id="extracted-row",
            source_kind="extracted",
            property="render_template",
            pattern_id="render-template",
            seed_id="seed-b",
        ),
    ]
    (tmp_path / "reports/pilot-candidates.jsonl").write_text(
        "".join(
            json.dumps(dataclasses.asdict(row), sort_keys=True) + "\n"
            for row in candidates
        ),
        encoding="utf-8",
    )

    cmd_pilot()

    selected = (tmp_path / "reports/pilot.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(selected) == 2
    calibration = json.loads(
        (tmp_path / "reports/threshold-derivation.json").read_text(encoding="utf-8")
    )
    assert calibration["profile_version"] == 3
    assert calibration["target_rows"] == 2
    assert (tmp_path / "reports/threshold-derivation.md").exists()
