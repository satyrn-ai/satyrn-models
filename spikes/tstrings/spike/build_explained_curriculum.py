"""Add explanatory rows to a curriculum, and verify every claim they make.

The corpus is task/solution pairs. It never *says* what `Template` is, what
`.strings` holds, or that `.render()` does not exist — the model has to infer
all of it from worked examples. Documentation in the prompt states it outright,
and the seed measurement shows that difference as fragility rather than level:
adapter-alone scores 54/58/48 across seeds (spread 10) while adapter-plus-docs
scores 80/76/80 (spread 4). Knowledge inferred from examples comes out slightly
different on every initialisation.

These rows state it. Content is grounded in `pep750-docs-context-v3.md`, which
is verbatim PEP 750 plus a factual API summary.

Two deliberate exclusions:

- **The canonical `render()` body.** It appears in the docs file, but renderer
  over-exposure is a separate lever, already isolated and measured null.
  Shipping more copies here would confound the two experiments.
- **Task-format instructions** ("assign to `result`", "print nothing"). Those
  are benchmark conventions, not knowledge about the language, and training on
  them would teach the harness rather than the feature.

Every row carrying code is executed at build time and dropped if its assertions
fail. That is not ceremony: a project skill file documented `Interpolation.expr`
and `.conv` — withdrawn draft names that raise `AttributeError` — for the whole
of this effort, and it was a task author who caught it, not us. Prose about an
API is exactly the kind of content where a wrong claim is invisible on review.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SYSTEM = (
    "You are a Python 3.14 expert. Answer questions about the language "
    "precisely and briefly."
)

# (question, answer, verification) — `verification` is executed on its own and
# must raise nothing. An empty string means the answer states no code claim.
ROWS: list[tuple[str, str, str]] = [
    (
        "In Python 3.14, what type does a t-string literal like t'Hi {name}' "
        "evaluate to?",
        "It evaluates to a `string.templatelib.Template`. It is not a `str`, "
        "and it is immutable. Unlike an f-string, which produces a finished "
        "string immediately, a t-string keeps its static parts and its "
        "interpolations available for a later processing step.",
        "from string.templatelib import Template\n"
        "name='x'\n"
        "assert isinstance(t'Hi {name}', Template)\n"
        "assert not isinstance(t'Hi {name}', str)",
    ),
    (
        "What are the public members of `string.templatelib.Template`?",
        "Exactly `.strings`, `.values`, `.interpolations`, `__iter__` and "
        "`__add__`. There is no `.render()` method, no `.static_parts`, and no "
        "`.specs`.",
        "from string.templatelib import Template\n"
        "name='x'\n"
        "t = t'a {name} b'\n"
        "for attr in ('strings','values','interpolations'):\n"
        "    assert hasattr(t, attr)\n"
        "for missing in ('render','static_parts','static','specs'):\n"
        "    assert not hasattr(t, missing)",
    ),
    (
        "What does `Template.strings` return?",
        "A tuple of the static text segments, in order. It always has exactly "
        "one more element than `.interpolations`, so a template that begins or "
        "ends with an interpolation has an empty string at that position.",
        "name='World'\n"
        "assert t'Hello {name}!'.strings == ('Hello ', '!')\n"
        "assert t'{name}'.strings == ('', '')\n"
        "t2 = t'a {name} b {name} c'\n"
        "assert len(t2.strings) == len(t2.interpolations) + 1",
    ),
    (
        "What does `Template.values` return?",
        "A tuple of the evaluated interpolation values, in order — the results "
        "of the expressions, not their source text.",
        "name='World'\ncount=3\n"
        "assert t'Hello {name}!'.values == ('World',)\n"
        "assert t'{name} {count}'.values == ('World', 3)",
    ),
    (
        "What are the fields of a `string.templatelib.Interpolation`?",
        "Exactly `.value`, `.expression`, `.conversion` and `.format_spec`. "
        "`.value` is the evaluated result, `.expression` is the source text of "
        "the expression, `.conversion` is 'r', 's', 'a' or None, and "
        "`.format_spec` is the format specification as a string.",
        "from string.templatelib import Interpolation\n"
        "user='ada'\n"
        "i = t'{user!r:>8}'.interpolations[0]\n"
        "assert i.value == 'ada'\n"
        "assert i.expression == 'user'\n"
        "assert i.conversion == 'r'\n"
        "assert i.format_spec == '>8'\n"
        "for missing in ('expr','conv'):\n"
        "    assert not hasattr(i, missing)",
    ),
    (
        "How do I get the source text of the expression inside an "
        "interpolation?",
        "Read `.expression` on the `Interpolation`. The attribute is spelled in "
        "full — `.expr` is from an earlier draft of PEP 750 and does not "
        "exist; using it raises `AttributeError`.",
        "total=42\n"
        "assert t'{total}'.interpolations[0].expression == 'total'\n"
        "try:\n"
        "    t'{total}'.interpolations[0].expr\n"
        "    raise SystemExit('should have raised')\n"
        "except AttributeError:\n"
        "    pass",
    ),
    (
        "What does the conversion field hold, and what is it called?",
        "`.conversion` — spelled in full, not `.conv`. It is 'r', 's' or 'a' "
        "for `!r`, `!s` and `!a`, and `None` when no conversion was written.",
        "v='x'\n"
        "assert t'{v!r}'.interpolations[0].conversion == 'r'\n"
        "assert t'{v!s}'.interpolations[0].conversion == 's'\n"
        "assert t'{v!a}'.interpolations[0].conversion == 'a'\n"
        "assert t'{v}'.interpolations[0].conversion is None",
    ),
    (
        "What does `string.templatelib.convert` do?",
        "`convert(obj, conversion)` applies an `!r`, `!s` or `!a` conversion "
        "and matches f-string behaviour. With a conversion of `None` it returns "
        "the object unchanged, so it is safe to call unconditionally.",
        "from string.templatelib import convert\n"
        "assert convert('x', 'r') == \"'x'\"\n"
        "assert convert('x', 's') == 'x'\n"
        "assert convert(1.5, None) == 1.5",
    ),
    (
        "What do I get when I iterate over a `Template`?",
        "Its parts in order, alternating as written: plain `str` for the static "
        "segments and `Interpolation` for the substitutions. Empty static "
        "segments are skipped during iteration, which is why iteration and "
        "`.strings` do not always have the same length.",
        "from string.templatelib import Interpolation\n"
        "name='W'\n"
        "kinds = [type(p).__name__ for p in t'Hi {name}!']\n"
        "assert kinds == ['str', 'Interpolation', 'str'], kinds\n"
        "assert all(isinstance(p, (str, Interpolation)) for p in t'{name}')",
    ),
    (
        "When are the expressions inside a t-string evaluated?",
        "Immediately, when the template literal is evaluated — not later when "
        "the template is read or processed. Rebinding a name afterwards does "
        "not change the value already captured in the template.",
        "name='first'\n"
        "template = t'Hello {name}'\n"
        "name = 'second'\n"
        "assert template.values == ('first',)",
    ),
    (
        "Can I concatenate templates?",
        "Yes, with `+`. Two `Template` instances concatenate into a `Template` "
        "via `Template.__add__`.",
        "from string.templatelib import Template\n"
        "name='World'\n"
        "joined = t'Hello ' + t'{name}'\n"
        "assert isinstance(joined, Template)\n"
        "assert joined.values[0] == 'World'",
    ),
    (
        "Is there a built-in way to render a template to a string?",
        "No. There is no `Template.render()` and no rendering helper in the "
        "standard library. Processing a template is the caller's job, and code "
        "that processes one is under no obligation to return a string at all — "
        "returning a tuple, a dict or a parameterised query is equally valid.",
        "name='x'\n"
        "t0 = t'{name}'\n"
        "assert not hasattr(t0, 'render')\n"
        "import string.templatelib as m\n"
        "assert sorted(n for n in dir(m) if not n.startswith('_')) == "
        "['Interpolation', 'Template', 'convert']",
    ),
    (
        "If a task asks only for the static parts of a template, what should I "
        "return?",
        "`template.strings` — do not render. To join them into one string use "
        "`''.join(template.strings)`. If a task asks for the interpolated "
        "values, return `template.values`, again without rendering.",
        "name='W'\n"
        "tpl = t'Hello {name}!'\n"
        "assert tpl.strings == ('Hello ', '!')\n"
        "assert ''.join(tpl.strings) == 'Hello !'\n"
        "assert tpl.values == ('W',)",
    ),
    (
        "Why would I use a t-string instead of an f-string?",
        "Because an f-string is evaluated to a finished string immediately, so "
        "the boundary between literal text and substituted values is gone. A "
        "t-string keeps them separate, which is what lets code escape, quote, "
        "redact or parameterise the interpolated values while leaving the "
        "static text alone — the basis for safe SQL and HTML construction.",
        "value = \"O'Brien\"\n"
        "f_result = f'name = {value}'\n"
        "assert isinstance(f_result, str)\n"
        "tpl = t'name = {value}'\n"
        "assert tpl.strings == ('name = ', '')\n"
        "assert tpl.values == (\"O'Brien\",)",
    ),
    (
        "How do I apply an interpolation's format spec?",
        "Pass it to the built-in `format`: `format(value, interpolation."
        "format_spec)`. An absent format spec is the empty string, which "
        "`format` accepts, so no special case is needed.",
        "amount=1234.5\n"
        "i = t'{amount:>10.2f}'.interpolations[0]\n"
        "assert i.format_spec == '>10.2f'\n"
        "assert format(i.value, i.format_spec) == '   1234.50'\n"
        "j = t'{amount}'.interpolations[0]\n"
        "assert j.format_spec == ''\n"
        "assert format(j.value, j.format_spec) == '1234.5'",
    ),
    (
        "Do the names in `string.templatelib` need importing?",
        "Yes. `Template`, `Interpolation` and `convert` must be imported "
        "explicitly; none of them is a builtin. `isinstance` checks against "
        "`Interpolation` fail with `NameError` if the import is missing.",
        "import builtins\n"
        "for n in ('Template', 'Interpolation', 'convert'):\n"
        "    assert not hasattr(builtins, n)\n"
        "from string.templatelib import Interpolation, Template, convert\n"
        "assert Template and Interpolation and convert",
    ),
    (
        "How many static parts does a template with two interpolations have?",
        "Three. `.strings` always has exactly one more element than "
        "`.interpolations`, and positions with no literal text between "
        "substitutions hold the empty string.",
        "a=1\nb=2\n"
        "tpl = t'{a}{b}'\n"
        "assert len(tpl.interpolations) == 2\n"
        "assert tpl.strings == ('', '', '')",
    ),
    (
        "Can a template be used where a string is expected?",
        "No. `Template` is not a subclass of `str`, so passing one to code "
        "expecting a string fails or misbehaves. Convert it deliberately by "
        "processing its parts.",
        "from string.templatelib import Template\n"
        "name='x'\n"
        "tpl = t'a {name}'\n"
        "assert not isinstance(tpl, str)\n"
        "try:\n"
        "    'prefix' + tpl\n"
        "    raise SystemExit('should have raised')\n"
        "except TypeError:\n"
        "    pass",
    ),
]


# The content-matched placebo. Same system prompt, same 18-row x 5-copy shape,
# same stratum, same resulting row count — verified-true Python 3.14 facts about
# topics with nothing to do with t-strings.
#
# This is the control the experiment actually needs. A matched-update run would
# have held training length constant but changed the LR schedule length with it,
# and would have said nothing about the live alternative that *any* second
# register of prose helps — the explanatory rows train under a different system
# prompt from everything else, so "format diversity regularises" competes with
# "PEP 750 knowledge transfers". Only unrelated prose separates them.
PLACEBO_ROWS: list[tuple[str, str, str]] = [
    ("What does `dataclasses.field(default_factory=...)` do?",
     "It supplies a zero-argument callable used to build a fresh default for "
     "each instance. It is how mutable defaults such as `list` are declared, "
     "since a bare mutable default raises `ValueError` at class creation.",
     "from dataclasses import dataclass, field\n"
     "@dataclass\nclass A:\n    xs: list = field(default_factory=list)\n"
     "assert A().xs == [] and A().xs is not A().xs"),
    ("How do I get a path's suffix and stem with `pathlib`?",
     "`Path.suffix` is the final extension including the dot, and `Path.stem` "
     "is the filename without it. `Path.suffixes` returns every extension.",
     "from pathlib import Path\np = Path('a/b/report.tar.gz')\n"
     "assert p.suffix == '.gz' and p.stem == 'report.tar'\n"
     "assert p.suffixes == ['.tar', '.gz']"),
    ("What does `itertools.pairwise` yield?",
     "Successive overlapping pairs from an iterable: for `ABCD` it yields "
     "`AB`, `BC`, `CD`. An input shorter than two items yields nothing.",
     "from itertools import pairwise\n"
     "assert list(pairwise('ABCD')) == [('A','B'),('B','C'),('C','D')]\n"
     "assert list(pairwise('A')) == []"),
    ("What is the difference between `dict.get` and `dict.setdefault`?",
     "`get` returns a default without touching the dict; `setdefault` inserts "
     "the default under the key when absent and returns it.",
     "d = {}\nassert d.get('k', 1) == 1 and d == {}\n"
     "assert d.setdefault('k', 1) == 1 and d == {'k': 1}"),
    ("How does `functools.cache` differ from `lru_cache`?",
     "`cache` is `lru_cache(maxsize=None)` — an unbounded memo with no eviction "
     "and slightly less bookkeeping.",
     "from functools import cache\ncalls = []\n"
     "@cache\ndef f(n):\n    calls.append(n)\n    return n * 2\n"
     "assert f(3) == 6 and f(3) == 6 and calls == [3]"),
    ("What does the walrus operator do?",
     "`:=` assigns inside an expression, so a value can be bound and tested in "
     "one place — common in `while` and comprehension guards.",
     "xs = [1, 2, 3, 4]\n"
     "assert [y for x in xs if (y := x * 2) > 4] == [6, 8]"),
    ("What does `str.removeprefix` do when the prefix is absent?",
     "It returns the string unchanged. It never raises, and it strips at most "
     "one occurrence — unlike `lstrip`, which removes any leading characters "
     "in the given set.",
     "assert 'test_a'.removeprefix('test_') == 'a'\n"
     "assert 'abc'.removeprefix('zz') == 'abc'\n"
     "assert 'xxabc'.lstrip('x') == 'abc'"),
    ("How do I merge two dicts with the `|` operator?",
     "`a | b` returns a new dict with `b`'s values winning on shared keys; "
     "`a |= b` updates in place.",
     "a = {'x': 1, 'y': 2}\nb = {'y': 3}\n"
     "assert (a | b) == {'x': 1, 'y': 3}\nassert a == {'x': 1, 'y': 2}"),
    ("What does `enumerate(seq, start=1)` change?",
     "Only the counter's first value. It does not skip an element — indices "
     "begin at 1 while iteration still starts at the first item.",
     "assert list(enumerate('ab', start=1)) == [(1,'a'), (2,'b')]"),
    ("When is a `set` comprehension preferable to `set(...)` of a list?",
     "When the intermediate list is unnecessary — the comprehension builds the "
     "set directly, avoiding one full materialisation.",
     "xs = [1, 2, 2, 3]\nassert {x * 2 for x in xs} == {2, 4, 6}"),
    ("What does `collections.Counter.most_common(n)` return?",
     "A list of the `n` most frequent `(element, count)` pairs, highest first. "
     "Ties keep insertion order; with no argument it returns all of them.",
     "from collections import Counter\n"
     "assert Counter('aabbbc').most_common(2) == [('b',3), ('a',2)]"),
    ("How do I make a dataclass immutable?",
     "`@dataclass(frozen=True)`. Assigning to a field then raises "
     "`FrozenInstanceError`, and the class becomes hashable by default.",
     "from dataclasses import dataclass, FrozenInstanceError\n"
     "@dataclass(frozen=True)\nclass P:\n    x: int\n"
     "p = P(1)\n"
     "try:\n    p.x = 2\n    raise SystemExit('should have raised')\n"
     "except FrozenInstanceError:\n    pass"),
    ("What does `zip(strict=True)` do?",
     "It raises `ValueError` when the iterables differ in length, instead of "
     "silently stopping at the shortest.",
     "try:\n    list(zip([1,2], [1], strict=True))\n"
     "    raise SystemExit('should have raised')\n"
     "except ValueError:\n    pass\n"
     "assert list(zip([1,2],[1])) == [(1,1)]"),
    ("How do I read a file's text with `pathlib`?",
     "`Path.read_text(encoding=...)` reads the whole file and closes it. "
     "`write_text` is the counterpart.",
     "from pathlib import Path\nimport tempfile, os\n"
     "d = tempfile.mkdtemp()\np = Path(d) / 'f.txt'\n"
     "p.write_text('hi', encoding='utf-8')\n"
     "assert p.read_text(encoding='utf-8') == 'hi'"),
    ("What is the difference between `is` and `==`?",
     "`is` compares identity — whether two names refer to one object — while "
     "`==` compares value. Use `is` only for singletons such as `None`.",
     "a = [1]\nb = [1]\nassert a == b and a is not b\nassert a is a"),
    ("What does `sorted(key=...)` receive?",
     "A one-argument callable applied to each element, whose result is used "
     "for ordering. The elements themselves are returned, not the keys.",
     "xs = ['bbb', 'a', 'cc']\n"
     "assert sorted(xs, key=len) == ['a', 'cc', 'bbb']"),
    ("How do I catch several exception types in one clause?",
     "Give `except` a tuple of classes. A bare `except:` also catches "
     "`KeyboardInterrupt` and `SystemExit` and should be avoided.",
     "def f(x):\n"
     "    try:\n        return int(x)\n"
     "    except (ValueError, TypeError):\n        return None\n"
     "assert f('a') is None and f(None) is None and f('3') == 3"),
    ("What does `textwrap.dedent` do?",
     "It removes the longest common leading whitespace from every line, which "
     "is how indented triple-quoted literals are normalised. Lines consisting "
     "only of whitespace are ignored when computing the common prefix.",
     "from textwrap import dedent\n"
     "assert dedent('    a\\n    b\\n') == 'a\\nb\\n'"),
]


def verify(snippet: str, timeout: int = 20) -> str | None:
    """Run one verification snippet; return None on success, else the error."""
    if not snippet.strip():
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(snippet)
        path = handle.name
    try:
        done = subprocess.run(
            [sys.executable, path], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    finally:
        Path(path).unlink(missing_ok=True)
    if done.returncode != 0:
        return (done.stderr.strip().splitlines() or ["failed"])[-1]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path("handoff/curriculum-repair-v2"))
    parser.add_argument(
        "--out", type=Path, default=Path("handoff/curriculum-explained-v1")
    )
    parser.add_argument(
        "--placebo",
        action="store_true",
        help="Use PLACEBO_ROWS: same shape, unrelated topics, as the control.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=5,
        help="Copies of each explanatory row, to reach the registered share.",
    )
    args = parser.parse_args()

    content_rows = PLACEBO_ROWS if args.placebo else ROWS
    failures = []
    for index, (question, _, snippet) in enumerate(content_rows):
        error = verify(snippet)
        if error:
            failures.append((index, question[:60], error))
    if failures:
        for index, question, error in failures:
            print(f"row {index}: {question} -> {error}")
        raise SystemExit(f"{len(failures)} rows make false claims")
    label = "placebo" if args.placebo else "explanatory"
    print(f"verified {len(content_rows)} {label} rows, all claims hold")

    args.out.mkdir(parents=True, exist_ok=True)
    for split in ("train", "valid"):
        rows = [
            json.loads(line)
            for line in (args.base / f"{split}.jsonl").read_text().splitlines()
            if line.strip()
        ]
        if split == "train":
            for copy in range(args.repeat):
                for index, (question, answer, _) in enumerate(content_rows):
                    rows.append(
                        {
                            "messages": [
                                {"role": "system", "content": SYSTEM},
                                {"role": "user", "content": question},
                                {"role": "assistant", "content": answer},
                            ],
                            "partition": "train",
                            "prompt_family": "explanatory",
                            "seed_ids": [f"explain-{index}"],
                            "semantic_id": f"explain-{index}-{copy}",
                            "task_id": f"explain-{index}-{copy}",
                        }
                    )
        with (args.out / f"{split}.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"{split}: {len(rows)} rows")

    # The trainer keys `selection.jsonl` by `row_id` and looks each train row
    # up by its `task_id`, using the result for stratified batching. Copying the
    # base selection unchanged left the explanatory rows unrepresented and every
    # run died on `KeyError: 'explain-0-0'` before touching the GPU.
    #
    # They get their own stratum rather than being folded into an existing one:
    # the interleaved batcher spreads strata across batches, which is the
    # behaviour wanted here — explanation distributed through training, not
    # clumped into a few adjacent steps.
    selection = (args.base / "selection.jsonl").read_text().splitlines()
    extra = []
    for copy in range(args.repeat):
        for index, (question, _, _) in enumerate(content_rows):
            extra.append(
                json.dumps(
                    {
                        "row_id": f"explain-{index}-{copy}",
                        "seed_id": f"explain-{index}",
                        "pattern_id": "explanatory-docs-v3",
                        "prompt": question,
                        "prompt_family": "explanatory",
                        "role": "consumer",
                        "cell_role": "consumer",
                        "operation": "explanatory",
                        "capability": "explanatory",
                        "property": "explanatory",
                        "domain": "docs",
                        "source_kind": "authored",
                        "skeleton": "",
                    },
                    sort_keys=True,
                )
            )
    (args.out / "selection.jsonl").write_text(
        "\n".join([line for line in selection if line.strip()] + extra) + "\n"
    )
    print(f"selection: {len(selection) + len(extra)} rows "
          f"({len(extra)} explanatory)")

    for name in ("coverage.json", "manifest.json"):
        source = args.base / name
        if source.exists():
            (args.out / name).write_bytes(source.read_bytes())


if __name__ == "__main__":
    main()
