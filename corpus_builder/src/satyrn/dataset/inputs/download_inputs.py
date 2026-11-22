"""Download PEP, whatsnew, and GitHub source repository inputs."""

import logging
import subprocess
import urllib.request
from pathlib import Path

import click
import yaml

logger = logging.getLogger(__name__)

DATASETS_DIRECTORY = Path(__file__).parents[5] / "datasets"


def load_manifest(file_name: str) -> dict:
    """Read a YAML manifest from the inputs directory."""
    manifest_path = Path(__file__).parent / file_name
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_data = yaml.safe_load(manifest_text)
    return manifest_data


def parse_github_repo(spec: str) -> tuple[str, str, str | None]:
    """Parse https://github.com/<owner>/<repository>[@<reference>] into (owner, repository, reference)."""
    prefix = "https://github.com/"
    if not spec.startswith(prefix):
        raise click.ClickException(f"Expected {prefix}<owner>/<repo>[@<ref>], got: {spec}")
    remainder = spec.removeprefix(prefix)
    path_part, _, reference = remainder.partition("@")
    parts = path_part.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise click.ClickException(f"Expected {prefix}<owner>/<repo>[@<ref>], got: {spec}")
    owner, repository = parts
    resolved_reference = reference or None
    return owner, repository, resolved_reference


def is_commit_sha(reference: str) -> bool:
    """Return True if reference is a 40-character hexadecimal commit hash."""
    hex_digits = set("0123456789abcdefABCDEF")
    is_sha = len(reference) == 40 and all(char in hex_digits for char in reference)
    return is_sha


def clone_repository(owner: str, repository: str, reference: str | None, destination: Path) -> None:
    """Shallow-clone owner/repository at reference into destination if missing."""
    if destination.exists():
        logger.info("Skipping existing %s/%s", owner, repository)
        return

    clone_url = f"https://github.com/{owner}/{repository}.git"
    logger.info("Cloning %s/%s (%s)", owner, repository, reference or "default")

    if reference is not None and is_commit_sha(reference):
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(destination)], check=True)
        subprocess.run(["git", "-C", str(destination), "fetch", "--depth", "1", clone_url, reference], check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "FETCH_HEAD"], check=True)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", "--depth", "1"]
    if reference is not None:
        command.extend(["--branch", reference])
    command.extend([clone_url, str(destination)])
    subprocess.run(command, check=True)


def download_doc_sources(target_version: str, categories: dict[str, dict[str, str]], datasets_directory: Path) -> None:
    """Download PEP and whatsnew documents for target_version."""
    for category, urls in categories.items():
        output_directory = datasets_directory / f"python{target_version}" / "input" / category
        output_directory.mkdir(parents=True, exist_ok=True)
        for document_name, url in urls.items():
            destination_path = output_directory / f"{document_name}.rst"
            logger.info("Python %s: Downloading %s", target_version, document_name)
            urllib.request.urlretrieve(url, destination_path)


def download_code_sources(entries: list[dict], datasets_directory: Path) -> None:
    """Shallow-clone each repository entry under datasets_directory/sources."""
    sources_directory = datasets_directory / "sources"
    for entry in entries:
        owner, repository, reference = parse_github_repo(entry["repo"])
        destination = sources_directory / owner / repository
        clone_repository(owner, repository, reference, destination)


@click.command("download-inputs")
@click.argument("target")
def main(target: str) -> None:
    """Download PEP/whatsnew docs (3.14, 3.15) or GitHub code sections (web, datasci, misc)."""
    doc_sources = load_manifest("sources-docs.yaml")
    code_sources = load_manifest("sources-code.yaml")

    if target in doc_sources:
        download_doc_sources(target, doc_sources[target], DATASETS_DIRECTORY)
        return

    if target in code_sources:
        download_code_sources(code_sources[target], DATASETS_DIRECTORY)
        return

    valid_targets = sorted([*doc_sources.keys(), *code_sources.keys()])
    joined_targets = ", ".join(valid_targets)
    raise click.ClickException(f"Unknown target '{target}'. Choose from: {joined_targets}")


if __name__ == "__main__":
    main()
