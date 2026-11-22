"""Download PEP, whatsnew, and curated GitHub repository inputs."""

import logging
import urllib.request
from pathlib import Path

import click
import yaml

from satyrn.dataset.inputs.collect_code_repos import GitHubRepo, prune_repository

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parents[5]
DATASETS_DIRECTORY = REPO_ROOT / "datasets"


def load_manifest(file_name: str) -> dict:
    """Read a YAML manifest from the inputs directory."""
    manifest_path = Path(__file__).parent / file_name
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest_data = yaml.safe_load(manifest_text)
    return manifest_data


def download_doc_sources(target_version: str, categories: dict[str, dict[str, str]], datasets_directory: Path) -> None:
    """Download PEP and whatsnew documents for target_version."""
    for category, urls in categories.items():
        output_directory = datasets_directory / "inputs" / category / f"python{target_version}"
        output_directory.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading Python %s %s to %s", target_version, category, output_directory)
        for document_name, url in urls.items():
            destination_path = output_directory / f"{document_name}.rst"
            logger.info("Python %s: Downloading %s", target_version, document_name)
            urllib.request.urlretrieve(url, destination_path)


def download_code_sources(section_name: str, entries: list[dict], datasets_directory: Path) -> None:
    """Shallow-clone and prune each repository entry under datasets_directory/inputs/repos/<section_name>."""
    section_directory = datasets_directory / "inputs" / "repos" / section_name
    logger.info("Downloading %s repositories to %s", section_name, section_directory)
    for entry in entries:
        repository = GitHubRepo.from_url(entry["repo"])
        destination = section_directory / repository.owner / repository.name
        cloned = repository.shallow_clone(destination)
        if cloned:
            includes = entry.get("include") or ["."]
            excludes = set(entry.get("exclude") or [])
            prune_repository(destination, includes, excludes)


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
        download_code_sources(target, code_sources[target], DATASETS_DIRECTORY)
        return

    valid_targets = sorted([*doc_sources.keys(), *code_sources.keys()])
    joined_targets = ", ".join(valid_targets)
    raise click.ClickException(f"Unknown target '{target}'. Choose from: {joined_targets}")


if __name__ == "__main__":
    main()
