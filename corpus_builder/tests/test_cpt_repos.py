"""Tests for YAML-driven download-inputs and curated repo CPT generation."""

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from satyrn.dataset import cpt
from satyrn.dataset.inputs import download_inputs


def test_manifests_load_and_entries_are_valid() -> None:
    doc_sources = download_inputs.load_manifest("sources-docs.yaml")
    code_sources = download_inputs.load_manifest("sources-code.yaml")

    assert {"3.14", "3.15"} <= set(doc_sources)
    assert set(code_sources) == {"web", "datasci", "misc"}

    for entries in code_sources.values():
        for entry in entries:
            owner, repo, reference = download_inputs.parse_github_repo(entry["repo"])
            assert owner
            assert repo
            assert reference
            assert entry["include"]


def test_parse_github_repo_validates_format() -> None:
    assert download_inputs.parse_github_repo("https://github.com/django/django@6.1.3") == (
        "django",
        "django",
        "6.1.3",
    )
    assert download_inputs.parse_github_repo("https://github.com/pallets/flask") == ("pallets", "flask", None)

    with pytest.raises(click.ClickException):
        download_inputs.parse_github_repo("github://django/django")


def test_download_code_sources_clones_tags_and_shas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> None:
        commands.append(command)
        if command[:2] == ["git", "clone"]:
            Path(command[-1]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(download_inputs.subprocess, "run", fake_run)

    sha = "f323b9ae61e5ae4237355bd4b584d52ac55cfdd6"
    entries = [
        {"repo": "https://github.com/pallets/flask@3.1.3"},
        {"repo": f"https://github.com/ansible/awx@{sha}"},
    ]
    download_inputs.download_code_sources(entries, tmp_path)
    download_inputs.download_code_sources(entries, tmp_path)

    flask_dest = tmp_path / "sources" / "pallets" / "flask"
    awx_dest = tmp_path / "sources" / "ansible" / "awx"
    assert commands == [
        ["git", "clone", "--depth", "1", "--branch", "3.1.3", "https://github.com/pallets/flask.git", str(flask_dest)],
        ["git", "init", str(awx_dest)],
        ["git", "-C", str(awx_dest), "fetch", "--depth", "1", "https://github.com/ansible/awx.git", sha],
        ["git", "-C", str(awx_dest), "checkout", "FETCH_HEAD"],
    ]


def test_build_repo_rows_applies_include_exclude_and_ignores(tmp_path: Path) -> None:
    repo_dir = tmp_path / "sources" / "pydantic" / "pydantic"
    (repo_dir / "pydantic" / "_internal").mkdir(parents=True)
    (repo_dir / "pydantic" / "tests").mkdir(parents=True)
    (repo_dir / "docs" / "en").mkdir(parents=True)
    (repo_dir / "docs" / "zh").mkdir(parents=True)

    (repo_dir / "README.md").write_text("# Pydantic\n", encoding="utf-8")
    (repo_dir / "pydantic" / "main.py").write_text("class BaseModel:\n    pass\n", encoding="utf-8")
    (repo_dir / "pydantic" / "_internal" / "gen.py").write_text("internal = 1\n", encoding="utf-8")
    (repo_dir / "pydantic" / "tests" / "test_main.py").write_text("assert True\n", encoding="utf-8")
    (repo_dir / "pydantic" / "blob.py").write_text("x = '" + ("a" * 5000) + "'\n", encoding="utf-8")
    (repo_dir / "docs" / "en" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (repo_dir / "docs" / "en" / "legacy.rst").write_text("RST\n", encoding="utf-8")
    (repo_dir / "docs" / "zh" / "guide.md").write_text("# ZH\n", encoding="utf-8")

    entries = [
        {
            "repo": "https://github.com/pydantic/pydantic@v2.14.4",
            "include": ["pydantic", "docs", "README.md"],
            "exclude": ["_internal"],
        }
    ]
    rows = cpt.build_repo_rows(entries, tmp_path / "sources")

    filenames = [row["filename"] for row in rows]
    assert filenames == [
        "github/pydantic/pydantic/@v2.14.4/pydantic/main.py",
        "github/pydantic/pydantic/@v2.14.4/docs/en/guide.md",
        "github/pydantic/pydantic/@v2.14.4/README.md",
    ]
    assert rows[0]["text"] == (
        "### Project: pydantic\n"
        "### Version: v2.14.4\n"
        "### Filename: github/pydantic/pydantic/@v2.14.4/pydantic/main.py\n\n"
        "class BaseModel:\n"
        "    pass\n\n"
    )


def test_cpt_cli_writes_section_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_dir = tmp_path / "sources" / "pallets" / "flask" / "src" / "flask"
    repo_dir.mkdir(parents=True)
    (repo_dir / "app.py").write_text("class Flask:\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(cpt, "DATASETS_DIRECTORY", tmp_path)
    monkeypatch.setattr(
        cpt,
        "load_manifest",
        lambda name: {"web": [{"repo": "https://github.com/pallets/flask@3.1.3", "include": ["src/flask"]}]},
    )

    out_path = tmp_path / "out" / "web.jsonl"
    result = CliRunner().invoke(cpt.main, ["--input", "web", "--output", str(out_path)])

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["filename"] == "github/pallets/flask/@3.1.3/src/flask/app.py"


def test_download_inputs_cli_rejects_unknown_target() -> None:
    result = CliRunner().invoke(download_inputs.main, ["unknown-target"])
    assert result.exit_code != 0
    assert "Unknown target 'unknown-target'" in result.output
