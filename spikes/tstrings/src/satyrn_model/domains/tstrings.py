"""Provider-owned semantic primitives for Python template strings.

These functions are benchmark witnesses, not generic provider contracts and
not SP5 teaching implementations. Keeping them here lets the provider verify
the meaning of a ``RenderTemplate`` task independently of its generated
reference program.
"""

from string.templatelib import Interpolation, Template, convert

__all__ = ["render_fstring_equivalent"]


def render_fstring_equivalent(template: Template) -> str:
    """Render a template with f-string conversion and formatting semantics.

    PEP 750 deliberately does not define ``str(template)`` as rendering. This
    opt-in operation preserves static parts and handles each interpolation with
    ``format(convert(value, conversion), format_spec)``.
    """
    parts: list[str] = []
    for part in template:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, Interpolation):
            value = convert(part.value, part.conversion)
            parts.append(format(value, part.format_spec))
        else:  # pragma: no cover - Template's public iteration is closed.
            raise TypeError(f"unexpected template part: {type(part).__name__}")
    return "".join(parts)
