"""Independent semantic witnesses for PEP 750 template-string operations."""

from satyrn_model.domains.tstrings import render_fstring_equivalent


def test_renderer_matches_fstring_for_literal_and_interpolation() -> None:
    name = "Ada"
    template = t"Hello, {name}!"

    assert render_fstring_equivalent(template) == f"Hello, {name}!"


def test_renderer_applies_conversion_before_formatting() -> None:
    value = "hi"
    template = t"{value!r:>8}"

    assert render_fstring_equivalent(template) == f"{value!r:>8}"


def test_renderer_applies_dynamic_format_specification() -> None:
    value = 3.14159
    precision = 2
    template = t"{value:.{precision}f}"

    assert render_fstring_equivalent(template) == f"{value:.{precision}f}"


def test_template_repr_and_static_join_are_not_rendering() -> None:
    name = "Ada"
    template = t"Hello, {name}!"

    rendered = render_fstring_equivalent(template)
    assert str(template) != rendered
    assert "".join(template.strings) != rendered
