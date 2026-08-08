"""Spike: fresh held-out eval set (eval-2), authored blind to v4 training.

Distinct literals/operations from both the main benchmark and the probe;
written before v4 results exist to avoid test-set fitting via iteration.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    TaskRecord,
)

FRAMINGS = [
    "Using Python 3.14 t-strings (PEP 750), write a complete program that",
    "PEP 750 question: write Python code that",
    "Write a Python 3.14 program using template strings that",
]


def _task(i: int, framing: str, body: str, reference: str) -> TaskRecord:
    return TaskRecord(
        prompt=f"{framing} {body} Assign the result to a variable named `result`.",
        reference=reference,
        checks=(NameEquals(name="result"),),
        policy=PolicyRef(
            id="tstring",
            version=1,
            config={"requires_template": True, "templatelib_apis": ["strings", "values", "interpolations"]},
        ),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="spike-eval2",
            generator_version="0.1.0",
            seed_id=f"eval2-{i}",
        ),
    )


def build() -> list[TaskRecord]:
    tasks: list[TaskRecord] = []
    f = FRAMINGS
    cases = [
        # strings
        ("compute the static string parts of `t'Hello, {who}!'` given `who = 'Zed'`",
         "who = 'Zed'\nresult = t'Hello, {who}!'.strings"),
        ("compute the static string parts of `t'a{b}c{d}'` given `b = 1` and `d = 2`",
         "b = 1\nd = 2\nresult = t'a{b}c{d}'.strings"),
        # values
        ("compute the interpolated values of `t'u={u} p={p}'` given `u = 'x'` and `p = 3`",
         "u = 'x'\np = 3\nresult = t'u={u} p={p}'.values"),
        # render (str)
        ("render `t'Status: {code}'` to a plain string given `code = 404`",
         "code = 404\nresult = str(t'Status: {code}')"),
        ("render `t'[{a}] {b}'` to a plain string given `a = 'OK'` and `b = 'done'`",
         "a = 'OK'\nb = 'done'\nresult = str(t'[{a}] {b}')"),
        # join
        ("join the static parts of `t'user={u}'` with an empty string given `u = 'n'`",
         "u = 'n'\nresult = ''.join(t'user={u}'.strings)"),
        # format
        ("compute the formatted form of `t'{n:04d}'` given `n = 7`",
         "n = 7\nresult = str(t'{n:04d}')"),
        ("compute the rendered form of `t'{x:.3f}'` given `x = 1.23456`",
         "x = 1.23456\nresult = str(t'{x:.3f}')"),
        # conversion
        ("compute the converted form of `t'{v!s}'` given `v = 9`",
         "v = 9\nresult = str(t'{v!s}')"),
        # interpolation fields
        ("extract the expression of the first interpolation of `t'{q}'` given `q = 1`",
         "q = 1\nresult = t'{q}'.interpolations[0].expression"),
        ("extract the value of the first interpolation of `t'k={k}'` given `k = 'v'`",
         "k = 'v'\nresult = t'k={k}'.interpolations[0].value"),
        # xform
        ("compute the static parts of `t'a' + t'b'`",
         "result = (t'a' + t'b').strings"),
        ("compute the static parts of `t'x' + t'{y}'` given `y = 1`",
         "y = 1\nresult = (t'x' + t'{y}').strings"),
        # iteration
        ("collect the parts of `t'{a}-{b}'` given `a = 1` and `b = 2` via iteration",
         "a = 1\nb = 2\nresult = list(iter(t'{a}-{b}'))"),
        # multiline
        (
            "compute the static parts of the multiline template with a line break",
            "result = t'''one\\ntwo'''.strings",
        ),
    ]
    for i, (body, ref) in enumerate(cases):
        tasks.append(_task(i, f[i % len(f)], body, ref))
    return tasks


if __name__ == "__main__":
    tasks = build()
    out = Path("benchmark")
    out.mkdir(exist_ok=True)
    with (out / "eval2.jsonl").open("w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t.to_dict(), sort_keys=True) + "\n")
    print(f"{len(tasks)} eval2 tasks written")
