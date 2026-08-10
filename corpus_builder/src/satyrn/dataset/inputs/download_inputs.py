"""Download the PEP and whatsnew source documents used by dataset generation."""

import logging
import urllib.request
from pathlib import Path

import click

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SOURCES = {
    "3.14": {
        "docs": {
            "PEP649": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0649.rst",
            "PEP749": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0749.rst",
            "PEP734": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0734.rst",
            "PEP750": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0750.rst",
            "PEP758": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0758.rst",
            "PEP765": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0765.rst",
            "PEP768": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0768.rst",
            "whatsnew": "https://raw.githubusercontent.com/python/cpython/main/Doc/whatsnew/3.14.rst",
        }
    },
    "3.15": {
        "docs": {
            "PEP810": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0810.rst",
            "PEP814": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0814.rst",
            "PEP661": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0661.rst",
            "PEP799": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0799.rst",
            "PEP831": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0831.rst",
            "PEP798": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0798.rst",
            "PEP686": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0686.rst",
            "PEP829": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0829.rst",
            "PEP728": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0728.rst",
            "PEP747": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0747.rst",
            "PEP800": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0800.rst",
            "PEP782": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0782.rst",
            "PEP803": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0803.rst",
            "PEP820": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0820.rst",
            "PEP793": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0793.rst",
            "PEP788": "https://raw.githubusercontent.com/python/peps/main/peps/pep-0788.rst",
            "whatsnew": "https://raw.githubusercontent.com/python/cpython/main/Doc/whatsnew/3.15.rst",
        }
    },
}


@click.command("download-inputs")
@click.argument("target_version", type=click.Choice(sorted(SOURCES)))
def main(target_version: str) -> None:
    """Download PEP and whatsnew source documents."""
    for category, urls in SOURCES[target_version].items():
        out_dir = Path(__file__).parents[5] / "datasets" / f"python{target_version}" / "input" / category
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, url in urls.items():
            dest = out_dir / f"{name}.rst"
            logger.info("Python %s: Downloading %s", target_version, name)
            urllib.request.urlretrieve(url, dest)


if __name__ == "__main__":
    main()
