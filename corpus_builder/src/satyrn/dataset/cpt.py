"""Continued Pretraining (CPT) dataset generation."""

from pathlib import Path

import click


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
    click.echo(f"cpt: would read from {input_dir}, write to {output_dir}")
    raise click.ClickException("satyrn-dataset cpt is not yet implemented")
