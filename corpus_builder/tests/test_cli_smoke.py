"""Smoke tests: the satyrn-dataset CLI imports and responds to --help."""

from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from satyrn.dataset.cli import cli

EXPECTED_COMMANDS = ["collect-doc-changes", "cpt", "download-inputs", "eval", "rl", "sft"]


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """Run the CLI without creating a results/ directory."""
    # start_run_log writes results/ into the current directory; skip it so the tests create no files.
    monkeypatch.setattr("satyrn.dataset.cli.start_run_log", Mock())
    return CliRunner()


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
