"""Tests for the dataset web viewer backend."""

import json
from pathlib import Path

from satyrn.dataset.viewer.app import create_app, load_dataset


def write_jsonl(path: Path, rows: list[object]) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def test_load_dataset_parses_rows_and_annotates_positions(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "dataset.jsonl",
        [{"prompt": "first"}, {"prompt": "second"}],
    )

    dataset = load_dataset(path)

    assert dataset.source_name == "dataset.jsonl"
    assert [item["prompt"] for item in dataset.items] == ["first", "second"]
    assert dataset.items[0]["_viewer"] == {"line": 1, "index": 0}
    assert dataset.items[1]["_viewer"] == {"line": 2, "index": 1}
    assert dataset.errors == []


def test_load_dataset_skips_blank_lines_and_records_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "dataset.jsonl"
    path.write_text('{"prompt": "ok"}\n\nnot json\n42\n', encoding="utf-8")

    dataset = load_dataset(path)

    assert len(dataset.items) == 1
    assert [error["line"] for error in dataset.errors] == [3, 4]


def test_load_dataset_missing_file_raises(tmp_path: Path) -> None:
    dataset_path = tmp_path / "missing.jsonl"

    try:
        load_dataset(dataset_path)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_dataset_endpoint_returns_loaded_rows(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "dataset.jsonl", [{"prompt": "hello"}])
    app = create_app(load_dataset(path))
    client = app.test_client()

    response = client.get("/api/dataset")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source"] == "dataset.jsonl"
    assert payload["count"] == 1
    assert payload["items"][0]["prompt"] == "hello"
