"""Continued Pretraining (CPT) dataset generation."""

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import click
from sphinx.application import Sphinx

from satyrn.dataset.inputs.download_inputs import DATASETS_DIRECTORY, load_manifest, parse_github_repo


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


def should_exclude(path: Path, repository_directory: Path, excludes: set[str]) -> bool:
    """Return True if path matches any basename or repository-relative entry in excludes."""
    relative_path = path.relative_to(repository_directory).as_posix()
    excluded = path.name in excludes or relative_path in excludes
    return excluded


def iter_included_files(repository_directory: Path, include_path: Path, excludes: set[str]) -> Iterator[Path]:
    """Yield .py, .pyi, and .md files under include_path in sorted order."""
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


def has_oversized_line(content: str, max_line_chars: int = 4096) -> bool:
    """Return True if any line in content exceeds max_line_chars."""
    oversized = any(len(line) > max_line_chars for line in content.splitlines())
    return oversized


def build_repo_rows(entries: list[dict], sources_directory: Path) -> list[dict[str, str]]:
    """Collect filtered source files from cloned repositories into CPT JSONL rows."""
    rows: list[dict[str, str]] = []
    seen_filenames: set[str] = set()

    for entry in entries:
        owner, project, reference = parse_github_repo(entry["repo"])
        repository_directory = sources_directory / owner / project
        if not repository_directory.is_dir():
            raise click.ClickException(
                f"Repository not found at {repository_directory}. Run 'satyrn-dataset download-inputs' first."
            )

        version = reference or "main"
        includes = entry.get("include") or ["."]
        excludes = set(entry.get("exclude") or [])

        for include_item in includes:
            include_path = repository_directory / include_item
            if not include_path.exists():
                raise click.ClickException(f"Configured include path not found: {include_path}")

            for file_path in iter_included_files(repository_directory, include_path, excludes):
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if not content.strip() or has_oversized_line(content):
                    continue

                relative_path = file_path.relative_to(repository_directory).as_posix()
                filename = f"github/{owner}/{project}/@{version}/{relative_path}"
                if filename in seen_filenames:
                    continue
                seen_filenames.add(filename)

                header = f"### Project: {project}\n### Version: {version}\n### Filename: {filename}\n\n"
                rows.append({"filename": filename, "text": f"{header}{content}\n"})

    return rows


@click.command("cpt")
@click.option(
    "-i",
    "--input",
    "--input-dir",
    "input_source",
    required=True,
    help="Directory of .rst docs or code section name (web, datasci, misc).",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write the generated dataset to.",
)
def main(input_source: str, output_path: Path) -> None:
    """Generate a Continued Pretraining (CPT) dataset."""
    if output_path.suffix != ".jsonl":
        raise click.BadParameter("Output file must end with .jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    code_sources = load_manifest("sources-code.yaml")
    if input_source in code_sources:
        sources_directory = DATASETS_DIRECTORY / "sources"
        rows = build_repo_rows(code_sources[input_source], sources_directory)
    else:
        input_dir = Path(input_source)
        if not input_dir.is_dir():
            raise click.ClickException(f"Directory '{input_source}' does not exist.")
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
