"""Build reviewed PEP 750 development and confirmatory benchmarks.

The old 100-task benchmark was a parameter sweep over five consumer patterns.
Some prompts omitted bindings used by their references, and it had no
template-function authoring coverage.  This builder makes every binding part
of the prompt and records operation, role, family, and review state in the
manifest.  The resulting confirmatory artifact remains *pending human review*
until an independent reviewer approves the frozen task list.
"""

from __future__ import annotations

import hashlib
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

FRAMINGS = (
    "Using Python 3.14 t-strings (PEP 750), write a complete program that",
    "PEP 750 question: write Python code that",
    "Write a Python 3.14 program using template strings that",
)

RENDER_EXPRESSION = (
    "''.join(part if isinstance(part, str) else "
    "format(convert(part.value, part.conversion), part.format_spec) "
    "for part in template)"
)


def _task(
    index: int,
    *,
    operation: str,
    role: str,
    family: str,
    body: str,
    bindings: str,
    reference: str,
) -> tuple[TaskRecord, dict[str, str]]:
    """Create one fully specified task and its review manifest entry."""
    prompt = (
        f"{FRAMINGS[index % len(FRAMINGS)]} {body}\n\n"
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
            generator="spike-benchmark",
            generator_version="0.2.0",
            seed_id=f"benchmark-{index}",
        ),
    )
    return task, {
        "task_id": task.id,
        "operation": operation,
        "role": role,
        "family": family,
        "review_status": "needs_human_review",
    }


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


def _suite(
    *,
    start: int,
    label: str,
    standard_count: int,
    dynamic_count: int,
    conversion_count: int,
    author_count: int,
) -> tuple[list[TaskRecord], list[dict[str, str]]]:
    """Create a role-balanced suite with distinct, explicit bindings."""
    tasks: list[TaskRecord] = []
    manifest: list[dict[str, str]] = []
    index = start

    def add(**kwargs: str) -> None:
        nonlocal index
        task, entry = _task(index, **kwargs)
        tasks.append(task)
        manifest.append(entry)
        index += 1

    for i in range(standard_count):
        value = f"{label}-value-{i}"
        add(
            operation="strings",
            role="consumer",
            family="static-parts",
            body=f"return the static parts of `t'prefix-{label}-{i}: {{value}}'`.",
            bindings=f"value = {value!r}",
            reference=(
                f"value = {value!r}\nresult = t'prefix-{label}-{i}: {{value}}'.strings"
            ),
        )
        left, right = f"{label}-left-{i}", f"{label}-right-{i}"
        add(
            operation="values",
            role="consumer",
            family="interpolated-values",
            body=f"return the interpolated values of `t'{{left}}/{i}/{{right}}'`.",
            bindings=f"left = {left!r}\nright = {right!r}",
            reference=(
                f"left = {left!r}\nright = {right!r}\n"
                f"result = t'{{left}}/{i}/{{right}}'.values"
            ),
        )
        field = ("value", "expression", "conversion", "format_spec")[i % 4]
        literal = "t'amount={amount!r:>8}'"
        add(
            operation="interpolation_fields",
            role="consumer",
            family=f"interpolation-{field}",
            body=(
                f"extract the `{field}` field from the first interpolation of "
                f"`{literal}`."
            ),
            bindings=f"amount = {label + '-amount-' + str(i)!r}",
            reference=(
                f"amount = {label + '-amount-' + str(i)!r}\n"
                f"result = {literal}.interpolations[0].{field}"
            ),
        )
        add(
            operation="join_static_parts",
            role="consumer",
            family="intentional-static-join",
            body=(
                "join only the static parts of "
                f"`t'left-{label}-{i}: {{value}} :right'`. "
                "This is intentionally not full rendering."
            ),
            bindings=f"value = {value!r}",
            reference=(
                f"value = {value!r}\n"
                f"result = ''.join(t'left-{label}-{i}: {{value}} :right'.strings)"
            ),
        )
        number = i * 17 + 3
        literal = f"t'item-{label}-{i}= {{number:04d}}'"
        add(
            operation="render_template",
            role="consumer",
            family="basic-format-render",
            body=(
                f"fully render `{literal}` with f-string-equivalent template "
                "semantics. Use an explicit template-processing loop; "
                "`str(template)` is not rendering."
            ),
            bindings=f"number = {number}",
            reference=_render_reference(f"number = {number}", literal),
        )
        add(
            operation="compose_templates",
            role="consumer",
            family="composition-then-inspection",
            body=(
                f"compose `t'left-{label}-{i}: ' + t'{{value}}'`, then return the "
                "resulting Template's static parts."
            ),
            bindings=f"value = {value!r}",
            reference=(
                f"value = {value!r}\n"
                f"result = (t'left-{label}-{i}: ' + t'{{value}}').strings"
            ),
        )

    for i in range(dynamic_count):
        number, precision = i + 0.375, (i % 3) + 1
        literal = "t'pi={number:.{precision}f}'"
        add(
            operation="render_dynamic_format_spec",
            role="consumer",
            family="dynamic-format-spec",
            body=f"fully render `{literal}` using its dynamic format specification.",
            bindings=f"number = {number}\nprecision = {precision}",
            reference=_render_reference(
                f"number = {number}\nprecision = {precision}", literal
            ),
        )

    for i in range(conversion_count):
        value = f"{label}-repr-{i}"
        literal = "t'value={value!r:>18}'"
        add(
            operation="render_conversion_format",
            role="consumer",
            family="conversion-then-format",
            body=(
                f"fully render `{literal}`, applying conversion before the format "
                "specification."
            ),
            bindings=f"value = {value!r}",
            reference=_render_reference(f"value = {value!r}", literal),
        )

    for i in range(author_count):
        value = f"{label}-author-{i}"
        choice = i % 3
        if choice == 0:
            literal = f"t'author-{label}-{i}: {{value}}'"
            add(
                operation="author_static_parts_function",
                role="author",
                family="typed-if-isinstance-authoring",
                body=(
                    "define a typed "
                    "`static_parts(template: Template) -> tuple[str, ...]` "
                    f"template function, then call it for `{literal}`."
                ),
                bindings=f"value = {value!r}",
                reference=(
                    "from string.templatelib import Template\n\n"
                    "def static_parts(template: Template) -> tuple[str, ...]:\n"
                    "    return template.strings\n\n"
                    f"value = {value!r}\nresult = static_parts({literal})"
                ),
            )
        elif choice == 1:
            literal = f"t'author-{label}-{i}: {{value}}'"
            add(
                operation="author_values_function",
                role="author",
                family="typed-if-isinstance-authoring",
                body=(
                    "define a typed "
                    "`values_of(template: Template) -> tuple[object, ...]` "
                    f"template function, then call it for `{literal}`."
                ),
                bindings=f"value = {value!r}",
                reference=(
                    "from string.templatelib import Template\n\n"
                    "def values_of(template: Template) -> tuple[object, ...]:\n"
                    "    return template.values\n\n"
                    f"value = {value!r}\nresult = values_of({literal})"
                ),
            )
        else:
            literal = "t'author-render={number:04d}'"
            number = i * 9 + 1
            add(
                operation="author_render_template_function",
                role="author",
                family="typed-if-isinstance-authoring",
                body=(
                    "define a typed `render_template(template: Template) -> str` "
                    "template function using `if isinstance`, then call it for "
                    f"`{literal}`."
                ),
                bindings=f"number = {number}",
                reference=_author_renderer_reference(f"number = {number}", literal),
            )
    return tasks, manifest


def build_development() -> tuple[list[TaskRecord], list[dict[str, str]]]:
    """Thirty disjoint tasks for prompt and corpus development."""
    return _suite(
        start=1_000,
        label="development",
        standard_count=3,
        dynamic_count=1,
        conversion_count=2,
        author_count=9,
    )


def build_confirmatory() -> tuple[list[TaskRecord], list[dict[str, str]]]:
    """One hundred disjoint tasks: 70 consumer and 30 authoring tasks."""
    return _suite(
        start=10_000,
        label="confirmatory",
        standard_count=10,
        dynamic_count=5,
        conversion_count=5,
        author_count=30,
    )


def _write(path: Path, tasks: list[TaskRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for task in tasks:
            stream.write(json.dumps(task.to_dict(), sort_keys=True) + "\n")


if __name__ == "__main__":
    development, development_manifest = build_development()
    confirmatory, confirmatory_manifest = build_confirmatory()
    out = Path("benchmark")
    _write(out / "development" / "tasks.jsonl", development)
    _write(out / "confirmatory" / "tasks.jsonl", confirmatory)
    (out / "development" / "manifest.json").write_text(
        json.dumps(development_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "confirmatory" / "manifest.json").write_text(
        json.dumps(confirmatory_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    fingerprint = hashlib.sha256(
        (out / "confirmatory" / "tasks.jsonl").read_bytes()
    ).hexdigest()
    (out / "confirmatory" / "fingerprint.txt").write_text(
        fingerprint + "\n", encoding="utf-8"
    )
    print(f"development tasks: {len(development)}")
    print(f"confirmatory tasks: {len(confirmatory)} ({fingerprint[:12]})")
