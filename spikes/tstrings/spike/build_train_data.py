"""Spike: corpus rows -> mlx-lm training data (chat format, varied prompts).

Prompts are rendered per-property in the same style as the benchmark
(framing variety is the B-HEADER counter). Negative-control rows are
excluded from run 1 (they teach f-string output, which the benchmark's
policy stage rejects on t-string tasks).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FRAMINGS = [
    "Using Python 3.14 t-strings (PEP 750), write a complete program that",
    "PEP 750 question: write Python code that",
    "Write a Python 3.14 program using template strings that",
]


def classify(reference: str) -> str:
    if "getattr(template, 'strings')" in reference or "getattr(template, \"strings\")" in reference:
        return "introspect"
    if ".values" in reference:
        return "values"
    if "convert" in reference and "import convert" in reference:
        return "convert"
    if "Interpolation(" in reference:
        return "interpolation"
    if "t1 + t2" in reference:
        return "transform"
    if "join(template.strings)" in reference or "result = str(" in reference:
        return "render"
    if "result = f" in reference or "result = f'" in reference:
        return "negative"
    return "other"


def template_and_bindings(reference: str) -> tuple[str | None, list[tuple[str, str]]]:
    m = re.search(r"\bt([rbfu]*['\"]).*?\1", reference, re.DOTALL)
    template = m.group(0) if m else None
    bindings = re.findall(r"^(\w+) = (.*)$", reference, re.MULTILINE)
    return template, bindings


def render_prompt(prop: str, template: str | None, bindings: list[tuple[str, str]], framing: str) -> str:
    given = ", ".join(f"`{n} = {v}`" for n, v in bindings if n not in ("template", "result"))
    given_clause = f" given {given}" if given else " with no interpolated values"
    if template is None:
        template_clause = "the template value"
    else:
        template_clause = f"the template `{template}`"

    if prop in ("introspect", "values"):
        attr = "static string parts" if prop == "introspect" else "interpolated values"
        return f"{framing} compute the {attr} of {template_clause}{given_clause}."
    if prop == "render":
        return (
            f"{framing} join the static string parts of {template_clause} "
            f"with an empty string{given_clause}."
        )
    if prop == "convert":
        return (f"{framing} apply a `!r` conversion to the value `'hello'` using "
                "`string.templatelib.convert` and store the result.")
    if prop == "interpolation":
        return (f"{framing} build an `Interpolation` value with value `'hello'`, "
                "expression `'name'`, no conversion, and raw text `'Hi '`.")
    if prop == "transform":
        return (
            f"{framing} concatenate two template values with `+`{given_clause} "
            "and compute the static string parts of the result."
        )
    return f"{framing} evaluate {template_clause}{given_clause}."


def build() -> None:
    snap = json.loads(Path("corpus/tstrings.jsonl").read_text(encoding="utf-8"))
    tasks = snap["tasks"]
    print(f"{len(tasks)} corpus rows")

    train: list[dict] = []
    seen: set[str] = set()
    prop_counts: dict[str, int] = {}
    for i, task in enumerate(tasks):
        prop = classify(task["reference"])
        if prop == "negative":
            continue  # excluded from run 1
        if prop == "other":
            continue
        prop_counts[prop] = prop_counts.get(prop, 0) + 1
        template, bindings = template_and_bindings(task["reference"])
        for f in FRAMINGS:
            prompt = render_prompt(prop, template, bindings, f) + (
                " Assign the result to a variable named `result`."
            )
            answer = f"```python\n{task['reference']}\n```"
            train.append(
                {
                    "messages": [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": answer},
                    ]
                }
            )

    # -- Retired augmentation ------------------------------------------------
    # Curated literal/binding combos across the missing shapes. Each combo
    # gets a values row, a str() render row, and (for relevant shapes) a
    # format/conversion/interpolation row.
    def ref_for(kind: str, literal: str, bindings) -> str:
        lines = "\n".join(f"{n} = {v}" for n, v in bindings)
        pre = f"{lines}\n" if lines else ""
        if kind == "values":
            return f"{pre}result = {literal}.values"
        if kind == "render":
            return f"{pre}result = str({literal})"
        if kind == "format":
            return f"{pre}result = str({literal})"
        if kind == "conv":
            return f"{pre}result = str({literal})"
        if kind == "interp-value":
            return f"{pre}result = {literal}.interpolations[0].value"
        if kind == "interp-expr":
            return f"{pre}result = {literal}.interpolations[0].expression"
        if kind == "interp-conv":
            return f"{pre}result = {literal}.interpolations[0].conversion"
        if kind == "interp-fmt":
            return f"{pre}result = {literal}.interpolations[0].format_spec"
        if kind == "iter":
            return f"{pre}result = list(iter({literal}))"
        if kind == "join":
            return f"{pre}result = ''.join({literal}.strings)"
        if kind == "xstr":
            return f"{pre}result = ({literal}).strings"
        if kind == "interp-ctor":
            return (
                "from string.templatelib import Interpolation\n"
                "result = Interpolation('Ada', 'user', None, 'Hi ').value"
            )
        raise ValueError(kind)

    AUG = [
        # (kind, prompt_body, literal, bindings)
        ("values", "compute the interpolated values of the template", "t'Val: {v:.2f}'", (("v", "3.14159"),)),
        ("render", "render the template to a plain string using str()", "t'Val: {v:.2f}'", (("v", "3.14159"),)),
        ("format", "compute the formatted form of the template", "t'Val: {v:.2f}'", (("v", "3.14159"),)),
        ("values", "compute the interpolated values of the template", "t'{v:{w}}'", (("v", "42"), ("w", "5"))),
        ("render", "render the template to a plain string using str()", "t'{v:{w}}'", (("v", "42"), ("w", "5"))),
        ("conv", "compute the repr-converted form of the template", "t'{v!r}'", (("v", "'s'"),)),
        ("render", "render the template to a plain string using str()", "t'{v!r}'", (("v", "'s'"),)),
        ("conv", "compute the converted form of the template", "t'{a!s}:{b!r}'", (("a", "3.5"), ("b", "'q'"))),
        ("interp-value", "extract the value of the first interpolation of the template", "t'x {v} y'", (("v", "1"),)),
        ("interp-expr", "extract the expression string of the first interpolation of the template", "t'x {v} y'", (("v", "1"),)),
        ("interp-conv", "extract the conversion of the first interpolation of the template", "t'{v!r}'", (("v", "1"),)),
        ("interp-fmt", "extract the format spec of the first interpolation of the template", "t'{v:.2f}'", (("v", "1"),)),
        ("iter", "iterate the template and collect its parts as a list", "t'abc {x} yz'", (("x", "1"),)),
        ("values", "compute the interpolated values of the template", "t'{x} and {y:.1f}'", (("x", "'a'"), ("y", "2.5"))),
        ("render", "render the template to a plain string using str()", "t'{{literal}} {x}'", (("x", "1"),)),
        ("render", "render the concatenation of two templates to a plain string", "t'Hello, ' + t'Ada'", ()),
        ("join", "join the static string parts of the template with an empty string", "t'Hello, {user}!'", (("user", "'Bob'"),)),
        ("join", "join the static string parts of the template with an empty string", "t'user={u}'", (("u", "'n'"),)),
        ("xstr", "compute the static string parts of the concatenation of two templates", "t'Hello, ' + t'Ada'", ()),
        ("xstr", "compute the static string parts of the concatenation of two templates", "t'x' + t'{y}'", (("y", "1"),)),
        ("interp-ctor", "build an Interpolation with value 'Ada', expression 'user', no conversion, raw 'Hi ' and check its value", "", ()),
        ("render", "render the template to a plain string using str()", "t'[{a}] {b}'", (("a", "'OK'"), ("b", "'done'"))),
        # v5: rebalance the categories v4 diluted (format/conv/xform/values)
        ("format", "compute the formatted form of the template", "t'{n:04d}'", (("n", "7"),)),
        ("format", "compute the formatted form of the template", "t'{x:.3f}'", (("x", "1.23456"),)),
        ("format", "compute the formatted form of the template", "t'({v:+.2f})'", (("v", "3.5"),)),
        ("conv", "compute the converted form of the template", "t'{v!a}'", (("v", "'s'"),)),
        ("conv", "compute the converted form of the template", "t'q={q!s}'", (("q", "9"),)),
        ("xstr", "compute the static string parts of the concatenation of two templates", "t'[' + t'OK' + t']'", ()),
        ("values", "compute the interpolated values of the template", "t'u={u} p={p}'", (("u", "'x'"), ("p", "3"))),
    ]
    # The former hand-authored augmentation bypassed SP5 approvals, provenance,
    # and final-data contamination checks. It is retained above only as audit
    # evidence and must never enter rebuilt training data.
    for kind, body, literal, bindings in ():
        given = ", ".join(f"`{n} = {v}`" for n, v in bindings)
        given_clause = f" given {given}" if given else ""
        for f in FRAMINGS:
            prompt = f"{f} {body} `{literal}`{given_clause}. Assign the result to a variable named `result`."
            ref = ref_for(kind, literal, bindings)
            train.append({"messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": f"```python\n{ref}\n```"},
            ]})
    print("retired augmentation rows: 0")

    # Validation split: first 16 examples (deterministic, distinct rows).
    valid = train[::7][:16]
    train_set = [x for x in train if x not in valid]

    _reject_benchmark_overlap(train)

    out = Path("train_data")
    out.mkdir(exist_ok=True)
    for name, rows in (("train", train_set), ("valid", valid)):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"train={len(train_set)} valid={len(valid)}")
    print("property mix:", prop_counts)
    for ex in train_set[:3]:
        print("---")
        print(ex["messages"][0]["content"][:120])
        print(ex["messages"][1]["content"][:60])


def _reject_benchmark_overlap(rows: list[dict]) -> None:
    """Fail closed when rendered training answers copy benchmark references."""
    references: set[str] = set()
    # `benchmark/` is gitignored, so a missing file is the fresh-checkout
    # default rather than a signal that the benchmark is irrelevant. Skipping
    # it would turn this guard fail-open exactly when it matters most.
    for path in (
        Path("benchmark/development/tasks.jsonl"),
        Path("benchmark/confirmatory/tasks.jsonl"),
        Path("benchmark/repair-v1/tasks.jsonl"),
    ):
        if not path.exists():
            raise RuntimeError(
                f"{path} is missing; rebuild the benchmarks before rendering "
                "training data so contamination can be checked"
            )
        tasks = [json.loads(line) for line in path.read_text().splitlines()]
        references.update(task["reference"].strip() for task in tasks)

    overlap = {
        row["messages"][1]["content"]
        .removeprefix("```python\n")
        .removesuffix("\n```")
        .strip()
        for row in rows
    } & references
    if overlap:
        raise RuntimeError(
            f"rendered training data contains {len(overlap)} benchmark reference overlap(s)"
        )


if __name__ == "__main__":
    build()
