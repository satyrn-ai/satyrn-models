"""Run Python code in a gVisor-sandboxed Docker container."""

import logging
import shutil
import subprocess
import urllib.request
from functools import lru_cache
from uuid import uuid4

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARACTERS = 12000
TIMEOUT_SECONDS = 20
SANDBOX_LABEL_NAME = "satyrn-sandbox"
SANDBOX_RUN_IDENTIFIER = uuid4().hex


def truncate(text: str, limit: int = MAX_OUTPUT_CHARACTERS) -> str:
    """Return text cut to limit characters, noting how many were cut."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated, {len(text) - limit} more characters]"


@lru_cache
def docker_available() -> bool:
    """Return True if Docker is available and running."""
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@lru_cache
def gvisor_available() -> bool:
    """Return True if runsc is registered with Docker."""
    result = subprocess.run(
        ["docker", "info", "--format", "{{range .Runtimes}}{{.Path}}\n{{end}}"], capture_output=True, text=True
    )
    return result.returncode == 0 and "runsc" in result.stdout


@lru_cache
def get_python_docker_image(python_version: str) -> str:
    """Return the Docker image tag for python_version."""
    tag = f"{python_version}-slim"
    if tag_exists_on_docker_hub(tag):
        return f"python:{tag}"

    rc_tag = f"{python_version}-rc-slim"
    if tag_exists_on_docker_hub(rc_tag):
        return f"python:{rc_tag}"

    raise ValueError(f"No Docker image found for Python {python_version} (tried {tag} and {rc_tag})")


@lru_cache
def tag_exists_on_docker_hub(tag: str) -> bool:
    """Return True if library/python:tag exists on Docker Hub."""
    try:
        urllib.request.urlopen(f"https://hub.docker.com/v2/repositories/library/python/tags/{tag}")
        return True
    except urllib.request.HTTPError as error:
        if error.code == 404:
            return False
        raise


def pull_image(image: str) -> None:
    """Pull image if it isn't already local."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        subprocess.run(["docker", "pull", image])


def remove_leftover_containers() -> int:
    """Remove containers this process left running. Return how many were removed."""
    listing = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={SANDBOX_LABEL_NAME}={SANDBOX_RUN_IDENTIFIER}"],
        capture_output=True,
        text=True,
    )
    container_ids = listing.stdout.split()
    if container_ids:
        subprocess.run(["docker", "rm", "--force", *container_ids], capture_output=True)
    return len(container_ids)


class Sandbox:
    """A Docker container that runs Python code under a fixed Python version."""

    def __init__(self, python_version: str) -> None:
        if not docker_available():
            raise RuntimeError("Docker is not available.")

        self.python_version = python_version
        self.image = get_python_docker_image(python_version)
        self.use_gvisor = gvisor_available()
        if not self.use_gvisor:
            logger.warning("gVisor (runsc) is not registered with Docker; running without sandbox isolation.")
        pull_image(self.image)

    def run(self, code: str) -> str:
        """Run code in the container. Return its combined output."""
        command = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--memory=512m",
            "--cpus=0.75",
            "--pids-limit=100",
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            "--name",
            f"{SANDBOX_LABEL_NAME}-{uuid4().hex}",
            "--label",
            f"{SANDBOX_LABEL_NAME}={SANDBOX_RUN_IDENTIFIER}",
            # set the user to nobody
            "-u",
            "65534:65534",
            # lock the file system
            "--read-only",
            # give code a writable working dir in /tmp
            "-w",
            "/tmp",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev",
        ]
        if self.use_gvisor:
            command.append("--runtime=runsc")
        command += [self.image, "python3", "-u", "-c", code]

        try:
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            return f"[did not terminate within {TIMEOUT_SECONDS} seconds]"
        return truncate(result.stdout)
