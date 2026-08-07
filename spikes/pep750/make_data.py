"""Generate verified PEP 750 (template string) training data.

Every candidate example is executed on the current interpreter (Python 3.14+
required for t-strings) and only written to data/pep750.jsonl if it runs
cleanly. Examples are adapted from PEP 750 (https://peps.python.org/pep-0750/).

Usage:
  python make_data.py                    # validate all examples, write JSONL
  python make_data.py --validate-only    # validate all examples, no write
  python make_data.py --code "..."       # validate a single snippet
  python make_data.py -c "..." --label "my test"   # with a custom label
"""

import argparse
import json
import sys
from pathlib import Path

HEADER = "# Python 3.14 t-strings"

# (description, code) — code must be self-contained and run without error.
EXAMPLES: list[tuple[str, str]] = [
    (
        "create a template string and check its type",
        '''from string.templatelib import Template

name = "World"
template = t"Hello {name}"
assert isinstance(template, Template)''',
    ),
    (
        "access the static string parts and interpolations of a template",
        '''name = "World"
template = t"Hello {name}!"
assert template.strings == ("Hello ", "!")
assert len(template.interpolations) == 1''',
    ),
    (
        "read the evaluated value of an interpolation",
        '''name = "World"
template = t"Hello {name}"
assert template.interpolations[0].value == "World"''',
    ),
    (
        "read the source expression of an interpolation",
        '''name = "World"
template = t"Hello {name}"
assert template.interpolations[0].expression == "name"''',
    ),
    (
        "use a !r conversion in an interpolation",
        '''name = "World"
template = t"Hello {name!r}"
assert template.interpolations[0].conversion == "r"''',
    ),
    (
        "use a format spec in an interpolation",
        '''value = 42
template = t"Value: {value:.2f}"
assert template.interpolations[0].format_spec == ".2f"''',
    ),
    (
        "nest an interpolation inside a format spec",
        '''value = 42
precision = 2
template = t"Value: {value:.{precision}f}"
assert template.interpolations[0].format_spec == ".2f"''',
    ),
    (
        "iterate over the strings and interpolations of a template",
        '''name = "World"
template = t"Hello {name}!"
contents = list(template)
assert len(contents) == 3
assert contents[0] == "Hello "
assert contents[1].value == "World"
assert contents[2] == "!"''',
    ),
    (
        "note that adjacent interpolations leave empty strings in .strings",
        '''first = "Eat"
second = "Red Leicester"
template = t"{first}{second}"
assert template.strings == ("", "", "")
assert [i.value for i in template.interpolations] == ["Eat", "Red Leicester"]''',
    ),
    (
        "write a custom renderer that uppercases interpolations",
        '''from string.templatelib import Interpolation, Template

def lower_upper(template: Template) -> str:
    """Render static parts lowercased and interpolations uppercased."""
    parts: list[str] = []
    for item in template:
        if isinstance(item, Interpolation):
            parts.append(str(item.value).upper())
        else:
            parts.append(item.lower())
    return "".join(parts)

name = "world"
assert lower_upper(t"HELLO {name}") == "hello WORLD"''',
    ),
    (
        "concatenate two templates with +",
        '''from string.templatelib import Template

name = "World"
template = t"Hello " + t"{name}"
assert isinstance(template, Template)
assert template.strings == ("Hello ", "")
assert template.values[0] == "World"''',
    ),
    (
        "implicitly concatenate adjacent template literals",
        '''name = "World"
template = t"Hello " t"{name}"
assert template.strings == ("Hello ", "")
assert template.values[0] == "World"''',
    ),
    (
        "build a Template from a plain string or an Interpolation",
        '''from string.templatelib import Interpolation, Template

name = "World"
static = t"Hello " + Template(name)  # name becomes a static string part
dynamic = t"Hello " + Template(Interpolation(name, "name"))  # name is interpolated
assert static.strings == ("Hello World",)
assert dynamic.interpolations[0].value == "World"''',
    ),
    (
        "use the {name=} debug syntax in a template",
        '''name = "World"
template = t"Hello {name=}"
assert template.strings[0] == "Hello name="
assert template.interpolations[0].value == "World"
assert template.interpolations[0].conversion == "r"''',
    ),
    (
        "use a raw template string to keep backslashes literal",
        '''trade = "shrubberies"
template = rt'Did you say "{trade}"?\\n'
assert template.strings[0] == r'Did you say "'
assert template.strings[1] == r'"?\\n' ''',
    ),
    (
        "render a template like an f-string with a custom f() function",
        '''from string.templatelib import Interpolation, Template
from typing import Literal

def convert(value: object, conversion: Literal["a", "r", "s"] | None) -> object:
    if conversion == "a":
        return ascii(value)
    if conversion == "r":
        return repr(value)
    if conversion == "s":
        return str(value)
    return value

def f(template: Template) -> str:
    parts: list[str] = []
    for item in template:
        match item:
            case str() as s:
                parts.append(s)
            case Interpolation(value, _, conversion, format_spec):
                parts.append(format(convert(value, conversion), format_spec))
    return "".join(parts)

name = "World"
value = 42
assert f(t"Hello {name!r}, value: {value:.2f}") == "Hello 'World', value: 42.00"''',
    ),
    (
        "match interpolations by value type with structural pattern matching",
        '''from string.templatelib import Interpolation, Template

def describe(template: Template) -> list[str]:
    kinds: list[str] = []
    for item in template:
        match item:
            case Interpolation(value=int()):
                kinds.append("int")
            case Interpolation(value=str()):
                kinds.append("str")
            case str():
                pass
    return kinds

assert describe(t"{1} and {'two'}") == ["int", "str"]''',
    ),
    (
        "interpolate a callable value",
        '''name = "World"
template = t"Hello {(lambda: name)}"
assert callable(template.interpolations[0].value)
assert template.interpolations[0].value() == "World"''',
    ),
    (
        "return a reusable template from a function",
        '''from string.templatelib import Template

def reusable(name: str, question: str) -> Template:
    return t"Hello {name}, {question}?"

template = reusable("King Arthur", "what is your quest")
assert template.values == ("King Arthur", "what is your quest")''',
    ),
    (
        "inspect the structure of an empty template and one with only an interpolation",
        '''from string.templatelib import Template

empty = t""
assert list(empty) == []
assert empty.strings == ("",)
assert empty.interpolations == ()

value = "hello"
solo = t"{value}"
assert solo.strings == ("", "")
assert solo.interpolations[0].value == "hello"''',
    ),
    (
        "expand the {value=} debug syntax explicitly",
        '''value = 42
template = t"{value=}"
assert template.strings[0] == "value="
assert template.interpolations[0].expression == "value"
assert template.interpolations[0].conversion == "r"''',
    ),
    (
        "build a parameterized SQL query from a template",
        '''from string.templatelib import Interpolation, Template

def sql(template: Template) -> tuple[str, list[object]]:
    query: list[str] = []
    params: list[object] = []
    for item in template:
        if isinstance(item, Interpolation):
            query.append("?")
            params.append(item.value)
        else:
            query.append(item)
    return "".join(query), params

user_id = 42
statement, params = sql(t"SELECT * FROM users WHERE id = {user_id}")
assert statement == "SELECT * FROM users WHERE id = ?"
assert params == [42]''',
    ),
    (
        "render HTML with automatic escaping of interpolated values",
        '''import html as _html
from string.templatelib import Interpolation, Template

def html(template: Template) -> str:
    parts: list[str] = []
    for item in template:
        if isinstance(item, Interpolation):
            parts.append(_html.escape(str(item.value)))
        else:
            parts.append(item)
    return "".join(parts)

evil = "<script>alert('evil')</script>"
assert html(t"<p>{evil}</p>") == "<p>&lt;script&gt;alert(&#x27;evil&#x27;)&lt;/script&gt;</p>"''',
    ),
    (
        "get all interpolated values with the .values property",
        '''name = "World"
count = 3
template = t"{name} has {count} items"
assert template.values == ("World", 3)''',
    ),
]


def validate_snippet(code: str, label: str = "<snippet>") -> tuple[bool, str]:
    """Execute *code* on the live interpreter.  Returns (passed, error_message).

    The error message is empty on success.
    """
    try:
        exec(compile(code, label, "exec"), {})
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def _validate_examples() -> tuple[list[str], list[tuple[str, str]]]:
    """Run every EXAMPLE through validate_snippet.  Returns (kept, failed)."""
    kept: list[str] = []
    failed: list[tuple[str, str]] = []
    for desc, code in EXAMPLES:
        text = f"{HEADER}: {desc}\n{code}"
        ok, err = validate_snippet(text, desc)
        if ok:
            kept.append(text)
        else:
            failed.append((desc, err))
    return kept, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and/or generate PEP 750 training data")
    parser.add_argument(
        "-v", "--validate-only",
        action="store_true",
        help="Validate all examples without writing JSONL.",
    )
    parser.add_argument(
        "-c", "--code",
        type=str,
        default=None,
        help="Validate a single code snippet instead of built-in examples.",
    )
    parser.add_argument(
        "-l", "--label",
        type=str,
        default="<snippet>",
        help="Label for --code output (default: <snippet>).",
    )
    args = parser.parse_args()

    # ── single-snippet mode ──────────────────────────────────────────
    if args.code:
        ok, err = validate_snippet(args.code, args.label)
        if ok:
            print(f"✓  {args.label} — passed")
        else:
            print(f"✗  {args.label} — {err}")
            sys.exit(1)
        return

    # ── validate all built-in examples ───────────────────────────────
    kept, failed = _validate_examples()

    if args.validate_only:
        print(f"{len(kept)}/{len(EXAMPLES)} examples passed validation")
        for desc, err in failed:
            print(f"  FAILED: {desc}: {err}")
        if failed:
            sys.exit(1)
        return

    # ── write JSONL (default) ────────────────────────────────────────
    out = Path("data/pep750.jsonl")
    out.parent.mkdir(exist_ok=True)
    with out.open("w") as fh:
        for text in kept:
            fh.write(json.dumps({"text": text}) + "\n")

    print(f"{len(kept)}/{len(EXAMPLES)} examples verified and written to {out}")
    for desc, err in failed:
        print(f"  FAILED: {desc}: {err}")


if __name__ == "__main__":
    main()
