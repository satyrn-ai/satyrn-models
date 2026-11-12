"""Tests for the Pi harness, driven through a fake process instead of Docker and Pi."""

import io
import json
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from satyrn.dataset.pi_harness import harness
from satyrn.dataset.pi_harness.harness import File, PiHarness

StartHarness = Callable[..., tuple[PiHarness, list[str]]]


class FakeProcess:
    """Record what is written to stdin and replay the given lines on stdout."""

    def __init__(self, stdout_lines: Iterable[str]) -> None:
        self.stdin = io.StringIO()
        self.stdout = iter(stdout_lines)

    def sent_commands(self) -> list[dict]:
        return [json.loads(line) for line in self.stdin.getvalue().splitlines()]


def finished_run(stop_reason: str) -> list[str]:
    """Return the stdout lines of an agent run whose last message has stop_reason."""
    messages = [{"role": "assistant", "stopReason": stop_reason}]
    return [
        '{"type": "agent_settled"}\n',
        json.dumps({"type": "response", "data": {"messages": messages}}) + "\n",
    ]


@pytest.fixture
def start_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StartHarness:
    """Return a function that starts a PiHarness on a fake process and returns it with its docker command."""
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    monkeypatch.setattr(harness, "check_prerequisites", lambda: None)
    monkeypatch.setattr(harness.tempfile, "mkdtemp", lambda prefix: str(root_dir))

    def start(
        stdout_lines: Iterable[str] = (), gvisor: bool = False, workspace: list[File] | None = None
    ) -> tuple[PiHarness, list[str]]:
        docker_commands: list[list[str]] = []

        def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
            docker_commands.append(command)
            return FakeProcess(stdout_lines)

        monkeypatch.setattr(harness, "gvisor_available", lambda: gvisor)
        monkeypatch.setattr(harness.subprocess, "Popen", fake_popen)
        return PiHarness("deepseek/deepseek-flash", workspace or []), docker_commands[0]

    return start


def test_init_writes_the_workspace_files(start_harness: StartHarness) -> None:
    pi, _ = start_harness(workspace=[File("render.py", "x = 1\n"), File("notes.txt", "hello")])

    assert (pi.workspace_dir / "render.py").read_text() == "x = 1\n"
    assert (pi.workspace_dir / "notes.txt").read_text() == "hello"


def test_stop_deletes_the_temporary_directory(start_harness: StartHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    pi, _ = start_harness(workspace=[File("render.py", "x = 1\n")])
    monkeypatch.setattr(harness.subprocess, "run", lambda *args, **kwargs: None)

    pi.stop()

    assert not pi.root_dir.exists()


@pytest.mark.parametrize("gvisor", [True, False])
def test_start_runs_pi_in_a_container(start_harness: StartHarness, gvisor: bool) -> None:
    pi, command = start_harness(gvisor=gvisor)

    volumes = [command[index + 1] for index, argument in enumerate(command) if argument == "--volume"]
    assert volumes[:2] == [f"{pi.workspace_dir}:/workspace", f"{pi.payload_dir}:/payload"]
    assert volumes[2].endswith(":/extensions/render-payload.ts:ro")
    assert ("--runtime=runsc" in command) == gvisor
    assert command[command.index(harness.PI_IMAGE) + 1] == "pi"
    assert command[command.index("--model") + 1] == "deepseek/deepseek-flash"
    assert pi.container_name in command


def test_send_command_returns_the_first_record_of_the_reply_type(start_harness: StartHarness) -> None:
    lines = [
        "not json\n",
        '{"type": "event"}\n',
        '{"type": "response", "data": 1}\n',
        '{"type": "response", "data": 2}\n',
    ]
    pi, _ = start_harness(lines)

    record = pi.send_command({"type": "get_messages"}, "response")

    assert record == {"type": "response", "data": 1}
    assert pi.process.sent_commands() == [{"type": "get_messages"}]


def test_send_command_raises_when_the_stream_ends_without_the_reply(start_harness: StartHarness) -> None:
    pi, _ = start_harness(['{"type": "event"}\n'])

    with pytest.raises(RuntimeError, match="before sending agent_settled"):
        pi.send_command({"type": "prompt", "message": "hello"}, "agent_settled")


def test_agent_run_sends_the_message_and_accepts_a_stopped_run(start_harness: StartHarness) -> None:
    pi, _ = start_harness(finished_run("stop"))

    pi.agent_run("Refactor render.py")

    assert pi.process.sent_commands() == [
        {"type": "prompt", "message": "Refactor render.py"},
        {"type": "get_messages"},
    ]


@pytest.mark.parametrize("stop_reason", ["aborted", "error"])
def test_agent_run_raises_unless_the_last_message_stopped(start_harness: StartHarness, stop_reason: str) -> None:
    pi, _ = start_harness(finished_run(stop_reason))

    with pytest.raises(RuntimeError, match=stop_reason):
        pi.agent_run("Refactor render.py")


def test_render_session_sends_the_trigger_prompt_and_returns_the_payload(start_harness: StartHarness) -> None:
    pi, _ = start_harness(['{"type": "agent_settled"}\n'])
    pi.payload_path.write_text('{"messages": []}')

    payload = pi.render_session()

    assert payload == '{"messages": []}'
    assert pi.process.sent_commands() == [{"type": "prompt", "message": PiHarness.RENDER_TRIGGER_PROMPT}]
