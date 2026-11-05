"""Flask application that renders a generated JSONL dataset in the browser.

The backend is intentionally thin: it loads the JSONL file once and exposes the
raw rows over a small JSON API.  All presentation logic (markdown rendering,
Python syntax highlighting, layout) lives in the TypeScript frontend so that the
dataset schema can evolve without touching the server.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from flask import Flask, jsonify, send_from_directory

logger = logging.getLogger(__name__)

STATIC_DIRECTORY = Path(__file__).parent / "static"


@dataclass(frozen=True)
class Dataset:
    """A dataset file loaded from disk alongside its per-row parse errors."""

    path: Path
    items: list[dict[str, Any]]
    errors: list[dict[str, Any]]

    @property
    def source_name(self) -> str:
        """Return a human readable name for the dataset file."""
        return self.path.name


def load_dataset(path: Path) -> Dataset:
    """Load a JSONL dataset, skipping blank lines and recording malformed rows.

    A single malformed line should not prevent the rest of the dataset from being
    inspected, so parse failures are collected rather than raised.
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset file does not exist: {path}")

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError as error:
                errors.append({"line": line_number, "message": str(error)})
                continue
            if not isinstance(item, dict):
                errors.append({"line": line_number, "message": "Row is not a JSON object"})
                continue
            item.setdefault("_viewer", {})["line"] = line_number
            item["_viewer"]["index"] = len(items)
            items.append(item)

    return Dataset(path=path.resolve(), items=items, errors=errors)


def create_app(dataset: Dataset) -> Flask:
    """Create the Flask application serving a loaded dataset and the built UI."""
    app = Flask(__name__, static_folder=str(STATIC_DIRECTORY), static_url_path="")

    @app.get("/api/dataset")
    def get_dataset() -> Any:
        """Return the dataset metadata and every row."""
        return jsonify(
            {
                "source": dataset.source_name,
                "path": str(dataset.path),
                "count": len(dataset.items),
                "errors": dataset.errors,
                "items": dataset.items,
            }
        )

    @app.get("/api/health")
    def get_health() -> Any:
        """Report whether the frontend bundle has been built."""
        return jsonify({"status": "ok", "frontend_built": (STATIC_DIRECTORY / "index.html").exists()})

    @app.get("/")
    def index() -> Any:
        """Serve the built single page application."""
        index_path = STATIC_DIRECTORY / "index.html"
        if not index_path.exists():
            return (
                "<h1>Frontend not built</h1>"
                "<p>Run <code>npm install &amp;&amp; npm run build</code> inside the "
                "<code>frontend</code> directory, or use <code>npm run dev</code> for "
                "hot reloading against this server.</p>",
                503,
            )
        return send_from_directory(STATIC_DIRECTORY, "index.html")

    return app


@click.command("viewer")
@click.argument("dataset_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--host", default="127.0.0.1", show_default=True, help="Interface to bind to.")
@click.option("--port", default=5000, show_default=True, type=click.IntRange(1, 65535), help="Port to listen on.")
@click.option("--debug", is_flag=True, default=False, help="Enable the Flask debug reloader.")
def main(dataset_path: Path, host: str, port: int, debug: bool) -> None:
    """Serve DATASET_PATH (a JSONL file) through the web viewer."""
    dataset = load_dataset(dataset_path)
    logger.info("Loaded %d dataset items from %s", len(dataset.items), dataset.path)
    if dataset.errors:
        logger.warning("Skipped %d malformed line(s)", len(dataset.errors))

    app = create_app(dataset)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
