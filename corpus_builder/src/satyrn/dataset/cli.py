import click

from satyrn.dataset import cpt, rl, sft


@click.group("satyrn-dataset")
def cli() -> None:
    """Satyrn dataset generation tools."""


cli.add_command(cpt.main)
cli.add_command(sft.main)
cli.add_command(rl.main)
