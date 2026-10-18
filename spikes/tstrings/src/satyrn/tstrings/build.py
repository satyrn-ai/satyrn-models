"""Deterministic task building from mined seeds."""

import ast
import builtins
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import asdict
from pathlib import Path

import click

from satyrn.tstrings.cells import load_cells, operations_of
from satyrn.tstrings.types import Check, Provenance, Seed, Task, semantic_id, task_id

_BUILTIN_NAMES = frozenset(dir(builtins))
_CONSTRUCT_HEADER = "from string.templatelib import Template\n\n"
_RENDER_HEADER = (
    "from string.templatelib import Template, Interpolation\n\n"
    "def _convert(value, conversion):\n"
    '    if conversion == "a":\n'
    "        return ascii(value)\n"
    '    if conversion == "r":\n'
    "        return repr(value)\n"
    '    if conversion == "s":\n'
    "        return str(value)\n"
    "    return value\n\n"
    "def _render(template):\n"
    "    parts = []\n"
    "    for item in template:\n"
    "        if isinstance(item, str):\n"
    "            parts.append(item)\n"
    "        elif isinstance(item, Interpolation):\n"
    "            parts.append(format(_convert(item.value, item.conversion), item.format_spec))\n"
    '    return "".join(parts)\n\n'
)

_FEATURE_CHECK = Check(kind="uses_feature", expected="string.templatelib")


def _collect_simple_assignments(
    tree: ast.Module,
    source: str,
    *,
    constants_only: bool = True,
) -> dict[str, tuple[str, int, int]]:
    """Return NAME -> (assignment_source, end_lineno, end_col) for single-target assignments."""
    assignments: dict[str, tuple[str, int, int]] = {}
    lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        # never treat a t-string/f-string literal itself as a carry-along assignment
        if isinstance(node.value, ast.JoinedStr):
            continue
        if constants_only and not isinstance(node.value, ast.Constant):
            continue
        segment = ast.get_source_segment(source, node)
        if segment is None:
            continue
        idx = node.lineno - 1
        indent = lines[idx][: node.col_offset] if 0 <= idx < len(lines) else ""
        if indent and not segment.startswith(indent):
            segment = indent + segment
        assignments[target.id] = (segment, node.end_lineno or node.lineno, node.end_col_offset)
    return assignments


def _interpolation_names(node: ast.AST) -> set[str]:
    """Return every NAME id referenced inside a literal's interpolation values."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.Interpolation, ast.FormattedValue)):
            for sub in ast.walk(child.value):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
    return names


def extract_literal(seed_text: str, need_interpolation: bool) -> tuple[str, list[str]] | None:
    """Return (literal_source, assignment_lines) for the first qualifying literal."""
    tree = ast.parse(seed_text)
    assignments = _collect_simple_assignments(tree, seed_text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.TemplateStr):
            continue
        interps = [n for n in ast.walk(node) if isinstance(n, (ast.Interpolation, ast.FormattedValue))]
        if need_interpolation and not interps:
            continue
        names = _interpolation_names(node) - _BUILTIN_NAMES
        literal_pos = (node.lineno, node.col_offset)
        missing = [
            name
            for name in names
            if name not in assignments or (assignments[name][1], assignments[name][2]) >= literal_pos
        ]
        if missing:
            continue
        literal = ast.get_source_segment(seed_text, node)
        if literal is None:
            continue
        needed = [assignments[name][0] for name in sorted(names)]
        return literal, needed
    return None


def _assemble(header: str, assignments: list[str], body: str) -> str:
    """Join a header, dedented assignment lines, and the operation body into a runnable program."""
    parts = [header]
    for line in assignments:
        parts.append(textwrap.dedent(line) + "\n")
    parts.append("\n" + body)
    return "".join(parts)


def _build_construct(literal: str, assignments: list[str]) -> tuple[str, tuple[Check, ...]]:
    """Build a construct reference printing the Template type name."""
    body = f"t = {literal}\nprint(type(t).__name__)\n"
    return _assemble(_CONSTRUCT_HEADER, assignments, body), (_FEATURE_CHECK,)


def _build_render(literal: str, assignments: list[str]) -> tuple[str, tuple[Check, ...]]:
    """Build a render reference printing the walked-and-joined string."""
    body = f"t = {literal}\nprint(_render(t))\n"
    return _assemble(_RENDER_HEADER, assignments, body), (_FEATURE_CHECK,)


def _build_read_strings(literal: str, assignments: list[str]) -> tuple[str, tuple[Check, ...]]:
    """Build a read_strings reference printing the Template's strings tuple."""
    body = f"t = {literal}\nprint(t.strings)\n"
    return _assemble(_CONSTRUCT_HEADER, assignments, body), (_FEATURE_CHECK,)


def _build_read_values(literal: str, assignments: list[str]) -> tuple[str, tuple[Check, ...]]:
    """Build a read_values reference printing the Template's values tuple."""
    body = f"t = {literal}\nprint(t.values)\n"
    return _assemble(_CONSTRUCT_HEADER, assignments, body), (_FEATURE_CHECK,)


def _build_read_interpolations(literal: str, assignments: list[str]) -> tuple[str, tuple[Check, ...]]:
    """Build a read_interpolations reference printing the first interpolation's expression."""
    body = f"t = {literal}\nprint(t.interpolations[0].expression)\n"
    return _assemble(_CONSTRUCT_HEADER, assignments, body), (_FEATURE_CHECK,)


def _build_negative_control(seed_text: str) -> tuple[str, tuple[Check, ...]] | None:
    """Build a negative-control reference from the seed's first f-string and its assignments."""
    tree = ast.parse(seed_text)
    assignments = _collect_simple_assignments(tree, seed_text, constants_only=False)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and not isinstance(node, ast.TemplateStr):
            fstring_source = ast.get_source_segment(seed_text, node)
            if fstring_source is None:
                continue
            names = _interpolation_names(node)
            if names - set(assignments) - _BUILTIN_NAMES:
                continue
            needed = [assignments[name][0] for name in sorted(names) if name in assignments]
            body = f"result = {fstring_source}\nprint(result)\n"
            return _assemble("", needed, body), ()
    return None


_BUILDERS = {
    "construct": _build_construct,
    "render": _build_render,
    "read_strings": _build_read_strings,
    "read_values": _build_read_values,
    "read_interpolations": _build_read_interpolations,
}


def build_reference(operation: str, seed_text: str) -> tuple[str, tuple[Check, ...]] | None:
    """Assemble a runnable reference program plus its checks for the given operation."""
    if operation == "negative_control":
        return _build_negative_control(seed_text)
    builder = _BUILDERS.get(operation)
    if builder is None:
        return None
    need_interpolation = operation == "read_interpolations"
    extracted = extract_literal(seed_text, need_interpolation=need_interpolation)
    if extracted is None:
        return None
    literal, assignments = extracted
    return builder(literal, assignments)


def run_reference(reference: str, timeout: int = 10) -> tuple[int, str]:
    """Execute a reference program and return its (returncode, stdout)."""
    completed = subprocess.run(
        [sys.executable, "-c", reference],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout


PROMPT_FAMILIES: dict[str, tuple[str, ...]] = {
    "build": ("Using Python t-strings, {op}. Print the result.",),
    "create": ("Write a Python program to {op}. Print what it produces.",),
    "show": ("Demonstrate Python t-strings by showing how to {op}. Print the outcome.",),
    "teach": ("Show how Python t-strings let you {op}. Print the value.",),
    "example": ("Give an example of how to {op} with Python t-strings. Print the result.",),
    "output": ("Produce a small Python example to {op}. Print the output.",),
}

OPERATION_VERBS: dict[str, str] = {
    "construct": "build a Template",
    "render": "render a Template to a string",
    "read_strings": "extract a Template's static parts (its .strings tuple)",
    "read_values": "read a Template's evaluated values (its .values tuple)",
    "read_interpolations": "inspect an interpolation's expression, conversion, and format spec",
    "negative_control": "format a value into a string using ordinary Python string features (no t-strings)",
}


def fill_family(family: str, operation: str, seed_values: dict) -> str:
    """Fill the family's first phrasing with the operation's verb phrase."""
    return PROMPT_FAMILIES[family][0].format(op=OPERATION_VERBS[operation])


def prompt_fingerprint(prompt: str, seed_tokens: set[str]) -> str:
    """Normalize a prompt into a seed-insensitive fingerprint string."""
    normalized = re.sub(r"\s+", " ", prompt.lower())
    for token in seed_tokens:
        normalized = re.sub(rf"\b{re.escape(token.lower())}\b", "#", normalized)
    return normalized


OP_ORDER: tuple[str, ...] = (
    "construct",
    "render",
    "read_strings",
    "read_values",
    "read_interpolations",
    "negative_control",
)

FAMILY_ORDER: tuple[str, ...] = tuple(PROMPT_FAMILIES.keys())


def _load_seeds(seeds_path: Path) -> list[Seed]:
    """Read mined seeds from a JSONL file."""
    seeds: list[Seed] = []
    with seeds_path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            seeds.append(
                Seed(
                    text=entry["text"],
                    source_id=entry["source_id"],
                    path=entry["path"],
                    line=int(entry["line"]),
                )
            )
    return seeds


def build_tasks(
    seeds_path: Path,
    cells_path: Path,
    output_dir: Path | None = None,
    reports_dir: Path | None = None,
) -> list[Task]:
    """Build teachable tasks from mined seeds and optionally write outputs."""
    load_cells(cells_path)  # validate the cell table
    seeds = _load_seeds(seeds_path)

    drops: list[dict] = []
    candidates: list[dict] = []  # ordered by OP_ORDER then seed order

    for seed in seeds:
        ops = operations_of(seed.text)
        if not ops:
            drops.append(
                {
                    "source_id": seed.source_id,
                    "path": seed.path,
                    "line": seed.line,
                    "operation": None,
                    "reason": "no clean operation",
                }
            )
            continue
        for operation in OP_ORDER:
            if operation not in ops:
                continue
            built = build_reference(operation, seed.text)
            if built is None:
                drops.append(
                    {
                        "source_id": seed.source_id,
                        "path": seed.path,
                        "line": seed.line,
                        "operation": operation,
                        "reason": f"{operation}: no qualifying literal",
                    }
                )
                continue
            reference, checks = built
            try:
                code, out = run_reference(reference)
            except subprocess.TimeoutExpired:
                code, out = -1, ""
            if code != 0:
                drops.append(
                    {
                        "source_id": seed.source_id,
                        "path": seed.path,
                        "line": seed.line,
                        "operation": operation,
                        "reason": f"{operation}: reference failed to run",
                    }
                )
                continue
            try:
                code2, out2 = run_reference(reference)
            except subprocess.TimeoutExpired:
                code2, out2 = -1, ""
            if code2 == 0 and out2 != out:
                drops.append(
                    {
                        "source_id": seed.source_id,
                        "path": seed.path,
                        "line": seed.line,
                        "operation": operation,
                        "reason": f"{operation}: non-deterministic output",
                    }
                )
                continue
            candidates.append(
                {
                    "seed": seed,
                    "operation": operation,
                    "reference": reference,
                    "checks": checks,
                    "expected_stdout": out,
                }
            )

    tasks: list[Task] = []
    families: list[str] = []
    family_counters: dict[tuple[str, str], int] = {}
    for cand in candidates:
        seed = cand["seed"]
        operation = cand["operation"]
        role = "author" if operation == "construct" else "consumer"
        cell = (role, operation)
        family = FAMILY_ORDER[family_counters.get(cell, 0) % len(FAMILY_ORDER)]
        family_counters[cell] = family_counters.get(cell, 0) + 1
        families.append(family)
        prompt = fill_family(family, operation, {})
        checks = cand["checks"] + (Check(kind="expected_stdout", expected=cand["expected_stdout"]),)
        provenance = Provenance(
            source_id=seed.source_id,
            path=seed.path,
            line=seed.line,
            license="PSF-2.0",
        )
        fields = {
            "prompt": prompt,
            "reference": cand["reference"],
            "checks": tuple(asdict(c) for c in checks),
            "role": role,
            "operation": operation,
            "provenance": asdict(provenance),
        }
        tid = task_id(fields)
        sid = semantic_id(fields)
        tasks.append(
            Task(
                prompt=prompt,
                reference=cand["reference"],
                checks=checks,
                role=role,
                operation=operation,
                provenance=provenance,
                task_id=tid,
                semantic_id=sid,
            )
        )

    if output_dir is not None:
        output_path = output_dir / "built.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as fh:
            for task in tasks:
                fh.write(json.dumps(asdict(task)) + "\n")

    if reports_dir is not None:
        _write_reports(reports_dir, tasks, families, drops, seeds)

    return tasks


def _write_reports(
    reports_dir: Path,
    tasks: list[Task],
    families: list[str],
    drops: list[dict],
    seeds: list[Seed],
) -> None:
    """Write build.md and dropped.jsonl into the reports directory."""
    reports_dir.mkdir(parents=True, exist_ok=True)

    cell_counts: dict[tuple[str, str], int] = {}
    family_ops: set[tuple[str, str]] = set()
    for family, task in zip(families, tasks, strict=True):
        cell_counts[(task.role, task.operation)] = cell_counts.get((task.role, task.operation), 0) + 1
        family_ops.add((family, task.operation))

    drop_counts: dict[str, int] = {}
    for drop in drops:
        drop_counts[drop["reason"]] = drop_counts.get(drop["reason"], 0) + 1

    lines: list[str] = ["# Cycle 2.1 build report", ""]
    lines.append(f"- Seeds considered: {len(seeds)}")
    lines.append(f"- Tasks built: {len(tasks)}")
    lines.append(f"- Tasks dropped: {len(drops)}")
    lines.append(f"- Distinct (family, operation) fingerprints: {len(family_ops)}")
    lines.append("")
    lines.append("## Per-cell counts")
    lines.append("")
    lines.append("| role | operation | tasks |")
    lines.append("| --- | --- | --- |")
    cell_rows: list[tuple[str, str]] = [
        ("author", "construct"),
        ("consumer", "render"),
        ("consumer", "read_strings"),
        ("consumer", "read_values"),
        ("consumer", "read_interpolations"),
        ("consumer", "negative_control"),
    ]
    for role, operation in cell_rows:
        count = cell_counts.get((role, operation), 0)
        lines.append(f"| {role} | {operation} | {count} |")
    lines.append("")
    lines.append("## Dropped counts")
    lines.append("")
    if drop_counts:
        lines.append("| reason | count |")
        lines.append("| --- | --- |")
        for reason in sorted(drop_counts):
            lines.append(f"| {reason} | {drop_counts[reason]} |")
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## Dropped seeds / operations")
    lines.append("")
    if drops:
        lines.append("| source_id | path | line | operation | reason |")
        lines.append("| --- | --- | --- | --- | --- |")
        for drop in drops:
            lines.append(
                f"| {drop['source_id']} | {drop['path']} | {drop['line']} | {drop['operation']} | {drop['reason']} |"
            )
    else:
        lines.append("(none)")
    lines.append("")
    (reports_dir / "build.md").write_text("\n".join(lines))

    with (reports_dir / "dropped.jsonl").open("w") as fh:
        for drop in drops:
            fh.write(json.dumps(drop) + "\n")


@click.command("build")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Mined seeds JSONL to build tasks from.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="tasks",
    show_default=True,
    help="Directory to write built tasks into.",
)
def main(input: Path, output_dir: Path) -> None:
    """Build teachable tasks from mined seeds."""
    spike_root = Path(__file__).resolve().parents[3]
    tasks = build_tasks(
        input,
        spike_root / "cells.toml",
        output_dir,
        spike_root / "reports",
    )
    output_path = output_dir / "built.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as fh:
        for task in tasks:
            fh.write(json.dumps(asdict(task)) + "\n")
    click.echo(f"Wrote {len(tasks)} tasks to {output_path}")
