import logging
import shutil
import subprocess
import sys
from pathlib import Path

from huggingface_hub import get_safetensors_metadata

logger = logging.getLogger(__name__)

LLAMA_CPP_URL = "https://github.com/ggml-org/llama.cpp.git"
SAFETENSORS_DTYPE_TO_OUTTYPE = {"F64": "f32", "F32": "f32", "F16": "f16", "BF16": "bf16"}
FALLBACK_OUTTYPE = "f16"


def format_repo_id(hf_ref: str) -> str:
    """Strip the `hf.co/` or URL prefix off a Hugging Face model reference."""
    return hf_ref.removeprefix("hf.co/").removeprefix("https://huggingface.co/").strip("/")


def extract_model_name(repo: str) -> str:
    """A filename- and tag-safe name for a Hugging Face repo."""
    return repo.split("/")[-1].lower().replace(".", "-").replace("_", "-")


def detect_outtype(repo: str) -> str:
    """Match the checkpoint's own native precision, so nothing gets quantized.

    Only reads the safetensors header, so it is fast regardless of model size.
    """
    try:
        metadata = get_safetensors_metadata(repo)
    except Exception as error:
        logger.warning(
            "Couldn't auto-detect precision for '%s' (%s); falling back to %s. "
            "Set model.gguf_outtype explicitly to override.",
            repo,
            error,
            FALLBACK_OUTTYPE,
        )
        return FALLBACK_OUTTYPE

    parameters = metadata.parameter_count
    dominant_dtype = max(parameters, key=lambda dtype: parameters[dtype])
    outtype = SAFETENSORS_DTYPE_TO_OUTTYPE.get(dominant_dtype)
    if outtype is None:
        logger.warning(
            "'%s' weights are mostly %s, which has no direct unquantized GGUF equivalent -- "
            "set model.gguf_outtype explicitly. Falling back to %s for now.",
            repo,
            dominant_dtype,
            FALLBACK_OUTTYPE,
        )
        return FALLBACK_OUTTYPE

    share = 100 * parameters[dominant_dtype] / sum(parameters.values())
    logger.info(
        "Detected '%s' native precision: %s (%.0f%% of parameters) -> --outtype %s (no quantization)",
        repo,
        dominant_dtype,
        share,
        outtype,
    )
    return outtype


def get_isolated_conversion_python(work_dir: Path, llama_cpp_dir: Path) -> Path:
    """Build an isolated virtualenv holding llama.cpp's conversion toolchain.

    llama.cpp's converter pins transformers/numpy/torch versions that collide
    with the ones evalplus needs, so the two must not share an environment.
    """
    venv_dir = work_dir / "llamacpp_venv"
    python = venv_dir / "bin" / "python"
    uv = shutil.which("uv")

    if not venv_dir.is_dir():
        logger.info("Creating an isolated virtualenv for the conversion toolchain at %s", venv_dir)
        if uv:
            subprocess.run([uv, "venv", "--quiet", str(venv_dir)], check=True)
        else:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    requirements = llama_cpp_dir / "requirements" / "requirements-convert_hf_to_gguf.txt"
    if uv:
        install = [uv, "pip", "install", "--python", str(python), "--quiet"]
    else:
        install = [str(python), "-m", "pip", "install", "--quiet"]
    subprocess.run([*install, "-r", str(requirements), "huggingface_hub"], check=True)
    return python


def build_gguf(repo: str, outtype: str, work_dir: Path) -> Path:
    """Download `repo` from Hugging Face and convert it to a single GGUF file.

    Needs roughly 2-3x the model's size in free disk space.
    """
    slug = extract_model_name(repo)
    gguf_path = work_dir / "gguf_models" / f"{slug}-{outtype}.gguf"
    if gguf_path.is_file():
        logger.info("Reusing the GGUF file already at %s", gguf_path)
        return gguf_path

    llama_cpp_dir = work_dir / "llama.cpp"
    if not llama_cpp_dir.is_dir():
        subprocess.run(["git", "clone", "--depth", "1", LLAMA_CPP_URL, str(llama_cpp_dir)], check=True)
    python = get_isolated_conversion_python(work_dir, llama_cpp_dir)

    # Gated repos need HF_TOKEN exported.
    checkpoint_dir = work_dir / "hf_models" / slug
    logger.info("Downloading %s to %s", repo, checkpoint_dir)
    download = (
        "from huggingface_hub import snapshot_download; "
        f"snapshot_download(repo_id={repo!r}, local_dir={str(checkpoint_dir)!r})"
    )
    subprocess.run([str(python), "-c", download], check=True)

    logger.info("Converting %s to %s (--outtype %s)", repo, gguf_path, outtype)
    gguf_path.parent.mkdir(parents=True, exist_ok=True)
    convert = subprocess.run(
        [
            str(python),
            str(llama_cpp_dir / "convert_hf_to_gguf.py"),
            str(checkpoint_dir),
            "--outtype",
            outtype,
            "--outfile",
            str(gguf_path),
        ],
        check=False,
    )
    if convert.returncode != 0 or not gguf_path.is_file():
        raise RuntimeError(
            f"GGUF conversion failed for {repo}. llama.cpp only supports architectures it has "
            "explicitly implemented -- check https://github.com/ggml-org/llama.cpp for current coverage."
        )

    logger.info("Removing the raw download at %s to save disk", checkpoint_dir)
    shutil.rmtree(checkpoint_dir, ignore_errors=True)
    return gguf_path
