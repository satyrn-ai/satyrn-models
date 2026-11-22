"""Tests for YAML-driven download-inputs and decoupled repo CPT generation."""

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from git import Repo

from satyrn.dataset import cpt
from satyrn.dataset.inputs import download_inputs
from satyrn.dataset.inputs.collect_code_repos import GitHubRepo


def test_manifests_load_and_entries_are_valid() -> None:
    doc_sources = download_inputs.load_manifest("sources-docs.yaml")
    code_sources = download_inputs.load_manifest("sources-code.yaml")

    assert {"3.14", "3.15"} <= set(doc_sources)
    assert set(code_sources) == {"web", "datasci", "misc"}

    for entries in code_sources.values():
        for entry in entries:
            repository = GitHubRepo.from_url(entry["repo"])
            assert repository.owner
            assert repository.name
            assert repository.ref
            assert entry["include"]


def test_github_repo_from_url_validates_format() -> None:
    assert GitHubRepo.from_url("https://github.com/django/django@6.1.3") == GitHubRepo("django", "django", "6.1.3")
    assert GitHubRepo.from_url("https://github.com/pallets/flask") == GitHubRepo("pallets", "flask", None)

    with pytest.raises(click.ClickException):
        GitHubRepo.from_url("github://django/django")


def test_shallow_clone_preserves_tag_and_supports_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    upstream_dir = tmp_path / "upstream"
    upstream = Repo.init(upstream_dir)
    (upstream_dir / "app.py").write_text("v1\n", encoding="utf-8")
    upstream.index.add(["app.py"])
    first_sha = upstream.index.commit("v1").hexsha
    upstream.create_tag("3.1.3")

    (upstream_dir / "app.py").write_text("v2\n", encoding="utf-8")
    upstream.index.add(["app.py"])
    upstream.index.commit("v2")

    monkeypatch.setattr(GitHubRepo, "clone_url", property(lambda self: str(upstream_dir)))

    tag_dest = tmp_path / "tag_clone"
    assert GitHubRepo("pallets", "flask", "3.1.3").shallow_clone(tag_dest) is True
    assert GitHubRepo("pallets", "flask", "3.1.3").shallow_clone(tag_dest) is False
    assert Repo(tag_dest).git.describe("--tags", "--always") == "3.1.3"
    assert (tag_dest / "app.py").read_text(encoding="utf-8") == "v1\n"

    sha_dest = tmp_path / "sha_clone"
    assert GitHubRepo("ansible", "awx", first_sha).shallow_clone(sha_dest) is True
    assert (sha_dest / "app.py").read_text(encoding="utf-8") == "v1\n"


def test_download_code_sources_prunes_unwanted_files_and_keeps_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream_dir = tmp_path / "upstream"
    upstream = Repo.init(upstream_dir)
    (upstream_dir / "pydantic" / "_internal").mkdir(parents=True)
    (upstream_dir / "pydantic" / "tests").mkdir(parents=True)
    (upstream_dir / "docs" / "en").mkdir(parents=True)
    (upstream_dir / "docs" / "zh").mkdir(parents=True)

    (upstream_dir / "README.md").write_text("# Pydantic\n\n" + ("Validation.\n" * 20), encoding="utf-8")
    reexports = "# Copyright\n" + ("from .main import BaseModel\n" * 10)
    (upstream_dir / "pydantic" / "__init__.py").write_text(reexports, encoding="utf-8")
    (upstream_dir / "pydantic" / "main.py").write_text("class BaseModel:\n    pass\n", encoding="utf-8")
    (upstream_dir / "pydantic" / "_internal" / "gen.py").write_text("internal = 1\n", encoding="utf-8")
    (upstream_dir / "pydantic" / "tests" / "test_main.py").write_text("assert True\n", encoding="utf-8")
    (upstream_dir / "pydantic" / "blob.py").write_text("x = '" + ("a" * 5000) + "'\n", encoding="utf-8")
    (upstream_dir / "docs" / "en" / "guide.md").write_text("# Guide\n\n" + ("Guide text.\n" * 20), encoding="utf-8")
    (upstream_dir / "docs" / "en" / "legacy.rst").write_text("RST\n", encoding="utf-8")
    (upstream_dir / "docs" / "zh" / "guide.md").write_text("# ZH\n", encoding="utf-8")
    upstream.index.add(upstream.untracked_files)
    upstream.index.commit("init")
    upstream.create_tag("v2.14.4")

    monkeypatch.setattr(GitHubRepo, "clone_url", property(lambda self: str(upstream_dir)))

    entries = [
        {
            "repo": "https://github.com/pydantic/pydantic@v2.14.4",
            "include": ["pydantic", "docs", "README.md"],
            "exclude": ["_internal"],
        }
    ]
    download_inputs.download_code_sources("web", entries, tmp_path)

    cloned_dir = tmp_path / "inputs" / "repos" / "web" / "pydantic" / "pydantic"
    kept_files = sorted(path.relative_to(cloned_dir).as_posix() for path in cpt.walk_repository_files(cloned_dir))
    assert kept_files == ["README.md", "docs/en/guide.md", "pydantic/main.py"]
    assert (cloned_dir / ".git").is_dir()


def test_cpt_cli_writes_section_jsonl_without_manifest(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repos" / "web" / "pallets" / "flask"
    (repo_dir / "src" / "flask").mkdir(parents=True)
    (repo_dir / "src" / "flask" / "app.py").write_text("class Flask:\n    pass\n", encoding="utf-8")

    repo = Repo.init(repo_dir)
    repo.create_remote("origin", "https://github.com/pallets/flask.git")
    repo.index.add(["src/flask/app.py"])
    repo.index.commit("release")
    repo.create_tag("3.1.3")

    out_path = tmp_path / "out" / "web.jsonl"
    result = CliRunner().invoke(cpt.main, ["--input", str(tmp_path / "repos" / "web"), "--output", str(out_path)])

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "filename": "github/pallets/flask/@3.1.3/src/flask/app.py",
            "text": (
                "### Project: flask\n### Version: 3.1.3\n### Filename: src/flask/app.py\n\nclass Flask:\n    pass\n\n"
            ),
        }
    ]


def test_download_inputs_cli_rejects_unknown_target() -> None:
    result = CliRunner().invoke(download_inputs.main, ["unknown-target"])
    assert result.exit_code != 0
    assert "Unknown target 'unknown-target'" in result.output
