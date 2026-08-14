"""Reinforcement Learning (RL) dataset generation."""

from pathlib import Path

import click


@click.command("rl")
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory of source material to draw from, or a single doc file.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="JSONL file to write the generated dataset to.",
)
def main(input_path: Path, output_path: Path) -> None:
    """Generate a Reinforcement Learning (RL) dataset."""
    if output_path.suffix != ".jsonl":
        raise click.BadParameter("Output file must end with .jsonl")
    click.echo(f"rl: would read from {input_path}, write to {output_path}")
    raise click.ClickException("satyrn-dataset rl is not yet implemented")
