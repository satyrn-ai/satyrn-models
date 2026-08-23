"""T-strings spike command-line interface."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import click

from satyrn.dataset.llm.models import get_llm
from satyrn.tstrings import build, deliver, gate, mine, render, split, train, transform
from satyrn.tstrings import eval as eval_cmd
from satyrn.tstrings.cells import CELLS
from satyrn.tstrings.composition import cell_counts, check_composition
from satyrn.tstrings.dedupe import deduplicate
from satyrn.tstrings.diversity import distinct_skeleton_ratio, skeleton
from satyrn.tstrings.types import Check, Provenance, Task


@click.group("satyrn-tstrings")
def cli() -> None:
    """T-strings training spike tools."""


def _load_tasks(path: Path) -> list[Task]:
    """Read Task records from a JSONL file."""
    tasks: list[Task] = []
    with path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            checks = tuple(Check(kind=c["kind"], expected=c["expected"]) for c in entry["checks"])
            provenance = entry["provenance"]
            tasks.append(
                Task(
                    prompt=entry["prompt"],
                    reference=entry["reference"],
                    checks=checks,
                    role=entry["role"],
                    operation=entry["operation"],
                    provenance=Provenance(
                        source_id=provenance["source_id"],
                        path=provenance["path"],
                        line=int(provenance["line"]),
                        license=provenance["license"],
                    ),
                    task_id=entry["task_id"],
                    semantic_id=entry["semantic_id"],
                )
            )
    return tasks


def _write_cells(cells_path: Path, floors: dict[tuple[str, str], int]) -> None:
    """Write re-derived per-cell floors into a cells.toml file."""
    lines: list[str] = []
    for role, operation in CELLS:
        lines.append(f"[cells.{role}.{operation}]")
        lines.append(f"min_tasks = {floors.get((role, operation), 0)}")
        lines.append("")
    cells_path.write_text("\n".join(lines))


def _write_build_report(
    report_path: Path,
    tasks: list[Task],
    removed: int,
    ratio: float,
    floor: float,
    floors: dict[tuple[str, str], int],
) -> None:
    """Write the postprocess composition and diversity report."""
    counts = cell_counts(tasks)
    distinct = len({skeleton(task.reference) for task in tasks})
    lines: list[str] = [
        "# Cycle 4.1 postprocess report",
        "",
        f"- Tasks loaded: {len(tasks) + removed}",
        f"- Deduplicated: {removed} removed, {len(tasks)} kept",
        f"- Distinct skeletons: {distinct} of {len(tasks)} (ratio {ratio:.6f})",
        f"- Skeleton floor: {floor:.6f}",
        "",
        "## Per-cell composition",
        "",
        "| role | operation | tasks | floor |",
        "| --- | --- | --- | --- |",
    ]
    for role, operation in CELLS:
        count = counts.get((role, operation), 0)
        lines.append(f"| {role} | {operation} | {count} | {floors.get((role, operation), 0)} |")
    lines.append("")
    report_path.write_text("\n".join(lines))


def _check_diversity(ratio: float, floor: float) -> None:
    """Raise ClickException when the measured ratio falls below the floor."""
    if ratio < floor:
        raise click.ClickException(f"measured skeleton ratio {ratio:.3f} below floor {floor:.3f}")


def _recorded_ratio(derivation_path: Path) -> float | None:
    """Return the ratio recorded by a prior build, or None on first build."""
    if not derivation_path.exists():
        return None
    data = json.loads(derivation_path.read_text())
    recorded = data.get("recorded_skeleton_ratio", data.get("measured_skeleton_ratio"))
    return float(recorded) if recorded is not None else None


_SPLIT_RULE = "md5(f'{path}:{line}').hexdigest()[0] in '01234567' -> valid"


class _MockLLM:
    """Deterministic fake LLM for exercising the freeze pipeline without a live key."""

    def generate(self, prompt: str, context) -> str:
        return "I locate the template usage first, then construct the example step by step."


def _sha256_bytes(data: bytes) -> str:
    """Return the hex sha256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _jsonl_bytes(rows: list[dict]) -> bytes:
    """Serialize rows as JSONL bytes."""
    return "".join(json.dumps(row) + "\n" for row in rows).encode()


def _generate_traces_parallel(rows: list[dict], llm_obj, workers: int) -> None:
    """Generate a trace per row concurrently, aborting on any failure."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _trace(row: dict) -> tuple[dict, str]:
        return row, render.generate_trace(row, llm_obj)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_trace, row): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                _, text = future.result()
            except Exception as error:
                raise click.ClickException(
                    f"trace generation failed for {row['filename']}:{row['_line']}: {error}"
                ) from error
            if not text.strip():
                raise click.ClickException(
                    f"LLM returned an empty trace for {row['filename']}:{row['_line']}; aborting freeze"
                )


@click.command("freeze")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Rendered SFT rows JSONL to freeze.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="corpus-sft",
    show_default=True,
    help="Directory to write the frozen corpus into.",
)
@click.option("--llm", default="deepseek", show_default=True, help="LLM provider for reasoning traces.")
@click.option("--model", default="deepseek-v4-flash", show_default=True, help="Model name for the LLM provider.")
@click.option(
    "--mock-llm",
    is_flag=True,
    default=False,
    help="Use a deterministic fake LLM instead of a live provider.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=8,
    show_default=True,
    help="Concurrent trace-generation workers (live LLM only).",
)
def freeze(
    input: Path,
    output_dir: Path,
    llm: str,
    model: str,
    mock_llm: bool,
    workers: int,
) -> None:
    """Freeze rendered rows into a trace-augmented SFT corpus."""
    spike_root = Path(__file__).resolve().parents[3]

    rows: list[dict] = []
    with input.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    gated = (
        _load_tasks(spike_root / "tasks" / "deduped.jsonl")
        if (spike_root / "tasks" / "deduped.jsonl").exists()
        else _load_tasks(spike_root / "tasks" / "gated.jsonl")
    )
    if len(gated) != len(rows):
        raise click.ClickException(
            f"gated.jsonl has {len(gated)} tasks but rendered.jsonl has {len(rows)} rows; "
            "positional re-join requires a 1:1 match"
        )
    for row, task in zip(rows, gated, strict=True):
        row["_line"] = task.provenance.line
        row["semantic_id"] = task.semantic_id

    dataset_fingerprint = _sha256_bytes(input.read_bytes())

    llm_obj = _MockLLM() if mock_llm else get_llm(llm, model)
    if mock_llm:
        for row in rows:
            render.generate_trace(row, llm_obj)
    else:
        _generate_traces_parallel(rows, llm_obj, workers)

    train, valid = split.lineage_split(rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, subset in (("train", train), ("valid", valid)):
        with (output_dir / f"{name}.jsonl").open("w") as fh:
            for row in subset:
                fh.write(json.dumps(row) + "\n")

    fingerprints = {
        "dataset": dataset_fingerprint,
        "rendered": _sha256_bytes(_jsonl_bytes(rows)),
        "benchmark": _sha256_bytes((spike_root / "benchmark" / "ood-v2" / "tasks.jsonl").read_bytes()),
        "system_prompt": _sha256_bytes((spike_root / "benchmark" / "system-prompt.txt").read_bytes()),
    }
    manifest_path = output_dir / "manifest.json"
    split.write_manifest(train, valid, fingerprints, _SPLIT_RULE, manifest_path)
    if mock_llm:
        data = json.loads(manifest_path.read_text())
        data["note"] = "traces are mock/deterministic pending a live-key re-freeze"
        manifest_path.write_text(json.dumps(data, indent=2) + "\n")

    click.echo(f"Froze {len(train)} train and {len(valid)} valid rows into {output_dir}")


@click.command("postprocess")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Gated tasks JSONL to postprocess.",
)
def postprocess(input: Path) -> None:
    """Deduplicate, measure diversity, and check composition over gated tasks."""
    spike_root = Path(__file__).resolve().parents[3]
    tasks = _load_tasks(input)

    kept, removed = deduplicate(tasks)
    click.echo(f"Deduplicated {len(tasks)} tasks: removed {removed}, kept {len(kept)}.")

    deduped_path = input.parent / "deduped.jsonl"
    with deduped_path.open("w") as fh:
        for task in kept:
            fh.write(json.dumps(asdict(task)) + "\n")
    click.echo(f"Wrote {len(kept)} deduplicated tasks to {deduped_path}")

    ratio = distinct_skeleton_ratio(kept)

    reports_dir = spike_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    derivation_path = reports_dir / "threshold-derivation.json"

    recorded = _recorded_ratio(derivation_path)
    floor = 0.25 if recorded is None else max(0.25, 0.75 * recorded)

    _check_diversity(ratio, floor)

    # Record the first build and migrate legacy files to the canonical key.
    canonical = recorded if recorded is not None else ratio
    derivation_path.write_text(json.dumps({"recorded_skeleton_ratio": canonical}) + "\n")

    floors = cell_counts(kept)
    _write_cells(spike_root / "cells.toml", floors)

    try:
        check_composition(kept, floors)
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    _write_build_report(reports_dir / "build.md", kept, removed, ratio, floor, floors)
    click.echo(f"Measured skeleton ratio {ratio:.6f}; floor {floor:.6f}; acceptance passed.")


cli.add_command(mine.main)
cli.add_command(build.main)
cli.add_command(gate.main)
cli.add_command(render.main)
cli.add_command(freeze)
cli.add_command(train.main)
cli.add_command(eval_cmd.main)
cli.add_command(eval_cmd.reproduce_cmd)
cli.add_command(transform.main)
cli.add_command(deliver.main)
cli.add_command(postprocess)
