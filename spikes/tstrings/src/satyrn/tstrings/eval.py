"""Evaluate adapters against the out-of-distribution benchmark."""

import ast
import json
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import click

from satyrn.tstrings.gate import _EXECUTOR_TIMEOUT, _subprocess_executor

_VERDICT_MARKER = "__SATYRN_TSTRINGS_VERDICT__"
_SCORING_TIMEOUT = 15
_DEFAULT_MODEL = "jedisct1/Mellum2-12B-A2.5B-Instruct-mlx-8bit"
_SPIKE_ROOT = Path(__file__).resolve().parents[3]


def extract_code(completion: str) -> str:
    """Return the last fenced block, truncated to the longest compiling prefix."""
    if "<think>" in completion:
        closed = re.split(r"</think>", completion, maxsplit=1)
        completion = closed[1] if len(closed) > 1 else ""
    completion = completion.split("<|im_end|>")[0].split("<|endoftext|>")[0]
    blocks = re.findall(r"```(?:python)?\s*\n?(.*?)```", completion, re.DOTALL)
    if blocks:
        completion = blocks[-1].strip()
    lines = completion.splitlines()
    for cut in range(len(lines), 0, -1):
        candidate = "\n".join(lines[:cut])
        try:
            compile(candidate, "<candidate>", "exec")
            return candidate
        except SyntaxError:
            continue
    return completion.strip()


def _answer_name(task: dict) -> str:
    """Return the name the task's checks require, defaulting to ``result``."""
    for check in task["checks"]:
        name = check.get("name")
        if name:
            return name
    return "result"


def _mechanism_failure(task: dict, tree: ast.AST) -> str | None:
    """Return the mechanism failure reason, or None when satisfied."""
    config = task["policy"]["config"]
    has_template = any(isinstance(node, ast.TemplateStr) for node in ast.walk(tree))
    if config["requires_template"] and not has_template:
        return "no t-string literal found where reference uses one"
    return None


def _deterministic_env() -> dict:
    """Return a scoring environment with hash randomization disabled."""
    return {**os.environ, "PYTHONHASHSEED": "0"}


def _probe(program: str, name: str) -> str:
    """Wrap ``program`` so it reports the canonical value of ``name``."""
    return "\n".join(
        [
            "import json",
            "def _canon(value):",
            "    if isinstance(value, (set, frozenset)):",
            "        return ['set', sorted(repr(item) for item in value)]",
            "    return ['value', repr(value)]",
            f"_source = {program!r}",
            f"_name = {name!r}",
            'namespace = {"__name__": "__main__"}',
            "try:",
            '    exec(compile(_source, "<candidate>", "exec"), namespace)',
            "except Exception as _exc:",
            "    _verdict = {'status': 'raised', 'exc': type(_exc).__name__}",
            "else:",
            "    if _name not in namespace:",
            "        _verdict = {'status': 'missing'}",
            "    else:",
            "        _verdict = {'status': 'ok', 'value': _canon(namespace[_name])}",
            "print()",
            f"print({_VERDICT_MARKER!r} + json.dumps(_verdict))",
        ]
    )


def _run_verdict(program: str, name: str, run: Callable[[str], str]) -> dict:
    """Execute ``program`` in a subprocess and return its structured verdict."""
    stdout = run(_probe(program, name))
    if stdout == _EXECUTOR_TIMEOUT:
        return {"status": "timeout"}
    for line in reversed(stdout.splitlines()):
        if line.startswith(_VERDICT_MARKER):
            try:
                return json.loads(line[len(_VERDICT_MARKER) :])
            except json.JSONDecodeError:
                continue
    return {"status": "raised", "exc": "unparseable verdict"}


def score_completion(completion: str, task: dict) -> dict:
    """Score a completion for value correctness and t-string mechanism."""
    candidate = extract_code(completion)
    name = _answer_name(task)
    base = {
        "candidate": candidate,
        "prompt": task["prompt"],
        "reference": task["reference"],
        "id": task["id"],
    }
    try:
        tree = ast.parse(candidate)
    except SyntaxError as exc:
        return {
            **base,
            "passed": False,
            "policy_passed": False,
            "stage": "candidate_parse",
            "reason": f"syntax error: {exc}",
        }

    run = _subprocess_executor(_SCORING_TIMEOUT, env=_deterministic_env())

    candidate_verdict = _run_verdict(candidate, name, run)
    if candidate_verdict["status"] == "timeout":
        return {**base, "passed": False, "policy_passed": False, "stage": "subprocess", "reason": "timeout"}
    if candidate_verdict["status"] == "raised":
        return {
            **base,
            "passed": False,
            "policy_passed": False,
            "stage": "candidate_execute",
            "reason": f"candidate raised {candidate_verdict.get('exc', '?')}",
        }
    if candidate_verdict["status"] == "missing":
        return {
            **base,
            "passed": False,
            "policy_passed": False,
            "stage": "semantic_check",
            "reason": f"candidate namespace missing {name!r}",
        }

    reference_verdict = _run_verdict(task["reference"], name, run)
    if reference_verdict["status"] != "ok":
        return {
            **base,
            "passed": False,
            "policy_passed": False,
            "stage": "subprocess",
            "reason": "reference did not run",
        }

    if candidate_verdict["value"] != reference_verdict["value"]:
        return {
            **base,
            "passed": False,
            "policy_passed": False,
            "stage": "semantic_check",
            "reason": f"{name!r} mismatch",
        }

    mechanism = _mechanism_failure(task, tree)
    if mechanism is not None:
        return {**base, "passed": True, "policy_passed": False, "stage": "policy", "reason": mechanism}

    return {**base, "passed": True, "policy_passed": True, "stage": None, "reason": None}


def score_results(completions: list[str], tasks: list[dict]) -> dict:
    """Aggregate per-completion scores into a summary and result items."""
    results = []
    passed = 0
    mechanism_passed = 0
    failure_stages: dict[str, int] = {}
    for completion, task in zip(completions, tasks, strict=True):
        started = time.perf_counter()
        result = score_completion(completion, task)
        result["completion"] = completion
        result["elapsed"] = round(time.perf_counter() - started, 2)
        results.append(result)
        if result["passed"]:
            passed += 1
            if result["policy_passed"]:
                mechanism_passed += 1
            else:
                failure_stages["policy"] = failure_stages.get("policy", 0) + 1
        else:
            stage = result["stage"] or "candidate_execute"
            failure_stages[stage] = failure_stages.get(stage, 0) + 1
    total = len(tasks)
    return {
        "summary": {
            "failure_stages": dict(sorted(failure_stages.items())),
            "passed": passed,
            "score": round(mechanism_passed / total, 3) if total else 0.0,
            "total": total,
        },
        "results": results,
    }


def load_reference_scores(paths: list[Path]) -> dict[str, float]:
    """Read each result file's summary score keyed by filename stem."""
    scores = {}
    for path in paths:
        data = json.loads(path.read_text())
        scores[path.stem] = data["summary"]["score"]
    return scores


@dataclass(frozen=True)
class _Tier:
    """One reproduction arm: its model/adapter/docs inputs and reference target."""

    name: str
    target: float | tuple[float, float]
    model: str
    adapter_path: Path | None = None
    docs: bool = False


def _within_tolerance(score: float, target: float | tuple[float, float], tolerance: float = 0.03) -> bool:
    """Return True when ``score`` lands within ``tolerance`` of the target."""
    if isinstance(target, tuple):
        low, high = target
        return low - tolerance <= score <= high + tolerance
    return abs(score - target) <= tolerance


def _describe_target(target: float | tuple[float, float]) -> str:
    """Format a target as a single number or a ``low-high`` range."""
    if isinstance(target, tuple):
        return f"{target[0]}\u2013{target[1]}"
    return str(target)


def _load_model(model: str, adapter_path: Path | None = None) -> tuple[object, object]:
    """Load the base model and optional adapter once per tier."""
    import mlx_lm

    return mlx_lm.load(model, adapter_path=str(adapter_path) if adapter_path else None)


def generate(
    prompt: str,
    *,
    model: object,
    tokenizer: object,
    docs: str | None = None,
    system_prompt: str,
) -> str:
    """Generate a completion from an already-loaded model and tokenizer."""
    import mlx_lm
    from mlx_lm import sample_utils

    parts = [system_prompt]
    if docs:
        parts.append(docs)
    parts.append(prompt)
    full_prompt = "\n\n".join(part.rstrip() for part in parts)
    sampler = sample_utils.make_sampler(temp=0.0)
    return mlx_lm.generate(model, tokenizer, full_prompt, max_tokens=700, sampler=sampler)


def reproduce(
    tasks: Sequence[dict],
    tiers: Sequence[_Tier],
    *,
    system_prompt: str,
    docs_block: str = "",
    generate_fn: Callable[..., str] | None = None,
    score_fn: Callable[[list[str], Sequence[dict]], dict] | None = None,
    load_fn: Callable[[str, Path | None], tuple[object, object]] | None = None,
) -> dict:
    """Run each tier through the harness and compare its score to the target."""
    generate_completion = generate_fn or generate
    load_model = load_fn or _load_model
    score = score_fn or score_results
    task_list = list(tasks)
    report = {"tiers": [], "warnings": []}
    for tier in tiers:
        model, tokenizer = load_model(tier.model, tier.adapter_path)
        docs = docs_block if tier.docs else None
        completions = [
            generate_completion(
                task["prompt"],
                model=model,
                tokenizer=tokenizer,
                docs=docs,
                system_prompt=system_prompt,
            )
            for task in task_list
        ]
        actual = score(completions, task_list)["summary"]["score"]
        passed = _within_tolerance(actual, tier.target)
        result = {
            "tier": tier.name,
            "actual": actual,
            "target": tier.target,
            "passed": passed,
        }
        report["tiers"].append(result)
        if not passed:
            report["warnings"].append(f"{tier.name}: {actual} outside {_describe_target(tier.target)} \u00b1 0.03")
    return report


@click.command("eval")
@click.option(
    "-i",
    "--input",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Benchmark tasks jsonl to evaluate against.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="reports",
    show_default=True,
    help="Directory to write REPORT.md into.",
)
@click.option("--model", default=_DEFAULT_MODEL, show_default=True, help="Base model to evaluate.")
@click.option(
    "--adapter-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="adapters",
    show_default=True,
    help="Directory of trained adapters (seed<N>/adapters.safetensors).",
)
def main(input: Path, output_dir: Path, model: str, adapter_dir: Path) -> None:
    """Evaluate base, docs, and trained adapters against the benchmark."""
    tasks = _load_jsonl_tasks(input)
    system_prompt = (_SPIKE_ROOT / "benchmark" / "system-prompt.txt").read_text().strip()
    docs_block = (_SPIKE_ROOT / "benchmark" / "pep750-docs-context-v3.md").read_text()

    adapter_paths = sorted(adapter_dir.glob("seed*/adapters.safetensors")) if adapter_dir.exists() else []
    if not adapter_paths:
        raise click.ClickException(f"no trained adapters found under {adapter_dir}")

    arms: dict[str, float] = {}
    arms["base"] = _score_arm(tasks, model, None, None, system_prompt)
    arms["docs"] = _score_arm(tasks, model, None, docs_block, system_prompt)
    for path in adapter_paths:
        arms[f"adapter:{path.parent.name}"] = _score_arm(tasks, model, path, None, system_prompt)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_report(arms, adapter_keys=[f"adapter:{p.parent.name}" for p in adapter_paths], path=output_dir / "REPORT.md")
    click.echo(f"Wrote REPORT.md to {output_dir / 'REPORT.md'}")


def _score_arm(tasks: list[dict], model: str, adapter_path: Path | None, docs: str | None, system_prompt: str) -> float:
    """Score one arm (one loaded model + tokenizer) over the benchmark."""
    model_loaded, tokenizer = _load_model(model, adapter_path)
    completions = [
        generate(task["prompt"], model=model_loaded, tokenizer=tokenizer, docs=docs, system_prompt=system_prompt)
        for task in tasks
    ]
    return score_results(completions, tasks)["summary"]["score"]


def _load_jsonl_tasks(path: Path) -> list[dict]:
    """Read benchmark tasks from a JSONL file."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _reference_targets(results_dir: Path) -> dict[str, float]:
    """Return each seed adapter's reference score keyed by its seed suffix."""
    targets = {}
    for path in sorted(results_dir.glob("eval-v2-runA-seed*.json")):
        match = re.fullmatch(r"eval-v2-runA-seed(\d+)", path.stem)
        if not match:
            continue
        targets[match.group(1)] = json.loads(path.read_text())["summary"]["score"]
    return targets


def _adapter_tiers(adapter_dir: Path, model: str, targets: dict[str, float]) -> list[_Tier]:
    """Return one tier per adapter directory that has a reference target."""
    if not adapter_dir.is_dir():
        return []
    tiers = []
    for adapter in sorted(adapter_dir.iterdir()):
        if not adapter.is_dir():
            continue
        match = re.search(r"seed(\d+)$", adapter.name)
        if match and match.group(1) in targets:
            tiers.append(_Tier(f"adapter-{adapter.name}", targets[match.group(1)], model, adapter_path=adapter))
    return tiers


def _render_report(model: str, adapter_dir: Path, report: dict) -> str:
    """Render the reproduction report as markdown."""
    lines = [
        "# Reproduction summary",
        "",
        f"- model: {model}",
        f"- adapters: {adapter_dir}",
        "",
        "| tier | target | actual | verdict |",
        "| --- | --- | --- | --- |",
    ]
    for tier in report["tiers"]:
        verdict = "PASS" if tier["passed"] else "FAIL"
        lines.append(f"| {tier['tier']} | {_describe_target(tier['target'])} | {tier['actual']} | {verdict} |")
    if report["warnings"]:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    return "\n".join(lines)


@click.command("reproduce")
@click.option(
    "--model",
    default=_DEFAULT_MODEL,
    show_default=True,
    help="Base model to reproduce.",
)
@click.option(
    "--adapter-dir",
    type=click.Path(path_type=Path),
    default=str(_SPIKE_ROOT / ".cache" / "adapters"),
    show_default=True,
    help="Directory of LoRA adapters to reproduce.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    default="reports",
    show_default=True,
    help="Directory to write the reproduction summary into.",
)
def reproduce_cmd(model: str, adapter_dir: Path, output_dir: Path) -> None:
    """Reproduce the reference scores across the base, docs, and adapter tiers."""
    tasks = _load_jsonl_tasks(_SPIKE_ROOT / "benchmark" / "ood-v2" / "tasks.jsonl")
    docs_block = (_SPIKE_ROOT / "benchmark" / "pep750-docs-context-v3.md").read_text()
    system_prompt = (_SPIKE_ROOT / "benchmark" / "system-prompt.txt").read_text()

    targets = _reference_targets(_SPIKE_ROOT / "results")
    adapter_tiers = _adapter_tiers(adapter_dir, model, targets)
    if not adapter_tiers:
        raise click.ClickException(
            f"no adapter tiers found under {adapter_dir}; provision the adapters first (see docs/reproduction.md)"
        )
    tiers = [
        _Tier("base", 0.05, model),
        _Tier("docs", 0.61, model, docs=True),
        *adapter_tiers,
    ]
    report = reproduce(tasks, tiers, system_prompt=system_prompt, docs_block=docs_block)

    for tier in report["tiers"]:
        verdict = "PASS" if tier["passed"] else "FAIL"
        click.echo(f"{tier['tier']}: actual {tier['actual']} vs target {_describe_target(tier['target'])} ({verdict})")
    for warning in report["warnings"]:
        click.echo(f"warning: {warning}")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reproduction.md").write_text(_render_report(model, adapter_dir, report))


def evaluate_arms(
    benchmark: list[dict],
    *,
    system_prompt: str,
    docs_block: str,
    adapter_paths: list[Path],
    generate_fn: Callable,
    score_fn: Callable,
) -> dict[str, float]:
    """Score every arm (base, docs, adapters) with the same harness."""
    arms: dict[str, float] = {}
    prompts = [t["prompt"] for t in benchmark]

    base_completions = [generate_fn(p, system_prompt=system_prompt, docs=None, adapter_path=None) for p in prompts]
    arms["base"] = score_fn(base_completions, benchmark)["summary"]["score"]

    docs_completions = [
        generate_fn(p, system_prompt=system_prompt, docs=docs_block, adapter_path=None) for p in prompts
    ]
    arms["docs"] = score_fn(docs_completions, benchmark)["summary"]["score"]

    for path in adapter_paths:
        adapter_completions = [
            generate_fn(p, system_prompt=system_prompt, docs=None, adapter_path=path) for p in prompts
        ]
        arms[f"adapter:{path.name}"] = score_fn(adapter_completions, benchmark)["summary"]["score"]
    return arms


def write_report(arms: dict[str, float], *, adapter_keys: list[str], path: Path) -> None:
    """Write REPORT.md applying the preregistered decision rule."""
    docs_score = arms["docs"]
    adapter_scores = [arms[k] for k in adapter_keys]
    mean = sum(adapter_scores) / len(adapter_scores)
    lo, hi = min(adapter_scores), max(adapter_scores)
    positive = mean > docs_score
    verdict = "decision rule met — POSITIVE" if positive else "decision rule not met — NEGATIVE"

    lines = [
        "# REPORT — t-strings fine-tuning experiment",
        "",
        f"## Verdict: {verdict}",
        "",
        f"- Adapter mean `summary.score`: {mean:.3f}",
        f"- Adapter spread: {lo:.3f}-{hi:.3f}",
        f"- Docs-in-context `summary.score` (the bar): {docs_score:.3f}",
        f"- Bare base `summary.score`: {arms['base']:.3f}",
        "",
        "## Per-arm scores",
        "",
    ]
    for key, value in arms.items():
        lines.append(f"- `{key}`: {value:.3f}")
    lines.append("")
    lines.append("A negative result is a valid outcome and is reported as such.")
    path.write_text("\n".join(lines))
