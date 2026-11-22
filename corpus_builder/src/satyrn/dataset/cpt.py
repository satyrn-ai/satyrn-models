"""Continued Pretraining (CPT) dataset generation."""

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import click
from git import Repo
from sphinx.application import Sphinx

from satyrn.dataset.inputs.collect_code_repos import GitHubRepo


def render_markdown(input_dir: Path, output_dir: Path) -> None:
    """Render every .rst under input_dir to Markdown in output_dir, preserving directory structure."""
    doc_paths = sorted(input_dir.rglob("*.rst"))
    if not doc_paths:
        raise click.ClickException(f"No .rst files found under {input_dir}")
    root_doc = doc_paths[0].relative_to(input_dir).with_suffix("").as_posix()  # set the root of the documentation tree

    # Use sphinx markdown builder to convert docs from rST to md files and place in temporary directories
    with tempfile.TemporaryDirectory() as confdir, tempfile.TemporaryDirectory() as doctree_dir:
        conf_py = 'project = "satyrn-cpt"\nextensions = ["sphinx_markdown_builder"]\n'
        Path(confdir, "conf.py").write_text(conf_py)
        app = Sphinx(
            srcdir=str(input_dir),
            confdir=confdir,
            outdir=str(output_dir),
            doctreedir=doctree_dir,
            buildername="markdown",
            confoverrides={"root_doc": root_doc},
            warning=None,
        )
        app.builder.epilog = "\n"
        app.build()


def find_repositories(input_dir: Path) -> list[Path]:
    """Return cloned git repository roots inside input_dir."""
    if (input_dir / ".git").is_dir():
        return [input_dir]
    repositories = sorted(git_dir.parent for git_dir in input_dir.glob("*/*/.git") if git_dir.is_dir())
    return repositories


def walk_repository_files(repository_directory: Path) -> Iterator[Path]:
    """Yield non-.git files under repository_directory in sorted order."""
    for root_path, directory_names, file_names in os.walk(repository_directory):
        directory_names[:] = sorted(name for name in directory_names if name != ".git")
        root = Path(root_path)
        for file_name in sorted(file_names):
            yield root / file_name


def build_repo_rows(repositories: list[Path]) -> list[dict[str, str]]:
    """Collect files from cloned repositories into CPT JSONL rows."""
    rows: list[dict[str, str]] = []
    for repository_directory in repositories:
        git_repo = Repo(repository_directory)
        github_repo = GitHubRepo.from_url(git_repo.remotes.origin.url)
        version = git_repo.git.describe("--tags", "--always")

        for file_path in walk_repository_files(repository_directory):
            content = file_path.read_text(encoding="utf-8")
            relative_path = file_path.relative_to(repository_directory).as_posix()
            filename = f"github/{github_repo.owner}/{github_repo.name}/@{version}/{relative_path}"
            header = f"### Project: {github_repo.name}\n### Version: {version}\n### Filename: {relative_path}\n\n"
            rows.append({"filename": filename, "text": f"{header}{content}\n"})
    return rows


@click.command("cpt")
@click.option(
    "-i",
    "--input",
    "--input-dir",
    "input_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory of .rst docs or cloned repositories to draw from.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write the generated dataset to.",
)
def main(input_dir: Path, output_path: Path) -> None:
    """Generate a Continued Pretraining (CPT) dataset."""
    if output_path.suffix != ".jsonl":
        raise click.BadParameter("Output file must end with .jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    repositories = find_repositories(input_dir)
    if repositories:
        rows = build_repo_rows(repositories)
    else:
        with tempfile.TemporaryDirectory() as markdown_dir:
            # Convert the input docs to markdown
            render_markdown(input_dir, Path(markdown_dir))
            rows = [
                {
                    "filename": path.relative_to(markdown_dir).with_suffix(".rst").as_posix(),
                    "text": path.read_text(),
                }
                for path in sorted(Path(markdown_dir).rglob("*.md"))
            ]

    with output_path.open("w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(row) + "\n" for row in rows)

    click.secho(f"Wrote {len(rows)} Continued Pretraining rows to ", nl=False, fg="green")
    click.secho(str(output_path), fg="green", bold=True)
