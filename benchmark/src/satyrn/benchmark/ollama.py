import json
import logging
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

TAGS_URL = "http://localhost:11434/api/tags"
STARTUP_TIMEOUT_SECONDS = 60


def is_server_up() -> bool:
    try:
        urllib.request.urlopen(TAGS_URL, timeout=2)
    except OSError:
        return False
    return True


def ensure_server() -> None:
    """Make a local Ollama server available, starting it if it isn't up yet.

    Ollama itself is a prerequisite: install it on the machine before running
    the benchmark. Starting it here covers cloud containers that have no
    systemd to run it as a service; where it is already up, this is a no-op.
    """
    if shutil.which("ollama") is None:
        raise RuntimeError("Ollama is not installed. Install it (https://ollama.com) and re-run.")

    if is_server_up():
        logger.info("Ollama server is already up")
        return

    logger.info("Starting `ollama serve` in the background")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(STARTUP_TIMEOUT_SECONDS):
        if is_server_up():
            logger.info("Ollama server is up")
            return
        time.sleep(1)
    raise RuntimeError(f"Ollama server did not respond on {TAGS_URL} within {STARTUP_TIMEOUT_SECONDS}s.")


def is_model_registered(name: str) -> bool:
    """Whether Ollama already has a model registered under `name`."""
    with urllib.request.urlopen(TAGS_URL, timeout=5) as response:
        tags = json.load(response)
    return any(entry.get("name") == name for entry in tags.get("models", []))


def create_model(name: str, gguf_path: Path) -> None:
    """Register a GGUF file as a local Ollama model."""
    modelfile_path = gguf_path.with_suffix(".Modelfile")
    modelfile_path.write_text(f"FROM {gguf_path.resolve()}\n")
    logger.info("Running `ollama create %s` from %s", name, modelfile_path)
    subprocess.run(["ollama", "create", name, "-f", str(modelfile_path)], check=True)
