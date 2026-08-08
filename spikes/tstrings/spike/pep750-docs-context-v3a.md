# PEP 750 documentation context — pinned excerpt

This is the documentation-only context for the baseline arm. It contains
verbatim excerpts from [PEP 750](https://peps.python.org/pep-0750/) and one
neutral PEP example. It deliberately excludes provider code, corpus patterns,
semantic-witness fixtures, and a project-owned default renderer.

- Source: `https://raw.githubusercontent.com/python/peps/main/peps/pep-0750.rst`
- Retrieved: 2026-08-03
- Source SHA-256: `b6715100a62130c7550ebbb19b22c7acb90ba01a24b9b1282c771ad2c1073761`
- PEP status: Final; Python version: 3.14

## Template string literals

> This PEP introduces a new string prefix, ``t``, to define template string
> literals. These literals resolve to a new type, ``Template``, found in the
> standard library module :mod:`!string.templatelib`.

> Template string literals support the full syntax of :pep:`701`.

> Template strings evaluate to an instance of a new immutable type,
> :class:`!string.templatelib.Template`.

```python
from string.templatelib import Template

template = t"This is a template string."
assert isinstance(template, Template)
```

## Template contents

> The ``Template.values`` property is a shortcut for accessing the ``value``
> attribute of each ``Interpolation`` in the template.

```python
@property
def values(self) -> tuple[object, ...]:
    return tuple(i.value for i in self.interpolations)
```

> The ``Template.__iter__()`` method provides a simple way to access the full
> contents of a template. It yields the string parts and interpolations in the
> order they appear, with empty strings omitted.

> The ``Interpolation`` type represents an expression inside a template string.

```python
class Interpolation:
    value: object
    expression: str
    conversion: Literal["a", "r", "s"] | None
    format_spec: str
```

## Processing template strings

> Developers can write arbitrary code to process template strings.

> There is no requirement that template strings are processed in any particular
> way. Code that processes templates has no obligation to return a string.
> Template strings are a flexible, general-purpose feature.

```python
from string.templatelib import Interpolation, Template


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
assert lower_upper(t"HELLO {name}") == "hello WORLD"
```

## Concatenation

> Template strings support explicit concatenation using ``+``. Concatenation is
> supported for two ``Template`` instances via ``Template.__add__()``.

```python
name = "World"
assert isinstance(t"Hello " + t"{name}", Template)
assert (t"Hello " + t"{name}").strings == ("Hello ", "")
assert (t"Hello " + t"{name}").values[0] == "World"
```

## API surface reference

> The ``Template.strings`` property is a shortcut for accessing the static
> string parts of the template. It always has exactly one more element than
> ``Template.interpolations``.

```python
name = "World"
assert t"Hello {name}!".strings == ("Hello ", "!")
assert t"Hello {name}!".values == ("World",)
assert t"Hello {name}!".interpolations[0].expression == "name"
```

> ``string.templatelib.convert(obj, conversion)`` applies an ``!r``/``!s``/``!a``
> conversion, matching the behaviour of f-string conversions.

```python
from string.templatelib import convert

assert convert("x", "r") == "'x'"
assert convert(1.5, None) == 1.5
```

### Note (not a PEP excerpt): the complete public surface

This section is a factual summary added for this evaluation arm. It is not
quoted from PEP 750.

`Template` has exactly these members: `.strings`, `.values`,
`.interpolations`, `__iter__`, and `__add__`.
`Interpolation` has exactly: `.value`, `.expression`, `.conversion`,
`.format_spec`.
`string.templatelib` exports exactly: `Template`, `Interpolation`, `convert`.

The following do **not** exist. Do not import, call, or access them:

| Does not exist | Use instead |
| --- | --- |
| `StaticPart` (importable type) | static parts are plain `str` |
| `static_parts` (importable function) | `template.strings` |
| `template.static_parts` / `template.static` | `template.strings` |
| `template.render()` | write an explicit loop, or define your own function |
| `template.specs` | `interpolation.format_spec` |

There is no built-in renderer. To render fully, iterate the template and
handle each part yourself:

```python
from string.templatelib import Interpolation, Template, convert

def render(template: Template) -> str:
    parts: list[str] = []
    for part in template:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, Interpolation):
            parts.append(format(convert(part.value, part.conversion), part.format_spec))
    return "".join(parts)
```

If a task asks only for the static parts, return `template.strings` — do not
render. If it asks to join the static parts, use `"".join(template.strings)`.
If it asks for the interpolated values, return `template.values` — do not
render.

### How to structure the program

Produce one self-contained program. Every helper function must appear **above**
the line that uses it; calling a function before its `def` is a `NameError`.
Every name must be imported explicitly from `string.templatelib` — nothing is
in scope by default. Put the answer in `result`, and do not print anything.
