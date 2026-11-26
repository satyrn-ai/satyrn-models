import os

import pytest


def pytest_configure(config):
    if os.environ.get("APP_ENV") != "test":
        pytest.exit(
            "Refusing to run: set APP_ENV=test to run the tests. Without it they would use the production settings.",
            returncode=4,
        )
