import inspect

import pytest
import reports
from http_client import fetch
from jobs import sync_orders, sync_users


def test_fetch_takes_timeout_s_with_a_default():
    parameter = inspect.signature(fetch).parameters["timeout_s"]
    assert parameter.default == 15
    assert fetch("https://x")["timeout_s"] == 15


def test_the_old_name_is_gone():
    with pytest.raises(TypeError):
        fetch("https://x", timeout=1)


def test_sync_jobs_still_run():
    assert [r["timeout_s"] for r in sync_users.run()] == [10]
    assert [r["timeout_s"] for r in sync_orders.run()] == [30, 30, 30]


def test_reports_still_run():
    assert reports.run()["timeout_s"] == 60
