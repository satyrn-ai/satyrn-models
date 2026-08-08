"""Spike: generalization probe — harder t-string tasks beyond corpus patterns.

These measure whether fine-tuning teaches general t-string ability or just
the corpus's pattern shapes. Reported separately from the main benchmark.
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
            generator="spike-probe",
            generator_version="0.1.0",
            seed_id=f"probe-{i}",
        ),
    )


def build() -> list[TaskRecord]:
    tasks: list[TaskRecord] = []
    f = FRAMINGS
    cases = [
        # format-spec interpolation (t'{v:{w}}') — corpus has the literal but
        # never renders it.
        ("compute the rendered form of `t'{v:{w}}'` given `v = 42` and `w = 5`",
         "v = 42\nw = 5\nresult = str(t'{v:{w}}')"),
        ("compute the values of `t'{v:{w}}'` given `v = 42` and `w = 5`",
         "v = 42\nw = 5\nresult = t'{v:{w}}'.values"),
        # escaped braces
        ("render `t'{{literal}} {x}'` given `x = 1`",
         "x = 1\nresult = str(t'{{literal}} {x}')"),
        # template iteration
        ("iterate the template `t'abc {x} yz'` given `x = 1` and collect the parts",
         "x = 1\nresult = list(iter(t'abc {x} yz'))"),
        # multiline template
        ("compute the static parts of the multiline template `t'''a\\nb'''`",
         "result = t'''a\nb'''.strings"),
        # interpolation conversion field
        ("extract the conversion of the first interpolation of `t'{v!r}'` given `v = 1`",
         "v = 1\nresult = t'{v!r}'.interpolations[0].conversion"),
        # interpolation format_spec field
        ("extract the format spec of the first interpolation of `t'{v:.2f}'` given `v = 1`",
         "v = 1\nresult = t'{v:.2f}'.interpolations[0].format_spec"),
        # str() + template concatenation
        ("render the concatenation `t'Hello, ' + t'Ada'` to a plain string",
         "result = str(t'Hello, ' + t'Ada')"),
        # values with a format spec
        ("compute the interpolated values of `t'{x} and {y:.1f}'` given `x = 'a'` and `y = 2.5`",
         "x = 'a'\ny = 2.5\nresult = t'{x} and {y:.1f}'.values"),
        # conversion in a format-spec position
        ("compute the values of `t'{v!r}'` given `v = 'q'`",
         "v = 'q'\nresult = t'{v!r}'.values"),
        # Template from string.templatelib import
        ("build a Template from the parts `('Hello, ',)` and check its rendered form",
         "from string.templatelib import Template\nresult = str(Template('Hello, '))"),
        # index-based interpolation
        ("compute the rendered form of `t'{0} + {1} = {0 + 1}'`",
         "result = str(t'{0} + {1} = {0 + 1}')"),
    ]
    for i, (body, ref) in enumerate(cases):
        tasks.append(_task(i, f[i % len(f)], body, ref))
    return tasks


if __name__ == "__main__":
    tasks = build()
    out = Path("benchmark")
    out.mkdir(exist_ok=True)
    with (out / "probe.jsonl").open("w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t.to_dict(), sort_keys=True) + "\n")
    print(f"{len(tasks)} probe tasks written")
