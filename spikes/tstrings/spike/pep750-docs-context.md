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
