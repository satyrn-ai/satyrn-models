"""GitHub repository reference parsing, shallow cloning, and file filtering."""

import logging
import os
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import click
from git import GitCommandError, Repo

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GitHubRepo:
    """Represent a GitHub repository and optional git ref."""

    owner: str
    name: str
    ref: str | None = None

    @classmethod
    def from_url(cls, spec: str) -> "GitHubRepo":
        """Parse https://github.com/<owner>/<name>[@<ref>] into a GitHubRepo."""
        match = re.fullmatch(r"https://github\.com/([^/@]+)/([^/@]+?)(?:\.git)?(?:@([^/]+))?", spec)
        if match is None:
            raise click.ClickException(f"Expected https://github.com/<owner>/<repo>[@<ref>], got: {spec}")
        owner, name, ref = match.groups()
        return cls(owner=owner, name=name, ref=ref)

    @property
    def clone_url(self) -> str:
        """Return the HTTPS git clone URL."""
        url = f"https://github.com/{self.owner}/{self.name}.git"
        return url

    def shallow_clone(self, destination: Path) -> bool:
        """Shallow-clone this repository at ref into destination; return False if already present."""
        if destination.exists():
            logger.info("Skipping existing %s/%s", self.owner, self.name)
            return False

        target = self.ref or "HEAD"
        logger.info("Cloning %s/%s (%s)", self.owner, self.name, target)
        repo = Repo.init(destination)
        try:
            remote = repo.create_remote("origin", self.clone_url)
            try:
                # Preserve tag refs locally so `git describe --tags` resolves the tag name instead of a short SHA
                remote.fetch(f"refs/tags/{target}:refs/tags/{target}", depth=1)
            except GitCommandError:
                remote.fetch(target, depth=1)
            repo.git.checkout("FETCH_HEAD")
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return True


def should_exclude(path: Path, repository_directory: Path, excludes: set[str]) -> bool:
    """Return True if path matches any basename or repository-relative entry in excludes."""
    relative_path = path.relative_to(repository_directory).as_posix()
    excluded = path.name in excludes or relative_path in excludes
    return excluded


def walk_source_files(repository_directory: Path, include_path: Path, excludes: set[str]) -> Iterator[Path]:
    """Yield source files under include_path in sorted order."""
    extensions = {".py", ".pyi", ".md"}
    ignored_directories = {
        ".git",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        ".venv",
        "migrations",
        "locale",
        "NEWS.d",
        "test",
        "tests",
        "testing",
        "benchmarks",
        "asv_bench",
    }

    if include_path.is_file():
        if include_path.suffix in extensions and not should_exclude(include_path, repository_directory, excludes):
            yield include_path
        return

    for root_path, directory_names, file_names in os.walk(include_path):
        root = Path(root_path)
        if root.name in {"doc", "docs"} and "en" in directory_names and "en" not in excludes:
            kept_directories = ["en"]
        else:
            kept_directories = [
                name
                for name in directory_names
                if name not in ignored_directories and not should_exclude(root / name, repository_directory, excludes)
            ]
        directory_names[:] = sorted(kept_directories)

        for file_name in sorted(file_names):
            file_path = root / file_name
            if file_path.suffix not in extensions or file_path.is_symlink():
                continue
            if should_exclude(file_path, repository_directory, excludes):
                continue
            yield file_path


def is_source_file(file_path: Path, max_line_chars: int = 4096) -> bool:
    """Return True if file_path is usable source text, excluding non-UTF-8, empty, and >4096-char-line files."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    if not content.strip():
        return False
    usable = all(len(line) <= max_line_chars for line in content.splitlines())
    return usable


def prune_repository(repository_directory: Path, includes: list[str], excludes: set[str]) -> None:
    """Delete files outside the curated include/exclude set while preserving .git."""
    kept_files: set[Path] = set()
    for include_item in includes:
        include_path = repository_directory / include_item
        if not include_path.exists():
            raise click.ClickException(f"Configured include path not found: {include_path}")
        for file_path in walk_source_files(repository_directory, include_path, excludes):
            if is_source_file(file_path):
                kept_files.add(file_path)

    for root_path, directory_names, file_names in os.walk(repository_directory, topdown=False):
        root = Path(root_path)
        if ".git" in root.relative_to(repository_directory).parts:
            continue
        for file_name in file_names:
            file_path = root / file_name
            if file_path not in kept_files:
                file_path.unlink()
        for directory_name in directory_names:
            if directory_name == ".git":
                continue
            directory_path = root / directory_name
            if not directory_path.is_symlink() and not any(directory_path.iterdir()):
                directory_path.rmdir()
