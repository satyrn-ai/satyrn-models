"""Property-based scoring for `ood-v1`, replacing exact match.

`ood-v1` grades with `name_equals`: the answer must compare equal to whatever
the hidden reference produced. Essentially every task requires reference string
literals its prompt never states — one asks to render a diagnostic "with the
supplied credentials" and supplies none, while the reference invents `riley`,
`swordfish` and `***`. Exact match therefore measures literal-guessing, and a
model with perfect t-string skill still fails.

Two later attempts were also wrong, in instructive ways:

- Scoring "is the answer a `str`" mis-specified the 6 of 25 tasks whose
  references answer with a `tuple` or a `dict`, filing correct structured
  answers as failures.
- Scoring type alone then ranked the **bare model first at 17/25** — while it
  used a t-string in **zero** tasks. It was solving every task the old way with
  f-strings and string concatenation, which is precisely the behaviour this
  work exists to change. A metric that ignores mechanism rewards ignoring the
  feature.

So a task is scored on properties that are all checkable without knowing the
reference's private literals, and **mechanism and correctness must hold
together**:

``policy``   the program actually builds a `Template` (AST-level, not a regex)
``typed``    the answer's type equals the reference's own answer type
``literals`` every literal the *prompt* does state appears in the answer
``solved``   policy and typed and literals

`solved` is the headline. It is still necessary-not-sufficient — it cannot tell
rendered sense from rendered nonsense — but unlike its predecessors it cannot
be satisfied by avoiding t-strings altogether.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROBE = '''
import json, sys
source = json.loads(sys.argv[1])
name = json.loads(sys.argv[2])
namespace = {"__name__": "__main__"}
try:
    exec(compile(source, "<candidate>", "exec"), namespace)
except BaseException:
    pass
if name in namespace:
    value = namespace[name]
    print(json.dumps({"type": type(value).__name__, "repr": repr(value)[:600]}))
else:
    print(json.dumps({"type": None, "repr": None}))
'''


def evaluate(source: str, answer: str, timeout: int = 20) -> dict:
    """Execute a program and report the type and repr of its answer name.

    A late exception is tolerated on purpose: a program that binds the answer
    and then fails on some unrelated trailing statement has still demonstrated
    the property under test.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(PROBE)
        probe = handle.name
    try:
        done = subprocess.run(
            [sys.executable, probe, json.dumps(source), json.dumps(answer)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"type": None, "repr": None}
    finally:
        Path(probe).unlink(missing_ok=True)
    for line in reversed(done.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"type": None, "repr": None}


def builds_template(source: str) -> bool:
    """True when the program uses the feature at all.

    Structural rather than textual: `ast.TemplateStr` exists in 3.14, so a
    `t"..."` in a comment or inside an ordinary string cannot be mistaken for
    the real thing, and the check does not depend on quoting style.

    A t-string *literal* is not the only legitimate route. One `ood-v1` task
    asks for a `Template` assembled by hand from `Interpolation` objects, and a
    literal-only check scored the correct answer as a policy failure.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.TemplateStr)
        or (isinstance(node, ast.ImportFrom) and node.module == "string.templatelib")
        for node in ast.walk(tree)
    )


def prompt_literals(prompt: str) -> list[str]:
    """Quoted literals the prompt actually states, which an answer must carry.

    Only what is written down: this is the half of exact match that is fair to
    demand, and it says nothing about literals the task kept private.
    """
    found = re.findall(r"`([^`]{2,40})`", prompt)
    return [
        item
        for item in found
        if not item.startswith(("t'", 't"'))
        and "=" not in item
        and not item.isidentifier()
    ]


def score_task(
    task: dict, candidate: str, ref_type: str | None, exact: bool = False
) -> dict:
    answer = next(
        (c["name"] for c in task.get("checks", ()) if c.get("name")), "result"
    )
    observed = evaluate(candidate, answer)
    rendered = observed["repr"] or ""
    wanted = prompt_literals(task["prompt"])
    literals = all(item in rendered for item in wanted) if wanted else True
    policy = builds_template(candidate)
    typed = observed["type"] is not None and observed["type"] == ref_type
    # `literals` is RETIRED from the verdict and kept only as a diagnostic.
    # It was built for `ood-v1`, where prompts stated too little. On a
    # benchmark whose prompts state the template, the backticked spans it
    # extracts are the template *source* (`Weather in {city} today`) and API
    # names (`.strings`) -- neither of which appears in a rendered answer, by
    # design. It failed tasks that pass exact match outright, and gated
    # `solved` down to 0-3 of 100 across every arm.
    #
    # On a benchmark that states its literals, exact match is fair again, so
    # the verdict is exact match plus the mechanism check that stops a model
    # scoring by avoiding t-strings entirely.
    return {
        "id": task["id"][:12],
        "policy": policy,
        "typed": typed,
        "literals": literals,
        "solved": policy and exact,
        "observed_type": observed["type"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument(
        "--tasks", type=Path, default=Path("benchmark/ood-v1/tasks.jsonl")
    )
    parser.add_argument("--out", type=Path, default=Path("results/ood-properties.json"))
    args = parser.parse_args()

    tasks = {}
    for raw in args.tasks.read_text().splitlines():
        if raw.strip():
            task = json.loads(raw)
            tasks[task["id"]] = task

    ref_types = {}
    for task_id, task in tasks.items():
        answer = next(
            (c["name"] for c in task.get("checks", ()) if c.get("name")), "result"
        )
        ref_types[task_id] = evaluate(task["reference"], answer)["type"]

    reports = []
    for path in args.results:
        payload = json.loads(path.read_text())
        rows = payload["results"]
        scored = [
            score_task(
                tasks[row["id"]],
                row["candidate"],
                ref_types[row["id"]],
                exact=row["passed"],
            )
            for row in rows
        ]
        total = len(scored) or 1
        reports.append(
            {
                "tag": payload.get("tag", path.stem),
                "n": len(scored),
                "solved": sum(s["solved"] for s in scored),
                "solved_rate": round(sum(s["solved"] for s in scored) / total, 3),
                "policy": sum(s["policy"] for s in scored),
                "typed": sum(s["typed"] for s in scored),
                "literals": sum(s["literals"] for s in scored),
                "exact_match": sum(1 for row in rows if row["passed"]),
                "detail": scored,
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n")

    width = max(len(r["tag"]) for r in reports)
    print(
        f"{'arm':{width}}  {'SOLVED':>6}  {'policy':>6}  {'typed':>6}  "
        f"{'literals':>8}  {'exact':>5}"
    )
    for r in reports:
        print(
            f"{r['tag']:{width}}  {r['solved']:>6}  {r['policy']:>6}  "
            f"{r['typed']:>6}  {r['literals']:>8}  {r['exact_match']:>5}"
        )
    print(
        f"\nn={reports[0]['n']}. solved = policy AND exact. "
        "literals is a retired diagnostic, not part of the verdict."
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
