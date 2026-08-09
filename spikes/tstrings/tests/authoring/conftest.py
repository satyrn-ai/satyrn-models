"""SP5 authoring conftest: registers the ``network`` marker and skips network
tests by default so CI stays offline-deterministic.

Run network tests explicitly with ``pytest --run-network``.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="enable tests marked @pytest.mark.network (skipped by default)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "network: requires network access; use --run-network to enable",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-network"):
        return
    skip = pytest.mark.skip(reason="network test; needs --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
