import logging
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_URL = "https://ollama.com/install.sh"
TAGS_URL = "http://localhost:11434/api/tags"
STARTUP_TIMEOUT_SECONDS = 60

# The Ollama install script needs zstd, which cloud containers often lack.
ZSTD_INSTALLERS = {
    "apt-get": [["apt-get", "update", "-qq"], ["apt-get", "install", "-y", "-qq", "zstd"]],
    "dnf": [["dnf", "install", "-y", "zstd"]],
    "yum": [["yum", "install", "-y", "zstd"]],
    "apk": [["apk", "add", "--no-cache", "zstd"]],
    "pacman": [["pacman", "-Sy", "--noconfirm", "zstd"]],
}


def install_zstd() -> None:
    logger.info("zstd not found -- installing it (required by the Ollama installer)")
    sudo = ["sudo"] if shutil.which("sudo") else []
    for manager, commands in ZSTD_INSTALLERS.items():
        if shutil.which(manager) is None:
            continue
        for command in commands:
            subprocess.run([*sudo, *command], check=False)
        if shutil.which("zstd"):
            return
    raise RuntimeError(
        "Could not install `zstd`, which the Ollama installer requires. Install it manually "
        "for this environment's distro (e.g. `apt-get install -y zstd`) and re-run."
    )


def install_ollama() -> None:
    if shutil.which("zstd") is None:
        install_zstd()
    logger.info("Ollama CLI not found -- installing via %s", INSTALL_URL)
    subprocess.run(f"curl -fsSL {INSTALL_URL} | sh", shell=True, check=False)
    if shutil.which("ollama") is None:
        raise RuntimeError(
            "Automatic install failed. Install Ollama manually (https://ollama.com) or check "
            "that this environment has outbound network access to ollama.com."
        )


def is_server_up() -> bool:
    try:
        urllib.request.urlopen(TAGS_URL, timeout=2)
    except OSError:
        return False
    return True


def ensure_server(install_deps: bool = True) -> None:
    """Make a local Ollama server available, installing and starting it if needed.

    This is self-contained so it works on a bare cloud sandbox (e.g. a molab
    notebook) that has no Ollama install and no systemd to run it as a service.
    On a machine where Ollama is already installed and running, it's a no-op.
    With `install_deps` off, a missing Ollama is an error rather than an install.
    """
    if shutil.which("ollama") is None:
        if not install_deps:
            raise RuntimeError("Ollama is not installed. Re-run without --no-install-deps to install it.")
        install_ollama()

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


def create_model(name: str, gguf_path: Path) -> None:
    """Register a GGUF file as a local Ollama model."""
    modelfile_path = gguf_path.with_suffix(".Modelfile")
    modelfile_path.write_text(f"FROM {gguf_path.resolve()}\n")
    logger.info("Running `ollama create %s` from %s", name, modelfile_path)
    subprocess.run(["ollama", "create", name, "-f", str(modelfile_path)], check=True)
