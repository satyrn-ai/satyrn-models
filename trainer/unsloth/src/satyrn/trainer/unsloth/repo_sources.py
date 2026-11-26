"""Load JSONL files and GitHub repositories for Continued Pretraining (CPT)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

from datasets import Dataset
from git import GitCommandError, InvalidGitRepositoryError, Repo
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)

CPT_GROUPS_DIRECTORY = Path(__file__).resolve().parents[4] / "configs" / "datasets" / "cpt"


def read_rows(paths: str | list[str]) -> list[dict]:
    """Read the rows of one or more JSONL files."""
    path_list = [paths] if isinstance(paths, str) else paths
    rows: list[dict] = []
    for path in path_list:
        with Path(path).open(encoding="utf-8") as file_handle:
            file_rows = [json.loads(line) for line in file_handle if line.strip()]
            rows.extend(file_rows)
    return rows


def ensure_repository_cloned(url: str, sources_root: Path) -> Path:
    """Return the local directory for a git+https://github.com/<owner>/<project>[@<ref>] URL."""
    remainder = url.removeprefix("git+https://github.com/")
    path_part, _, reference = remainder.partition("@")
    owner, project = path_part.strip("/").removesuffix(".git").split("/")
    repository_directory = sources_root / owner / project
    if not repository_directory.exists():
        logger.info("Cloning %s/%s", owner, project)
        clone_kwargs = {"depth": 1, "branch": reference} if reference else {"depth": 1}
        clone_url = f"https://github.com/{owner}/{project}.git"
        Repo.clone_from(clone_url, repository_directory, **clone_kwargs)
    return repository_directory


def get_git_version(repository_directory: Path) -> str:
    """Return the checked-out git tag or short commit hash of repository_directory."""
    try:
        version = Repo(repository_directory).git.describe("--tags", "--always")
        return version
    except (InvalidGitRepositoryError, GitCommandError):
        return "main"


def iter_source_files(repository_directory: Path) -> Iterator[Path]:
    """Yield Python and documentation files in repository_directory in sorted order."""
    extensions = {".py", ".pyi", ".md", ".rst"}
    ignored = {".git", "__pycache__", "node_modules", "migrations", "locale", "build", "dist", "vendor", ".venv"}
    for root_path, directory_names, file_names in os.walk(repository_directory):
        kept_directories = [name for name in directory_names if name not in ignored]
        directory_names[:] = sorted(kept_directories)
        root = Path(root_path)
        for file_name in sorted(file_names):
            file_path = root / file_name
            if file_path.suffix in extensions and not file_path.is_symlink():
                yield file_path


def paginate_file(header: str, content: str, page_chars: int) -> Iterator[str]:
    """Split content on line boundaries into pages of at most page_chars, each starting with header."""
    body_budget = page_chars - len(header)
    page_lines: list[str] = []
    used_chars = 0

    for line in content.splitlines(keepends=True):
        if len(line) > 4096 or len(line) > body_budget:
            return
        if page_lines and used_chars + len(line) > body_budget:
            body = "".join(page_lines)
            yield f"{header}{body}\n"
            page_lines, used_chars = [], 0
        page_lines.append(line)
        used_chars += len(line)

    if page_lines:
        body = "".join(page_lines)
        yield f"{header}{body}\n"


def iter_repository_pages(repository_directory: Path, page_chars: int) -> Iterator[str]:
    """Yield pages of source code from repository_directory with project, version, and filename lines."""
    project = repository_directory.name
    owner = repository_directory.parent.name
    version = get_git_version(repository_directory)

    for file_path in iter_source_files(repository_directory):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if not content.strip():
            continue
        relative_path = file_path.relative_to(repository_directory).as_posix()
        header = (
            f"### Project: {project}\n"
            f"### Version: {version}\n"
            f"### Filename: github/{owner}/{project}/@{version}/{relative_path}\n\n"
        )
        yield from paginate_file(header, content, page_chars)


def expand_cpt_entries(entries: str | list[str], groups_directory: Path) -> list[str]:
    """Expand any CPT group names (e.g. 'web') using YAML files in groups_directory."""
    entry_list = [entries] if isinstance(entries, str) else list(entries)
    expanded: list[str] = []
    for entry in entry_list:
        group_file = groups_directory / f"{entry}.yaml"
        group_entries = list(OmegaConf.load(group_file)) if group_file.is_file() else [entry]
        expanded.extend(group_entries)
    return expanded


def load_cpt_dataset(
    entries: str | list[str],
    sequence_length: int,
    sources_root: Path = Path("datasets/sources"),
    groups_directory: Path = CPT_GROUPS_DIRECTORY,
) -> Dataset:
    """Load CPT dataset rows from JSONL files, group names, and git+https:// repositories."""
    page_chars = int(sequence_length * 2.6)
    rows: list[dict[str, str]] = []

    for entry in expand_cpt_entries(entries, groups_directory):
        if entry.startswith("git+https://"):
            repository_directory = ensure_repository_cloned(entry, sources_root)
            pages = list(iter_repository_pages(repository_directory, page_chars))
            total_chars = sum(len(page) for page in pages)
            kilobytes = total_chars / 1024
            logger.info(
                "Loaded %s/%s: %d pages, %.1f kB",
                repository_directory.parent.name,
                repository_directory.name,
                len(pages),
                kilobytes,
            )
            page_rows = [{"text": page} for page in pages]
            rows.extend(page_rows)
        else:
            jsonl_rows = read_rows(entry)
            rows.extend(jsonl_rows)

    dataset = Dataset.from_list(rows)
    return dataset
