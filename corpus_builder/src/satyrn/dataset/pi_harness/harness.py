"""Headless Pi process driven over its RPC protocol."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from satyrn.dataset.utils.sandbox import (
    SANDBOX_LABEL_NAME,
    SANDBOX_RUN_IDENTIFIER,
    build_image,
    docker_available,
    gvisor_available,
)

PI_IMAGE = "satyrn-pi-harness"
PI_DOCKERFILE = Path(__file__).with_name("Dockerfile")
PI_EXTENSION = Path(__file__).with_name("render-payload.ts")


def build_pi_image() -> str:
    """Build and return the Pi image if needed."""
    return build_image(PI_IMAGE, PI_DOCKERFILE, "3.15")


def check_prerequisites() -> None:
    """Raise RuntimeError unless Docker is available and the model provider key is set."""
    if not docker_available():
        raise RuntimeError("Docker is not available.")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is not set in the environment.")


@dataclass
class File:
    """A text file."""

    name: str
    content: str


class PiHarness:
    """Headless Pi in RPC mode, running in a Docker container."""

    RENDER_TRIGGER_PROMPT = "[RENDER SESSION AND ABORT]"
    COMMAND_TIMEOUT_SECONDS = 300

    def __init__(self, model: str, workspace: list[File]) -> None:
        check_prerequisites()
        self.model = model
        self.root_dir = Path(tempfile.mkdtemp(prefix="satyrn-pi-workspace-"))
        self.workspace_dir = self.root_dir / "workspace"
        self.payload_dir = self.root_dir / "payload"
        self.payload_path = self.payload_dir / "payload.json"
        self.workspace_dir.mkdir()
        self.payload_dir.mkdir()
        for file in workspace:
            (self.workspace_dir / file.name).write_text(file.content)
        self.container_name = f"{PI_IMAGE}-{uuid4().hex}"
        self.start()

    def start(self) -> None:
        """Start Pi in a container."""
        docker_command = ["docker", "run", "--rm", "--init", "--interactive", "--name", self.container_name]
        docker_command += ["--label", f"{SANDBOX_LABEL_NAME}={SANDBOX_RUN_IDENTIFIER}"]
        docker_command += ["--user", f"{os.getuid()}:{os.getgid()}", "--tmpfs", "/home/agent"]
        docker_command += ["--env", "HOME=/home/agent", "--env", "USER=agent", "--env", "DEEPSEEK_API_KEY"]
        docker_command += ["--env", f"PI_RENDER_TRIGGER_PROMPT={self.RENDER_TRIGGER_PROMPT}"]
        docker_command += ["--env", f"PI_PAYLOAD_FILE=/payload/{self.payload_path.name}"]
        docker_command += ["--workdir", "/workspace", "--volume", f"{self.workspace_dir}:/workspace"]
        docker_command += ["--volume", f"{self.payload_dir}:/payload"]
        docker_command += ["--volume", f"{PI_EXTENSION}:/extensions/render-payload.ts:ro"]
        docker_command += ["--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=100"]
        docker_command += ["--memory=512m", "--cpus=0.75"]
        if gvisor_available():
            docker_command.append("--runtime=runsc")
        docker_command += [PI_IMAGE, "pi", "--mode", "rpc", "--no-session", "--no-extensions", "--no-skills"]
        docker_command += ["--no-context-files", "--model", self.model, "--extension", "/extensions/render-payload.ts"]
        self.process = subprocess.Popen(docker_command, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def stop(self) -> None:
        """Kill the container and delete its temporary directory."""
        subprocess.run(["docker", "kill", self.container_name], capture_output=True)
        shutil.rmtree(self.root_dir, ignore_errors=True)

    def send_command(self, command: dict, reply_type: str) -> dict:
        """Send an RPC command and return the first stdout record of reply_type."""
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        watchdog = threading.Timer(self.COMMAND_TIMEOUT_SECONDS, self.stop)
        watchdog.start()
        try:
            for stdout_line in self.process.stdout:
                if stdout_line.startswith("{") and (record := json.loads(stdout_line))["type"] == reply_type:
                    return record
        finally:
            watchdog.cancel()
        raise RuntimeError(f"Pi exited or timed out before sending {reply_type}")

    def agent_run(self, message: str) -> None:
        """Send a user message, wait until the agent finishes.

        Raise RuntimeError unless the session then ends with an assistant message that stopped normally:

            {"role": "assistant", "stopReason": "stop", ...}       finished
            {"role": "assistant", "stopReason": "aborted", ...}    aborted
            {"role": "assistant", "stopReason": "error", ...}      failed
        """
        self.send_command({"type": "prompt", "message": message}, "agent_settled")
        last_message = self.send_command({"type": "get_messages"}, "response")["data"]["messages"][-1]
        if last_message.get("stopReason") != "stop":
            raise RuntimeError(f"Pi run ended with stopReason {last_message.get('stopReason')!r}")

    def render_session(self) -> str:
        """Return the provider payload of the whole session, as Pi would send it for the next prompt."""
        self.send_command({"type": "prompt", "message": self.RENDER_TRIGGER_PROMPT}, "agent_settled")
        return self.payload_path.read_text()
