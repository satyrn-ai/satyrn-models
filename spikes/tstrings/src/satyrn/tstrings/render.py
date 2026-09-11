"""Render qualified tasks as SFT rows."""

import json
from pathlib import Path

import click

from satyrn.dataset.llm.context import Context
from satyrn.tstrings.types import Check, Provenance, Task

_TRACE_SYSTEM_PROMPT = "You are writing a first-person reasoning trace for a Python teaching example."


def contamination_check(rows: list[dict], benchmark_path: Path) -> None:
    """Raise ValueError when any rendered row overlaps the OOD benchmark (ground rule 2.4)."""
    benchmark_rows: list[dict] = []
    with benchmark_path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            benchmark_rows.append(json.loads(line))

    pairs = {(row["prompt"], row["reference"]) for row in benchmark_rows}
    references = {row["reference"] for row in benchmark_rows}

    for row in rows:
        if (row["idea"], row["code"]) in pairs or row["code"] in references:
            raise ValueError("rendered row overlaps the OOD benchmark (ground rule 2.4)")


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


def generate_trace(row: dict, llm) -> str:
    """Return a first-person reasoning trace and store it in the row's trace."""
    context = Context()
    context.system_prompt = _TRACE_SYSTEM_PROMPT
    prompt = (
        "Write a first-person reasoning trace for this Python teaching example.\n\n"
        f"Example idea: {row['idea']}\n\n"
        f"Example code:\n```python\n{row['code']}\n```"
    )
    text = llm.generate(prompt, context)
    row["trace"] = text
    return text


def render_tasks(tasks: list[Task], system_prompt: str) -> list[dict]:
    """Return one converged SFT row per task, per the spec's ruling 2."""
    rows: list[dict] = []
    for task in tasks:
        expected = next(
            (check.expected for check in task.checks if check.kind == "expected_stdout"),
            "",
        )
        rows.append(
            {
                "prompt": [
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": task.prompt},
                ],
                "completion": [
                    {
                        "role": "assistant",
                        "content": f"```python\n{task.reference}\n```",
                    }
                ],
                "filename": task.provenance.path,
                "python_version": "3.14",
                "idea": task.prompt,
                "code": task.reference,
                "trace": "",
                "expected_output": expected,
            }
        )
    return rows


@click.command("render")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Gated tasks JSONL to render.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="tasks",
    show_default=True,
    help="Directory to write SFT rows into.",
)
def main(input: Path, output_dir: Path) -> None:
    """Render qualified tasks as converged SFT rows."""
    spike_root = Path(__file__).resolve().parents[3]
    system_prompt = (spike_root / "benchmark" / "system-prompt.txt").read_text()
    tasks = _load_tasks(input)
    rows = render_tasks(tasks, system_prompt)
    contamination_check(rows, spike_root / "benchmark" / "ood-v2" / "tasks.jsonl")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "rendered.jsonl"
    with output_path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    click.echo(f"Rendered {len(rows)} rows into {output_path}")
