"""Gate candidate tasks against the anti-vacuity check."""

import ast
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import click

from satyrn.tstrings.types import Accepted, Check, InfrastructureFailure, Outcome, Provenance, Rejection, Task

_EXECUTOR_TIMEOUT = "__SATYRN_TSTRINGS_EXECUTOR_TIMEOUT__"
_SANDBOX_TIMEOUT_MESSAGE = "[did not terminate within 10 seconds]"
_RUNTIME_MARKER = "Traceback (most recent call last)"


def _subprocess_executor(timeout: int, env: dict[str, str] | None = None) -> Callable[[str], str]:
    """Build a subprocess executor that runs a program with a fixed timeout."""

    def run(program: str) -> str:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", program],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return _EXECUTOR_TIMEOUT
        return completed.stdout

    return run


def _sandbox_executor() -> Callable[[str], str]:
    """Build a gVisor sandbox executor, importing Docker lazily."""
    from satyrn.dataset.utils.sandbox import Sandbox

    sandbox = Sandbox("3.14")

    def run(program: str) -> str:
        stdout = sandbox.run(program)
        if stdout == _SANDBOX_TIMEOUT_MESSAGE:
            return _EXECUTOR_TIMEOUT
        return stdout

    return run


def _uses_feature(code: str, expected: str) -> bool:
    """Return True if the code's AST uses the required node or module."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.TemplateStr):
            return True
        if isinstance(node, ast.Import) and any(alias.name == expected for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == expected:
            return True
    return False


def _encode_verdict(outcome: Outcome) -> dict:
    """Serialize an outcome to a JSON-able verdict dict."""
    if isinstance(outcome, Accepted):
        return {"kind": "accepted", "observations": outcome.observations}
    return {"kind": "rejected", "stage": outcome.stage, "detail": outcome.detail}


def _decode_verdict(data: dict) -> Outcome | None:
    """Decode a parsed verdict dict back into an outcome."""
    kind = data.get("kind")
    if kind == "accepted" and isinstance(data.get("observations"), dict):
        return Accepted(observations=data["observations"])
    if kind == "rejected" and isinstance(data.get("stage"), str) and isinstance(data.get("detail"), str):
        return Rejection(stage=data["stage"], detail=data["detail"])
    return None


def _parse_verdict(combined: str) -> Outcome | None:
    """Scan the stream backwards for the last JSON object and decode it."""
    for line in reversed(combined.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        outcome = _decode_verdict(data)
        if outcome is not None:
            return outcome
    return None


def run_candidate(
    code: str,
    checks: tuple[Check, ...],
    *,
    timeout: int = 10,
    executor: Callable[[str], str] | None = None,
) -> Outcome:
    """Run a candidate once and return a structured outcome."""
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return Rejection(stage="syntax", detail=str(exc))

    run = executor if executor is not None else _sandbox_executor()
    stdout = run(code)
    if stdout == _EXECUTOR_TIMEOUT:
        return InfrastructureFailure(detail="timeout")
    if _RUNTIME_MARKER in stdout:
        return Rejection(stage="runtime", detail=_last_traceback_line(stdout))

    outcome: Outcome = Accepted(observations={})
    for check in checks:
        if check.kind == "expected_stdout":
            satisfied = stdout == check.expected
        elif check.kind == "uses_feature":
            satisfied = _uses_feature(code, check.expected)
        else:
            return Rejection(stage="semantic_check", detail=f"unsupported check kind {check.kind!r}")
        if not satisfied:
            outcome = Rejection(stage="semantic_check", detail=f"{check.kind} {check.expected!r} not satisfied")
            break

    parsed = _parse_verdict(f"{stdout}\n{json.dumps(_encode_verdict(outcome))}")
    return parsed if parsed is not None else InfrastructureFailure(detail="unparseable verdict")


def _last_traceback_line(output: str) -> str:
    """Return the final non-blank line of a traceback, or a generic label."""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return "runtime exception"


@dataclass(frozen=True, kw_only=True)
class Qualified:
    """A task proven to require the t-strings feature."""

    degenerates_run: int


@dataclass(frozen=True, kw_only=True)
class Vacuous:
    """A degenerate solution was accepted, so the task does not require t-strings."""

    degenerate: str


@dataclass(frozen=True, kw_only=True)
class VacuityUntested:
    """The anti-vacuity proof did not run properly; the task is not a pass."""

    degenerate: str
    detail: str


Qualification = Qualified | Vacuous | VacuityUntested


def _expected_stdout(task: Task) -> str:
    """Return the task's expected_stdout value, or the empty string."""
    for check in task.checks:
        if check.kind == "expected_stdout":
            return check.expected
    return ""


def _template_strs(reference: str) -> list[tuple[str, ast.TemplateStr]]:
    """Return the TemplateStr literals in reference, in source order."""
    tree = ast.parse(reference)
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.TemplateStr)]
    nodes.sort(key=lambda node: (node.lineno, node.col_offset))
    result: list[tuple[str, ast.TemplateStr]] = []
    for node in nodes:
        segment = ast.get_source_segment(reference, node)
        if segment is not None:
            result.append((segment, node))
    return result


def _first_template_str(reference: str) -> tuple[str, ast.TemplateStr] | None:
    """Return the first TemplateStr literal source and node, or None."""
    found = _template_strs(reference)
    return found[0] if found else None


def _carry_assignments(reference: str) -> str:
    """Return the reference's simple non-literal assignments, one per line."""
    tree = ast.parse(reference)
    segments: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        if not isinstance(node.targets[0], ast.Name):
            continue
        if isinstance(node.value, (ast.TemplateStr, ast.JoinedStr)):
            continue
        segment = ast.get_source_segment(reference, node)
        if segment is not None:
            segments.append((node.lineno, segment))
    segments.sort()
    return "".join(f"{segment}\n" for _, segment in segments)


def _assemble(reference: str, body: str) -> str:
    """Join the reference's carried assignments with a degenerate body line."""
    return _carry_assignments(reference) + body


def _as_fstring(segment: str) -> str:
    """Rewrite a TemplateStr literal source to an equivalent f-string."""
    if segment.startswith("t"):
        return "f" + segment[1:]
    return segment


def degenerate_fstring_substitute(task: Task) -> str:
    """Solve with an f-string, or hardcode the output when no TemplateStr exists."""
    literal = _first_template_str(task.reference)
    if literal is None:
        return degenerate_hardcoded_output(task)
    segment, _node = literal
    return _assemble(task.reference, f"print({_as_fstring(segment)})\n")


def degenerate_repr_as_render(task: Task) -> str:
    """Render the template via repr instead of its string value."""
    literal = _first_template_str(task.reference)
    if literal is None:
        return degenerate_hardcoded_output(task)
    segment, _node = literal
    return _assemble(task.reference, f"print(repr({_as_fstring(segment)}))\n")


def degenerate_static_join(task: Task) -> str:
    """Join only the template's static string parts, ignoring interpolations."""
    literal = _first_template_str(task.reference)
    if literal is None:
        return degenerate_hardcoded_output(task)
    _segment, node = literal
    parts = [repr(value.value) for value in node.values if isinstance(value, ast.Constant)]
    return _assemble(task.reference, f'print("".join([{", ".join(parts)}]))\n')


def degenerate_conversion_omission(task: Task) -> str:
    """Render the template while ignoring conversion specifiers."""
    literal = _first_template_str(task.reference)
    if literal is None:
        return degenerate_hardcoded_output(task)
    _segment, node = literal
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(repr(value.value))
        else:
            parts.append(f"str({value.str})")
    return _assemble(task.reference, f'print("".join([{", ".join(parts)}]))\n')


def degenerate_hardcoded_output(task: Task) -> str:
    """Print the expected_stdout value verbatim, with no logic."""
    return f"import sys\nsys.stdout.write({_expected_stdout(task)!r})\n"


_DEGENERATES: tuple[tuple[str, Callable[[Task], str]], ...] = (
    ("fstring_substitute", degenerate_fstring_substitute),
    ("repr_as_render", degenerate_repr_as_render),
    ("static_join", degenerate_static_join),
    ("conversion_omission", degenerate_conversion_omission),
    ("hardcoded_output", degenerate_hardcoded_output),
)


def _describe(outcome: Outcome) -> str:
    """Describe an outcome concisely for a drop record."""
    if isinstance(outcome, Accepted):
        return "accepted"
    if isinstance(outcome, Rejection):
        return f"rejected at {outcome.stage}: {outcome.detail}"
    return f"infrastructure failure: {outcome.detail}"


def _has_template_str(reference: str) -> bool:
    """Return True if reference's AST contains a TemplateStr literal."""
    tree = ast.parse(reference)
    return any(isinstance(node, ast.TemplateStr) for node in ast.walk(tree))


def qualify(task: Task, *, executor: Callable[[str], str] | None = None) -> Qualification:
    """Prove task non-vacuous by running the reference then each degenerate."""
    reference = run_candidate(task.reference, task.checks, executor=executor)
    if not isinstance(reference, Accepted):
        return VacuityUntested(degenerate="reference", detail=_describe(reference))

    if task.operation == "negative_control":
        if _has_template_str(task.reference):
            return VacuityUntested(degenerate="reference", detail="negative_control reference contains a TemplateStr")
        return Qualified(degenerates_run=0)

    for name, builder in _DEGENERATES:
        outcome = run_candidate(builder(task), task.checks, executor=executor)
        if isinstance(outcome, Accepted):
            return Vacuous(degenerate=name)
        if not (isinstance(outcome, Rejection) and outcome.stage == "semantic_check"):
            return VacuityUntested(degenerate=name, detail=_describe(outcome))

    return Qualified(degenerates_run=len(_DEGENERATES))


def _drop_record(task: Task, reason: str) -> dict:
    """Build a drop record for a task that failed the gate."""
    return {
        "task_id": task.task_id,
        "source_id": task.provenance.source_id,
        "path": task.provenance.path,
        "line": task.provenance.line,
        "operation": task.operation,
        "reason": reason,
    }


def _drop_task_ids(path: Path) -> set[str]:
    """Return the task_ids already recorded in a drops file."""
    try:
        with path.open("r") as fh:
            ids: set[str] = set()
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                if "task_id" in record:
                    ids.add(record["task_id"])
            return ids
    except FileNotFoundError:
        return set()


def _append_drops(path: Path, drops: list[dict]) -> None:
    """Append drop records to path, skipping task_ids already present."""
    existing = _drop_task_ids(path)
    with path.open("a") as fh:
        for drop in drops:
            if drop["task_id"] in existing:
                continue
            fh.write(json.dumps(drop) + "\n")
            existing.add(drop["task_id"])


def gate_tasks(
    tasks: list[Task],
    executor: Callable[[str], str] | None = None,
) -> tuple[list[Task], list[dict]]:
    """Return the qualified tasks and the drop records for the rest."""
    qualified: list[Task] = []
    drops: list[dict] = []
    for task in tasks:
        qualification = qualify(task, executor=executor)
        if isinstance(qualification, Qualified):
            qualified.append(task)
        elif isinstance(qualification, Vacuous):
            drops.append(_drop_record(task, f"vacuous: {qualification.degenerate} accepted"))
        else:
            drops.append(_drop_record(task, f"vacuity untested: {qualification.degenerate}: {qualification.detail}"))
    return qualified, drops


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


@click.command("gate")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Built tasks JSONL to gate.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="tasks",
    show_default=True,
    help="Directory to write qualified tasks into.",
)
@click.option(
    "--subprocess",
    is_flag=True,
    help="Run candidates in a subprocess instead of the gVisor sandbox.",
)
def main(input: Path, output_dir: Path, subprocess: bool) -> None:
    """Gate candidate tasks against the anti-vacuity check."""
    tasks = _load_tasks(input)
    executor = _subprocess_executor(10) if subprocess else None
    qualified, drops = gate_tasks(tasks, executor=executor)

    output_path = output_dir / "gated.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as fh:
        for task in qualified:
            fh.write(json.dumps(asdict(task)) + "\n")

    spike_root = Path(__file__).resolve().parents[3]
    reports_dir = spike_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    _append_drops(reports_dir / "dropped.jsonl", drops)

    click.echo(f"Qualified {len(qualified)} tasks; dropped {len(drops)} tasks.")
    click.echo(f"Wrote {len(qualified)} qualified tasks to {output_path}")
