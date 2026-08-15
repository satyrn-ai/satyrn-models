import logging
from datetime import datetime
from pathlib import Path

import click
from rich.logging import RichHandler

from satyrn.dataset import cpt, rl, sft
from satyrn.dataset.inputs import collect_doc_changes, download_inputs

handler = RichHandler(show_time=False, show_path=False)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])


def start_run_log(command_name: str) -> None:
    """Write the run's log messages to results/<timestamp>-corpus-builder-<command>/run.log."""
    run_directory = Path("results", f"{datetime.now():%Y%m%d-%H%M}-corpus-builder-{command_name}")
    run_directory.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(run_directory / "run.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(file_handler)


@click.group("satyrn-dataset")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Satyrn dataset generation tools."""
    if ctx.invoked_subcommand in ("sft", "rl"):
        start_run_log(ctx.invoked_subcommand)


cli.add_command(cpt.main)
cli.add_command(sft.main)
cli.add_command(rl.main)
cli.add_command(download_inputs.main)
cli.add_command(collect_doc_changes.main)
