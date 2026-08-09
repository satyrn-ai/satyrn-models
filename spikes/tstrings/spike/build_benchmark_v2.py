"""Build the repair-v1 PEP 750 benchmark with framing decoupled from capability.

The confirmatory benchmark in ``build_benchmark`` assigns framing with
``FRAMINGS[index % 3]`` while emitting its tasks in a fixed per-iteration
order.  Its standard loop emits six tasks per iteration, and six is congruent
to zero modulo three, so each of those operations is pinned to one wording;
the author loop's ``choice = i % 3`` is likewise a fixed bijection onto
framing.  Nine of the eleven operations are affected.  The exceptions are
``render_dynamic_format_spec`` and ``render_conversion_format``, whose loops
emit one task per index and so do cycle through all three framings — an
earlier draft of this module claimed the lock was universal, which it is not.
For the nine that are pinned, an operation score partly measures response to
one wording.

Here framing is an explicit axis instead of a function of position.  Each
capability is crossed with every framing and with two fresh constants, giving
14 x 3 x 2 = 84 tasks in which capability and framing are independent by
construction.  The older benchmarks are left untouched as historical evidence.

Like its predecessor this artifact is *pending human review* until an
independent reviewer approves the frozen task list.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    TaskRecord,
)

FRAMINGS = (
    "Using Python 3.14 t-strings (PEP 750), write a complete program that",
    "PEP 750 question: write Python code that",
    "Write a Python 3.14 program using template strings that",
)

FRAMING_IDS = ("direct", "pep750-request", "python-program")

VARIANTS_PER_CELL = 2

RENDER_EXPRESSION = (
    "''.join(part if isinstance(part, str) else "
    "format(convert(part.value, part.conversion), part.format_spec) "
    "for part in template)"
)


@dataclass(frozen=True)
class Cell:
    """One capability under test, independent of framing and constants."""

    capability: str
    role: str
    operation: str
    family: str
    build: Callable[[str, int], tuple[str, str, str]]
    """``(token, number) -> (body, bindings, reference)``."""


def _render_reference(bindings: str, literal: str) -> str:
    return (
        "from string.templatelib import convert\n"
        f"{bindings}\n"
        f"template = {literal}\n"
        f"result = {RENDER_EXPRESSION}"
    )


def _author_renderer_reference(bindings: str, literal: str) -> str:
    return (
        "from string.templatelib import Interpolation, Template, convert\n\n"
        "def render_template(template: Template) -> str:\n"
        "    parts: list[str] = []\n"
        "    for part in template:\n"
        "        if isinstance(part, str):\n"
        "            parts.append(part)\n"
        "        elif isinstance(part, Interpolation):\n"
        "            converted = convert(part.value, part.conversion)\n"
        "            parts.append(\n"
        "                format(converted, part.format_spec)\n"
        "            )\n"
        "    return ''.join(parts)\n\n"
        f"{bindings}\n"
        f"result = render_template({literal})"
    )


def _strings(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-value"
    literal = f"t'head-{token}: {{value}}'"
    return (
        f"return the static parts of `{literal}`.",
        f"value = {value!r}",
        f"value = {value!r}\nresult = {literal}.strings",
    )


def _values(token: str, number: int) -> tuple[str, str, str]:
    left, right = f"{token}-left", f"{token}-right"
    literal = f"t'{{left}}/{number}/{{right}}'"
    return (
        f"return the interpolated values of `{literal}`.",
        f"left = {left!r}\nright = {right!r}",
        f"left = {left!r}\nright = {right!r}\nresult = {literal}.values",
    )


def _interpolation_field(field: str) -> Callable[[str, int], tuple[str, str, str]]:
    def build(token: str, number: int) -> tuple[str, str, str]:
        amount = f"{token}-amount"
        literal = "t'amount={amount!r:>8}'"
        return (
            f"extract the `{field}` field from the first interpolation of `{literal}`.",
            f"amount = {amount!r}",
            f"amount = {amount!r}\nresult = {literal}.interpolations[0].{field}",
        )

    return build


def _join_static(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-value"
    literal = f"t'left-{token}: {{value}} :right'"
    return (
        f"join only the static parts of `{literal}`. This is intentionally not "
        "full rendering.",
        f"value = {value!r}",
        f"value = {value!r}\nresult = ''.join({literal}.strings)",
    )


def _render_basic(token: str, number: int) -> tuple[str, str, str]:
    literal = f"t'item-{token}= {{number:04d}}'"
    bindings = f"number = {number}"
    return (
        f"fully render `{literal}` with f-string-equivalent template semantics. "
        "Use an explicit template-processing loop; `str(template)` is not "
        "rendering.",
        bindings,
        _render_reference(bindings, literal),
    )


def _render_dynamic_spec(token: str, number: int) -> tuple[str, str, str]:
    precision = number % 3 + 1
    literal = "t'pi={number:.{precision}f}'"
    bindings = f"number = {number + 0.375}\nprecision = {precision}"
    return (
        f"fully render `{literal}` using its dynamic format specification.",
        bindings,
        _render_reference(bindings, literal),
    )


def _render_conversion(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-repr"
    literal = "t'value={value!r:>18}'"
    bindings = f"value = {value!r}"
    return (
        f"fully render `{literal}`, applying conversion before the format "
        "specification.",
        bindings,
        _render_reference(bindings, literal),
    )


def _compose(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-value"
    literal = f"t'left-{token}: ' + t'{{value}}'"
    return (
        f"compose `{literal}`, then return the resulting Template's static parts.",
        f"value = {value!r}",
        f"value = {value!r}\nresult = ({literal}).strings",
    )


def _author_strings(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-author"
    literal = f"t'author-{token}: {{value}}'"
    return (
        "define a typed `static_parts(template: Template) -> tuple[str, ...]` "
        f"template function, then call it for `{literal}`.",
        f"value = {value!r}",
        "from string.templatelib import Template\n\n"
        "def static_parts(template: Template) -> tuple[str, ...]:\n"
        "    return template.strings\n\n"
        f"value = {value!r}\nresult = static_parts({literal})",
    )


def _author_values(token: str, number: int) -> tuple[str, str, str]:
    value = f"{token}-author"
    literal = f"t'author-{token}: {{value}}'"
    return (
        "define a typed `values_of(template: Template) -> tuple[object, ...]` "
        f"template function, then call it for `{literal}`.",
        f"value = {value!r}",
        "from string.templatelib import Template\n\n"
        "def values_of(template: Template) -> tuple[object, ...]:\n"
        "    return template.values\n\n"
        f"value = {value!r}\nresult = values_of({literal})",
    )


def _author_render(token: str, number: int) -> tuple[str, str, str]:
    literal = "t'author-render={number:04d}'"
    bindings = f"number = {number}"
    return (
        "define a typed `render_template(template: Template) -> str` template "
        f"function using `if isinstance`, then call it for `{literal}`.",
        bindings,
        _author_renderer_reference(bindings, literal),
    )


CELLS: tuple[Cell, ...] = (
    Cell("strings", "consumer", "strings", "static-parts", _strings),
    Cell("values", "consumer", "values", "interpolated-values", _values),
    *(
        Cell(
            f"interpolation_{field}",
            "consumer",
            "interpolation_fields",
            f"interpolation-{field}",
            _interpolation_field(field),
        )
        for field in ("value", "expression", "conversion", "format_spec")
    ),
    Cell(
        "join_static",
        "consumer",
        "join_static_parts",
        "intentional-static-join",
        _join_static,
    ),
    Cell(
        "render_basic",
        "consumer",
        "render_template",
        "basic-format-render",
        _render_basic,
    ),
    Cell(
        "render_dynamic_spec",
        "consumer",
        "render_dynamic_format_spec",
        "dynamic-format-spec",
        _render_dynamic_spec,
    ),
    Cell(
        "render_conversion",
        "consumer",
        "render_conversion_format",
        "conversion-then-format",
        _render_conversion,
    ),
    Cell(
        "compose",
        "consumer",
        "compose_templates",
        "composition-then-inspection",
        _compose,
    ),
    Cell(
        "author_strings",
        "author",
        "author_static_parts_function",
        "typed-if-isinstance-authoring",
        _author_strings,
    ),
    Cell(
        "author_values",
        "author",
        "author_values_function",
        "typed-if-isinstance-authoring",
        _author_values,
    ),
    Cell(
        "author_render",
        "author",
        "author_render_template_function",
        "typed-if-isinstance-authoring",
        _author_render,
    ),
)


def _task(
    cell: Cell,
    framing_index: int,
    variant: int,
    serial: int,
) -> tuple[TaskRecord, dict[str, str]]:
    """Create one task whose framing is chosen independently of its capability."""
    token = f"r1-{cell.capability}-{FRAMING_IDS[framing_index]}-{variant}"
    number = serial * 7 + 3
    body, bindings, reference = cell.build(token, number)
    prompt = (
        f"{FRAMINGS[framing_index]} {body}\n\n"
        "Copy these input bindings exactly before using the template:\n"
        f"```python\n{bindings}\n```\n\n"
        "Assign the requested answer to module-level variable `result`."
    )
    task = TaskRecord(
        prompt=prompt,
        reference=reference,
        checks=(NameEquals(name="result"),),
        policy=PolicyRef(
            id="tstring",
            version=1,
            config={
                "requires_template": True,
                "templatelib_apis": ["strings", "values"],
            },
        ),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="spike-benchmark-repair",
            generator_version="1.0.0",
            seed_id=f"repair-v1-{serial}",
        ),
    )
    return task, {
        "task_id": task.id,
        "capability": cell.capability,
        "operation": cell.operation,
        "role": cell.role,
        "family": cell.family,
        "framing": FRAMING_IDS[framing_index],
        "variant": str(variant),
        "review_status": "needs_human_review",
    }


def build_repair_v1() -> tuple[list[TaskRecord], list[dict[str, str]]]:
    """Cross every capability with every framing and two fresh constants."""
    tasks: list[TaskRecord] = []
    manifest: list[dict[str, str]] = []
    serial = 0
    for cell in CELLS:
        for framing_index in range(len(FRAMINGS)):
            for variant in range(VARIANTS_PER_CELL):
                task, entry = _task(cell, framing_index, variant, serial)
                tasks.append(task)
                manifest.append(entry)
                serial += 1
    return tasks, manifest


def _write(path: Path, tasks: list[TaskRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for task in tasks:
            stream.write(json.dumps(task.to_dict(), sort_keys=True) + "\n")


if __name__ == "__main__":
    repair, repair_manifest = build_repair_v1()
    out = Path("benchmark/repair-v1")
    _write(out / "tasks.jsonl", repair)
    (out / "manifest.json").write_text(
        json.dumps(repair_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fingerprint = hashlib.sha256((out / "tasks.jsonl").read_bytes()).hexdigest()
    (out / "fingerprint.txt").write_text(fingerprint + "\n", encoding="utf-8")
    print(f"repair-v1 tasks: {len(repair)} ({fingerprint[:12]})")
