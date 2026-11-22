"""Tests for loading cloned GitHub repositories into CPT pages and rows."""

from pathlib import Path

import pytest

from satyrn.trainer.unsloth import repo_sources


def test_cpt_group_yaml_files_exist_and_expand() -> None:
    for group_name in ("web", "datasci", "misc"):
        urls = repo_sources.expand_cpt_entries(group_name, repo_sources.CPT_GROUPS_DIRECTORY)
        assert urls
        assert all(url.startswith("git+https://github.com/") for url in urls)


def test_ensure_repository_cloned_invokes_clone_from_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Path, dict]] = []

    def fake_clone_from(url: str, to_path: Path, **kwargs: object) -> None:
        calls.append((url, to_path, kwargs))
        to_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(repo_sources.Repo, "clone_from", fake_clone_from)

    first = repo_sources.ensure_repository_cloned("git+https://github.com/django/django@5.2", tmp_path)
    second = repo_sources.ensure_repository_cloned("git+https://github.com/django/django@5.2", tmp_path)

    assert first == tmp_path / "django" / "django"
    assert second == first
    assert calls == [
        ("https://github.com/django/django.git", tmp_path / "django" / "django", {"depth": 1, "branch": "5.2"})
    ]


def test_iter_repository_pages_formats_header_and_skips_ignored_dirs(tmp_path: Path) -> None:
    repository_directory = tmp_path / "django" / "django"
    (repository_directory / "db").mkdir(parents=True)
    (repository_directory / ".git").mkdir()
    (repository_directory / "migrations").mkdir()

    (repository_directory / "db" / "models.py").write_text("class Model:\n    pass\n", encoding="utf-8")
    (repository_directory / ".git" / "config.py").write_text("secret = 1\n", encoding="utf-8")
    (repository_directory / "migrations" / "0001.py").write_text("migrated = 1\n", encoding="utf-8")
    (repository_directory / "image.png").write_bytes(b"\x89PNG\r\n")

    pages = list(repo_sources.iter_repository_pages(repository_directory, page_chars=2000))

    assert pages == [
        "### Project: django\n"
        "### Version: main\n"
        "### Filename: github/django/django/@main/db/models.py\n\n"
        "class Model:\n"
        "    pass\n\n"
    ]


def test_paginate_file_splits_on_lines_and_repeats_header() -> None:
    header = "### Project: flask\n### Version: 3.1.0\n### Filename: github/pallets/flask/@3.1.0/app.py\n\n"
    content = "line_one = 1\nline_two = 2\nline_three = 3\n"
    two_lines_budget = len(header) + len("line_one = 1\nline_two = 2\n")

    pages = list(repo_sources.paginate_file(header, content, page_chars=two_lines_budget))

    assert pages == [
        f"{header}line_one = 1\nline_two = 2\n\n",
        f"{header}line_three = 3\n\n",
    ]


def test_paginate_file_skips_minified_long_lines() -> None:
    header = "### Project: app\n### Version: main\n### Filename: github/org/app/@main/blob.py\n\n"
    content = "x = '" + ("a" * 5000) + "'\n"

    pages = list(repo_sources.paginate_file(header, content, page_chars=10000))

    assert pages == []


def test_load_cpt_dataset_combines_jsonl_and_group(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "cpt.jsonl"
    jsonl_path.write_text('{"text": "doc from jsonl"}\n', encoding="utf-8")

    groups_directory = tmp_path / "groups"
    groups_directory.mkdir()
    (groups_directory / "web.yaml").write_text("- git+https://github.com/pallets/flask\n", encoding="utf-8")

    repository_directory = tmp_path / "sources" / "pallets" / "flask"
    repository_directory.mkdir(parents=True)
    (repository_directory / "app.py").write_text("class Flask:\n    pass\n", encoding="utf-8")

    dataset = repo_sources.load_cpt_dataset(
        [str(jsonl_path), "web"],
        sequence_length=512,
        sources_root=tmp_path / "sources",
        groups_directory=groups_directory,
    )

    texts = list(dataset["text"])
    assert len(texts) == 2
    assert texts[0] == "doc from jsonl"
    assert "### Project: flask\n" in texts[1]
    assert "### Filename: github/pallets/flask/@main/app.py\n" in texts[1]
