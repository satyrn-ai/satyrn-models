#!/usr/bin/env python3
"""Run a command on a RunPod GPU pod."""

import getpass
import json
import shlex
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import click


class GpuPod(NamedTuple):
    name: str
    gpu_id: str
    vram_gb: int
    price_per_hour: float | None
    available: bool


def runpodctl(*arguments: str) -> str:
    return subprocess.run(
        ["runpodctl", *arguments],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout


def all_gpus() -> list[GpuPod]:
    """Return every GPU type RunPod lists."""
    listing = runpodctl("gpu", "list")
    return [
        GpuPod(
            gpu["displayName"],
            gpu["gpuId"],
            gpu["memoryInGb"],
            gpu["securePricePerHr"],
            gpu["available"],
        )
        for gpu in json.loads(listing)
    ]


def echo_gpus(gpus: list[GpuPod]) -> None:
    """Print list of GPUs, ordered by VRAM then price."""
    for gpu in sorted(gpus, key=lambda gpu: (gpu.vram_gb, gpu.price_per_hour or 0)):
        price = f"${gpu.price_per_hour:.3f}/hr" if gpu.price_per_hour else "no price"
        stock = "" if gpu.available else "  unavailable"
        click.echo(f"{gpu.vram_gb:>4} GB  {price:>12}  {gpu.name}{stock}")


def create_pod(gpu_id: str) -> str:
    """Create a pod, wait for ssh to answer, and return its id."""
    pod = runpodctl(
        "pod",
        "create",
        "--gpu-id",
        gpu_id,
        "--image",
        "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404",
        "--container-disk-in-gb",
        "100",
        "--ports",
        "22/tcp",
        "--min-cuda-version",
        "12.8",
        "--name",
        f"satyrn-models-{getpass.getuser()}",
        "--wait",
    )
    return json.loads(pod)["id"]


SSH_OPTIONS = [
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]


@lru_cache
def get_pod_ssh_info(pod_id: str) -> dict:
    return json.loads(runpodctl("ssh", "info", pod_id))


def ssh_into_pod(pod_id: str, script: str) -> None:
    """Run a bash script on the pod, streaming its output."""
    pod = get_pod_ssh_info(pod_id)
    subprocess.run(
        [
            "ssh",
            "-i",
            pod["ssh_key"]["path"],
            "-p",
            str(pod["port"]),
            *SSH_OPTIONS,
            f"root@{pod['ip']}",
            "bash",
            "-s",
        ],
        input=script,
        text=True,
        check=True,
    )


def attach_to_pod(pod_id: str, command: str) -> None:
    """Run a command on the pod over a tty."""
    pod = get_pod_ssh_info(pod_id)
    subprocess.run(
        [
            "ssh",
            "-t",
            "-i",
            pod["ssh_key"]["path"],
            "-p",
            str(pod["port"]),
            *SSH_OPTIONS,
            f"root@{pod['ip']}",
            command,
        ],
        check=True,
    )


def copy_to_pod(pod_id: str, local_path: Path, remote_path: str) -> None:
    pod = get_pod_ssh_info(pod_id)
    subprocess.run(
        [
            "scp",
            "-i",
            pod["ssh_key"]["path"],
            "-P",
            str(pod["port"]),
            *SSH_OPTIONS,
            str(local_path),
            f"root@{pod['ip']}:{remote_path}",
        ],
        check=True,
    )


def setup_pod(pod_id: str, branch: str, transformers: str) -> None:
    ssh_into_pod(
        pod_id,
        f"""
        set -euo pipefail

        apt-get update
        apt-get install -y git-lfs tmux python3.13
        git lfs install
        mkdir -p /root/.runpod

        export XDG_CACHE_HOME=/root/.cache
        export HF_HOME=/root/.cache/huggingface
        export UV_CACHE_DIR=/root/.cache/uv
        export PIP_CACHE_DIR=/root/.cache/pip
        export VIRTUALENV_OVERRIDE_APP_DATA=/root/.cache/virtualenv

        if [ -d satyrn-models ]; then
            mv satyrn-models "satyrn-models-$(cat /proc/sys/kernel/random/uuid)"
        fi
        git clone --branch {shlex.quote(branch)} https://github.com/satyrn-ai/satyrn-models.git
        cd satyrn-models
        uv venv
        source .venv/bin/activate

        uv pip install --prerelease=allow --torch-backend=auto -e trainer/unsloth/
        uv pip install --torch-backend=auto "trl==1.7.0" "transformers=={transformers}" "torch==2.11.0" "torchvision==0.26.0"
    """,
    )


def run_in_tmux(pod_id: str, command: tuple[str, ...], remove_pod: bool) -> None:
    """Run the command in a detached tmux session, streaming its log until it exits."""
    # Reaper command will destroy the pod after 2 minutes if connection is lost
    reaper = f"; tmux new-session -d -s reaper 'sleep 120; runpodctl remove pod {pod_id}'"
    session = f"cd /root/satyrn-models && . .venv/bin/activate && {shlex.join(command)}{reaper if remove_pod else ''}"
    ssh_into_pod(pod_id, f"tmux set-option -g history-limit 10000; tmux new-session -d -s satyrn {shlex.quote(session)}")
    attach_to_pod(pod_id, "tmux attach -t satyrn")


def echo_run_log(pod_id: str) -> None:
    """Print run.log from the newest results directory on the pod."""
    ssh_into_pod(
        pod_id,
        "ls -dt /root/satyrn-models/results/*/run.log 2>/dev/null | head -1 | xargs -r cat",
    )


def select_gpu(gpu_name: str | None, minimum_vram_gb: int | None) -> GpuPod:
    """Return the cheapest available GPU matching the request."""
    if bool(gpu_name) == bool(minimum_vram_gb):
        raise click.UsageError("Pass exactly one of --gpu or --vram.")

    gpus = all_gpus()
    if gpu_name:
        wanted = gpu_name.lower()
        matches = [gpu for gpu in gpus if wanted in gpu.name.lower() or wanted in gpu.gpu_id.lower()]
    else:
        matches = [gpu for gpu in gpus if gpu.vram_gb >= minimum_vram_gb]

    if not matches:
        echo_gpus(gpus)
        raise click.ClickException("Nothing matched. Every GPU is listed above.")

    offered = [gpu for gpu in matches if gpu.available and gpu.price_per_hour]
    if not offered:
        echo_gpus(matches)
        raise click.ClickException("Every matching GPU is unavailable.")

    selected = min(offered, key=lambda gpu: gpu.price_per_hour)
    click.echo(f"GPU:     {selected.name} ({selected.vram_gb} GB, ${selected.price_per_hour:.3f}/hr)")
    return selected


@click.command(context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False})
@click.option("--gpu", "gpu_name", help="Part of the GPU name, e.g. 'RTX PRO 6000'.")
@click.option("--vram", "minimum_vram_gb", type=int, help="Cheapest GPU with at least this many GB.")
@click.option("--branch", default="main", show_default=True, help="`satyrn-models` branch to clone.")
@click.option("--transformers", default="5.5.0", show_default=True, help="`transformers` version to install.")
@click.option("--keep", is_flag=True, default=False, show_default=True, help="Leave the pod running when finished.")
@click.option("--pod-id", help="Use this existing pod instead of creating one.")
@click.argument("command", nargs=-1, type=click.UNPROCESSED, required=True)
def run_on_pod(gpu_name, minimum_vram_gb, branch, transformers, keep, pod_id, command):
    """Run COMMAND on a RunPod GPU pod."""
    click.echo(f"Command: {shlex.join(command)}")
    if not pod_id:
        gpu = select_gpu(gpu_name, minimum_vram_gb)
        click.echo("Creating pod...")
        pod_id = create_pod(gpu.gpu_id)

    try:
        click.echo(get_pod_ssh_info(pod_id)["ssh_command"])
        ssh_into_pod(pod_id, "nvidia-smi")
        click.echo("Setting up pod...")
        setup_pod(pod_id, branch, transformers)
        copy_to_pod(pod_id, Path(__file__).parent.parent / ".env", "/root/satyrn-models/.env")
        copy_to_pod(pod_id, Path.home() / ".runpod/config.toml", "/root/.runpod/config.toml")
        run_in_tmux(pod_id, command, remove_pod=not keep)
        echo_run_log(pod_id)
    except KeyboardInterrupt:
        click.echo("Interrupted.")
    except Exception as e:
        raise click.ClickException(f"{e}\nPod left running, delete with: runpodctl pod delete {pod_id}") from e

    if keep:
        click.echo(f"Pod kept, delete with: runpodctl pod delete {pod_id}")
    else:
        runpodctl("pod", "delete", pod_id)
        click.echo(f"Destroyed {pod_id}.")


if __name__ == "__main__":
    run_on_pod()
