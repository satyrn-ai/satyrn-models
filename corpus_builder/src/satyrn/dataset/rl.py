"""Reinforcement Learning (RL) dataset generation."""

from pathlib import Path

import click


@click.command("rl")
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
    """Generate a Reinforcement Learning (RL) dataset."""
    click.echo(f"rl: would read from {input_dir}, write to {output_dir}")
    raise click.ClickException("satyrn-dataset rl is not yet implemented")
