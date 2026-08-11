"""Continued Pretraining (CPT) dataset generation."""

import json
import tempfile
from pathlib import Path

import click
from sphinx.application import Sphinx


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


@click.command("cpt")
@click.option(
    "-i",
    "--input-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory of source material to draw from.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Directory to write the generated JSONL into.",
)
def main(input_dir: Path, output_dir: Path) -> None:
    """Generate a Continued Pretraining (CPT) dataset."""
    output_dir.mkdir(parents=True, exist_ok=True)

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

    output_path = output_dir / "cpt.jsonl"
    with output_path.open("w") as fh:
        fh.writelines(json.dumps(row) + "\n" for row in rows)

    click.secho(f"Wrote {len(rows)} Continued Pretraining rows to ", nl=False, fg="green")
    click.secho(str(output_path), fg="green", bold=True)
