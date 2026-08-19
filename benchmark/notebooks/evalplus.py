# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo",
#     "satyrn-benchmark @ git+https://github.com/pyrsuit/satyrn-models.git@${SATYRN_REF}#subdirectory=benchmark",
# ]
# ///
#
# Benchmarks a Hugging Face model with evalplus (HumanEval+ and MBPP+).
# See docs/benchmark_evalplus.md.

import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium", auto_download=["html"])


@app.cell
def _():
    import importlib
    import re
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    from string import Template

    # Edit this to benchmark from another branch or tag.
    SATYRN_REF = "main"

    # molab ignores the PEP 723 header above, so the package has to be installed
    # here; the spec is read back out of the header to keep it in one place.
    header = re.search(r'"(satyrn-benchmark @ [^"]+)"', Path(__file__).read_text())
    if header is None:
        raise RuntimeError("satyrn-benchmark is missing from the PEP 723 header at the top of this notebook.")
    spec = Template(header[1]).substitute(SATYRN_REF=SATYRN_REF)
    # The version stays 0.1.0 while the ref moves, so force the reinstall.
    if shutil.which("uv"):
        commands = [
            ["uv", "pip", "install", "--python", sys.executable, "--reinstall-package", "satyrn-benchmark", spec]
        ]
    else:
        commands = [
            [sys.executable, "-m", "pip", "install", spec],
            [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", spec],
        ]
    for command in commands:
        print(" ".join(command))
        subprocess.run(command, check=True)

    # Make the fresh install visible to the running interpreter.
    importlib.invalidate_caches()
    installed = True
    return (installed,)


@app.cell
def _(installed):
    from satyrn.benchmark.config import MODELS, BenchmarkConfig
    from satyrn.benchmark.run import run_benchmark

    run_benchmark(BenchmarkConfig(model=MODELS["mellum2-12b-a2.5"]))
    return


if __name__ == "__main__":
    app.run()
