"""Run Python code in a gVisor-sandboxed Docker container."""

import logging
import shutil
import subprocess
import urllib.request
from functools import lru_cache

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARACTERS = 12000


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


@lru_cache
def sandbox_available(python_version: str) -> bool:
    """Return True if Docker and gVisor are available and the Python image exists."""
    if not docker_available():
        logger.error("Docker is not available.")
        return False
    if not gvisor_available():
        logger.warning("gVisor (runsc) is not registered with Docker; running without sandbox isolation.")
    try:
        image = get_python_docker_image(python_version)
    except ValueError as error:
        logger.error("%s", error)
        return False
    pull_image(image)
    return True


def pull_image(image: str) -> None:
    """Pull image if it isn't already local."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        subprocess.run(["docker", "pull", image])


def run_in_sandbox(python_version: str, code: str) -> str:
    """Run code under python_version in a sandboxed container. Return its combined output."""
    if not sandbox_available(python_version):
        raise RuntimeError(f"Sandbox not available for Python {python_version}")

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
    if gvisor_available():
        command.append("--runtime=runsc")
    command += [get_python_docker_image(python_version), "python3", "-u", "-c", code]

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
    return truncate(result.stdout)
