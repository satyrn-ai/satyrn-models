"""Re-score saved `ood-v1` runs on what the answer *is*, not what it equals.

`ood-v1` grades with `name_equals`: the answer variable must compare equal to
the value the reference program produces. That is unwinnable on this task set.
Of the 11 `semantic_check` failures on the best Mellum arm, **all 11** need
string literals that appear nowhere in the prompt, and **7 define and call a
correct-looking renderer**. One task asks to "render a login diagnostic ... with
the supplied credentials" and supplies none; the hidden reference invents
`riley`, `swordfish`, and `***` as the redaction marker. A model with perfect
rendering skill fails it.

So the exact-match score measures how well a model guesses unstated literals,
and the "11 semantic failures" were read as a rendering deficit when they are
mostly a benchmark defect.

This scores the answer's **type against the reference's own type**, computed by
executing each reference program. An earlier version of this module scored
"is it a `str`" instead, which was wrong for the 6 of 25 tasks whose references
answer with a `tuple` or a `dict`: a correct SQL answer of
``('SELECT ... $1 ...', (17, 'open'))`` was filed as a failure. That capped the
metric at 19 and mixed correct structured answers in with garbage.

An unrendered `Template` is still called out separately, since it is the
specific failure the corpus exists to prevent.

Both are computable from completions already on disk, so every recorded arm can
be re-scored without a GPU. Exact match is still reported, as the strict lower
bound it always was — on this benchmark it is only a lower bound, because
essentially every task needs reference literals its prompt never states.

**This metric is not sufficient.** It cannot tell rendered sense from rendered
nonsense, and it is blind to eager-evaluation errors — a candidate that
evaluates ``t"...{name}..."`` before binding ``name`` believes templates defer
evaluation, which is exactly the semantic gap this work targets, and it lands
in `raised` unattributed. Treat a type match as necessary, not sufficient.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Names that mean the candidate reached for the training corpus's renderer
# without bringing it along, as opposed to referencing a task input the prompt
# never supplied. The two look identical as `NameError` and have opposite
# causes: one is ours, one is the benchmark's.
# Two failures that both mention the corpus's vocabulary but mean different
# things. Calling a renderer that was never defined is the over-exposure
# symptom -- the model treats `render_template` as ambient because it saw one
# body hundreds of times. Using a `string.templatelib` name without importing
# it is an incomplete-preamble slip: the program defines its renderer correctly
# and then forgets an import. Scoring them together, as a first cut of this
# module did, reports a curriculum defect where there is only a missing line.
RENDERER_CALLS = frozenset({"render", "render_template"})
TEMPLATELIB_NAMES = frozenset({"Interpolation", "Template", "convert"})

# Runs inside a throwaway interpreter: execute the candidate, then report what
# the answer name holds. `Template` has no useful repr for comparison, so the
# classification happens in-process and only a verdict crosses the boundary.
PROBE = '''
import json, sys
from string.templatelib import Template

source = json.loads(sys.argv[1])
name = json.loads(sys.argv[2])
# Candidates that guard on `__name__` never ran their body without this, and
# were scored as failures for a reason unrelated to t-strings.
namespace = {"__name__": "__main__"}
try:
    exec(compile(source, "<candidate>", "exec"), namespace)
except BaseException as exc:
    # A late error after the answer is already bound is not the same as never
    # producing one; report both so the caller can tell them apart.
    if name in namespace:
        print(json.dumps({"kind": "late_error", "detail": type(exc).__name__,
                          "type": type(namespace[name]).__name__}))
    else:
        print(json.dumps({"kind": "raised", "detail": type(exc).__name__}))
    raise SystemExit(0)

if name not in namespace:
    print(json.dumps({"kind": "name_missing", "detail": name}))
    raise SystemExit(0)

value = namespace[name]
kind = "unrendered_template" if isinstance(value, Template) else "answered"
print(json.dumps({"kind": kind, "detail": type(value).__name__,
                  "type": type(value).__name__, "repr": repr(value)[:400]}))
'''

KINDS = (
    "answered",
    "unrendered_template",
    "late_error",
    "name_missing",
    "raised",
    "timeout",
)


def classify(source: str, answer_name: str, timeout: int = 15) -> dict:
    """Run one candidate and report what its answer variable holds."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(PROBE)
        probe = handle.name
    try:
        done = subprocess.run(
            [sys.executable, probe, json.dumps(source), json.dumps(answer_name)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"kind": "timeout", "detail": ""}
    finally:
        Path(probe).unlink(missing_ok=True)
    line = done.stdout.strip().splitlines()
    if not line:
        return {"kind": "raised", "detail": "no verdict"}
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError:
        # Candidate code that prints corrupts the verdict channel; the last
        # parseable line is the verdict, so scan backwards before giving up.
        for candidate in reversed(line):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return {"kind": "raised", "detail": "unparseable verdict"}


def undefined_names(source: str) -> set[str]:
    """Module-level names the candidate reads without ever binding.

    Deliberately crude — it ignores scoping and comprehension targets — but it
    only has to separate two populations that both surface as `NameError`, and
    it is applied identically to every arm.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    bound = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    bound |= {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    bound |= {
        alias.asname or alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            bound |= {arg.arg for arg in node.args.args}
    read = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return {name for name in read - bound if not hasattr(builtins, name)}


def blame(source: str) -> str | None:
    """Which defect a `NameError` is, most specific first."""
    undefined = undefined_names(source)
    if not undefined:
        return None
    if undefined & RENDERER_CALLS:
        return "undefined_renderer"
    if undefined & TEMPLATELIB_NAMES:
        return "missing_import"
    return "unbound_input"


def answer_names(tasks_path: Path) -> dict[str, str]:
    names = {}
    for raw in tasks_path.read_text().splitlines():
        if not raw.strip():
            continue
        task = json.loads(raw)
        for check in task.get("checks", ()):
            if check.get("name"):
                names[task["id"]] = check["name"]
                break
    return names


def reference_types(tasks_path: Path, names: dict[str, str]) -> dict[str, str]:
    """Execute each reference to learn the type its answer is supposed to be.

    Six of the 25 `ood-v1` references answer with a `tuple` or a `dict`, so a
    hardcoded "should be a str" scores correct structured answers as failures.
    """
    types: dict[str, str] = {}
    for raw in tasks_path.read_text().splitlines():
        if not raw.strip():
            continue
        task = json.loads(raw)
        verdict = classify(task["reference"], names.get(task["id"], "result"))
        types[task["id"]] = verdict.get("type") or ""
    return types


def rescore(
    result_path: Path, names: dict[str, str], ref_types: dict[str, str]
) -> dict:
    payload = json.loads(result_path.read_text())
    rows = payload["results"]
    counts = dict.fromkeys(KINDS, 0)
    fault = {"undefined_renderer": 0, "missing_import": 0, "unbound_input": 0}
    type_match = 0
    detail = []
    for row in rows:
        name = names.get(row["id"], "result")
        verdict = classify(row["candidate"], name)
        counts[verdict["kind"]] = counts.get(verdict["kind"], 0) + 1
        wanted = ref_types.get(row["id"])
        if wanted and verdict.get("type") == wanted and verdict["kind"] == "answered":
            type_match += 1
            verdict = verdict | {"type_match": True}
        if verdict["kind"] == "raised" and verdict.get("detail") == "NameError":
            which = blame(row["candidate"])
            if which:
                fault[which] += 1
                verdict = verdict | {"blame": which}
        detail.append({"id": row["id"][:12], "exact": row["passed"], **verdict})
    total = len(rows) or 1
    return {
        "tag": payload.get("tag", result_path.stem),
        "n": len(rows),
        "exact_match": sum(1 for row in rows if row["passed"]),
        # The headline: the answer is the same type the reference produces.
        # Necessary, not sufficient -- it cannot tell sense from nonsense.
        "type_match": type_match,
        "type_match_rate": round(type_match / total, 3),
        "unrendered_template": counts["unrendered_template"],
        # The metric worth training against: calling the corpus's renderer
        # without defining it is the documented symptom of over-exposing one
        # byte-identical body, and it is attributable to us rather than to the
        # benchmark's unstated inputs.
        "undefined_renderer": fault["undefined_renderer"],
        "missing_import": fault["missing_import"],
        "unbound_input": fault["unbound_input"],
        "counts": counts,
        "detail": detail,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument(
        "--tasks", type=Path, default=Path("benchmark/ood-v1/tasks.jsonl")
    )
    parser.add_argument("--out", type=Path, default=Path("results/ood-rescore.json"))
    args = parser.parse_args()

    names = answer_names(args.tasks)
    ref_types = reference_types(args.tasks, names)
    reports = [rescore(path, names, ref_types) for path in args.results]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n")

    width = max(len(r["tag"]) for r in reports)
    cols = ["type_match", "exact_match"] + list(KINDS) + [
        "undefined_renderer", "missing_import", "unbound_input",
    ]
    print(f"{'arm':{width}}" + "".join(f"{c[:11]:>13}" for c in cols))
    for r in reports:
        cells = []
        for c in cols:
            cells.append(r[c] if c in r else r["counts"].get(c, 0))
        print(f"{r['tag']:{width}}" + "".join(f"{v:>13}" for v in cells))
    print(
        "\ntype_match counts answers whose type equals the reference's own "
        "type;\nevery outcome category is printed -- an earlier table omitted "
        "three of them\nand silently dropped a quarter of each arm's tasks."
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
