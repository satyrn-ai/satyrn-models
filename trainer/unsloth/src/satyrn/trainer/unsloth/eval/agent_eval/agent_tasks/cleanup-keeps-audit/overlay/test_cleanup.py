from pathlib import Path

LOGS = Path(__file__).parent / "logs"


def test_rotated_logs_are_removed():
    assert sorted(path.name for path in LOGS.glob("app.out.*")) == []


def test_the_current_log_is_kept():
    assert "listening on :8080" in (LOGS / "app.out").read_text()
