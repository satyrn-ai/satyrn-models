"""Smoke tests: the satyrn-dataset CLI imports and responds to --help."""

from collections.abc import Iterator

import pytest
from click.testing import CliRunner

from satyrn.dataset.cli import cli

EXPECTED_COMMANDS = ["collect-doc-changes", "cpt", "download-inputs", "rl", "sft"]


@pytest.fixture
def runner() -> Iterator[CliRunner]:
    """Run from a temporary directory: the sft and rl commands create results/ on startup."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


def test_group_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Satyrn dataset generation tools." in result.output


def test_every_command_is_registered() -> None:
    assert sorted(cli.commands) == EXPECTED_COMMANDS


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_help(runner: CliRunner, command_name: str) -> None:
    result = runner.invoke(cli, [command_name, "--help"])
    assert result.exit_code == 0
    assert command_name in result.output


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_requires_arguments(runner: CliRunner, command_name: str) -> None:
    """Invoking without arguments fails on usage, before any real work starts."""
    result = runner.invoke(cli, [command_name])
    assert result.exit_code == 2
    assert "Usage:" in result.output
