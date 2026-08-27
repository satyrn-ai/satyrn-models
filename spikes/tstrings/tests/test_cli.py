"""CLI smoke tests."""

import click
import pytest
from click.testing import CliRunner

from satyrn.tstrings.cli import _check_diversity, cli


def test_help_lists_all_subcommands() -> None:
    """Help lists all six pipeline subcommands and exits 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    output = result.output
    for command in ("mine", "build", "gate", "render", "train", "eval"):
        assert command in output


def test_help_lists_deliver_subcommand() -> None:
    """Help lists the deliver subcommand."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "deliver" in result.output


def test_check_diversity_raises_below_floor() -> None:
    """A measured ratio below the floor raises a ClickException."""
    with pytest.raises(click.ClickException, match="below floor"):
        _check_diversity(0.10, 0.25)


def test_check_diversity_passes_at_or_above_floor() -> None:
    """A measured ratio at or above the floor is a no-op."""
    assert _check_diversity(0.25, 0.25) is None
    assert _check_diversity(0.736, 0.25) is None
