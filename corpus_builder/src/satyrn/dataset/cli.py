import logging

import click
from rich.logging import RichHandler

from satyrn.dataset import cpt, rl, sft
from satyrn.dataset.inputs import collect_doc_changes, download_inputs

handler = RichHandler(show_time=False, show_path=False)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])


@click.group("satyrn-dataset")
def cli() -> None:
    """Satyrn dataset generation tools."""


cli.add_command(cpt.main)
cli.add_command(sft.main)
cli.add_command(rl.main)
cli.add_command(download_inputs.main)
cli.add_command(collect_doc_changes.main)
