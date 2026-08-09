"""Reviewed patterns catalog: the initial audited pattern set.

Patterns land here as reviewed source (see design §2.3 — no LLM call exists
anywhere in the pipeline). Each entry declares its property specs, claimed
labels, and every helper/template/renderer dependency.
"""

from .registry import Pattern, PromptVariant, PropertySpec

__all__ = ["CATALOG"]


def _p(**kw) -> Pattern:
    description = kw["description"]
    kw.setdefault(
        "prompt_variants",
        (
            PromptVariant(
                id="direct",
                text=f"{description}.",
                include_seed_context=True,
            ),
            PromptVariant(
                id="python-program",
                text=f"Write a Python 3.14 program that will {description}.",
                include_seed_context=True,
            ),
            PromptVariant(
                id="pep750-request",
                text=f"Using PEP 750, {description}.",
                include_seed_context=True,
            ),
        ),
    )
    return Pattern(**kw)


CATALOG: tuple[Pattern, ...] = (
    _p(
        id="author-static-parts",
        description="define a typed template function that returns static string parts",
        property_specs=(PropertySpec(kind="introspect", target=".strings"),),
        labels=frozenset({"introspect"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("introspect-strings",),
    ),
    _p(
        id="author-values",
        description="define a typed template function that returns interpolated values",
        property_specs=(PropertySpec(kind="introspect", target=".values"),),
        labels=frozenset({"introspect"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("introspect-values",),
    ),
    _p(
        id="author-render-template",
        description="define a typed template function that fully renders a template",
        property_specs=(PropertySpec(kind="render_template"),),
        labels=frozenset({"render_template"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=(
            "render-conversion-format",
            "reject-template-str",
            "reject-static-join",
            "reject-omitted-conversion",
        ),
    ),
    _p(
        id="intro-strings",
        description="introspect the static string parts of a template",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".strings", index=0, field="strings"
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-strings",),
    ),
    _p(
        id="render-template",
        description=(
            "render a template with f-string conversion and formatting semantics"
        ),
        property_specs=(PropertySpec(kind="render_template"),),
        labels=frozenset({"render_template"}),
        requires=("string.templatelib",),
        witnesses=(
            "render-conversion-format",
            "reject-template-str",
            "reject-static-join",
            "reject-omitted-conversion",
        ),
    ),
    _p(
        id="join-static-parts",
        description="join a template's static parts without rendering interpolations",
        property_specs=(PropertySpec(kind="join_static_parts"),),
        labels=frozenset({"join_static_parts"}),
        requires=("string.templatelib",),
        witnesses=("join-static-intent",),
    ),
    _p(
        id="compose-templates",
        description="concatenate two templates with +",
        property_specs=(PropertySpec(kind="compose_templates", arity=2),),
        labels=frozenset({"compose_templates"}),
        requires=("string.templatelib",),
        witnesses=("compose-template",),
    ),
    _p(
        id="construct-convert",
        description="apply a !r conversion with convert()",
        property_specs=(PropertySpec(kind="construct", operation="convert"),),
        labels=frozenset({"construct"}),
        requires=("string.templatelib.convert",),
        witnesses=("construct-convert",),
    ),
    _p(
        id="negative-fstring",
        description="produce the same output with an old-form f-string",
        property_specs=(PropertySpec(kind="negative"),),
        labels=frozenset({"negative"}),
        requires=(),
        witnesses=("negative-control",),
    ),
    _p(
        id="intro-values",
        description="introspect the interpolated values of a template",
        property_specs=(PropertySpec(kind="introspect", target=".values"),),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-values",),
    ),
    _p(
        id="intro-interpolations",
        description="introspect the interpolations of a template",
        property_specs=(
            PropertySpec(
                kind="introspect",
                target=".interpolations",
                field="interpolations",
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="intro-expressions",
        description="inspect source expressions on template interpolations",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".interpolations", field="expression"
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="intro-conversions",
        description="inspect conversion markers on template interpolations",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".interpolations", field="conversion"
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="intro-format-specs",
        description="inspect format specs on template interpolations",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".interpolations", field="format_spec"
            ),
        ),
        labels=frozenset({"introspect"}),
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="join-static-parts-pipe",
        description="join static template strings with a pipe separator",
        property_specs=(
            PropertySpec(kind="join_static_parts", separator="|"),
        ),
        labels=frozenset({"join_static_parts"}),
        requires=("string.templatelib",),
        witnesses=("join-static-intent",),
    ),
    _p(
        id="join-static-parts-newline",
        description="join static template strings with newline separators",
        property_specs=(
            PropertySpec(kind="join_static_parts", separator="\n"),
        ),
        labels=frozenset({"join_static_parts"}),
        requires=("string.templatelib",),
        witnesses=("join-static-intent",),
    ),
    _p(
        id="negative-fstring-direct-output",
        description="use an f-string when deferred template processing is unnecessary",
        property_specs=(PropertySpec(kind="negative"),),
        labels=frozenset({"negative"}),
        requires=(),
        witnesses=("negative-control",),
    ),
    _p(
        id="render-template-explicit-function",
        description="consume a typed template renderer and return its string output",
        property_specs=(PropertySpec(kind="render_template"),),
        labels=frozenset({"render_template"}),
        requires=("string.templatelib",),
        witnesses=(
            "render-conversion-format",
            "reject-template-str",
            "reject-static-join",
            "reject-omitted-conversion",
        ),
    ),
    _p(
        id="author-interpolations",
        description="define a typed function returning template interpolations",
        property_specs=(
            PropertySpec(
                kind="introspect",
                target=".interpolations",
                field="interpolations",
            ),
        ),
        labels=frozenset({"introspect"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="author-expressions",
        description="define a typed function returning expressions from interpolations",
        property_specs=(
            PropertySpec(
                kind="introspect", target=".interpolations", field="expression"
            ),
        ),
        labels=frozenset({"introspect"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="author-format-specs",
        description=(
            "define a typed function returning format specs from interpolations"
        ),
        property_specs=(
            PropertySpec(
                kind="introspect", target=".interpolations", field="format_spec"
            ),
        ),
        labels=frozenset({"introspect"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("introspect-interpolations",),
    ),
    _p(
        id="author-render-explicit-function",
        description="define a second typed template renderer for string output",
        property_specs=(PropertySpec(kind="render_template"),),
        labels=frozenset({"render_template"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=(
            "render-conversion-format",
            "reject-template-str",
            "reject-static-join",
            "reject-omitted-conversion",
        ),
    ),
    _p(
        id="compose-then-strings",
        description="compose two templates and inspect their strings",
        property_specs=(
            PropertySpec(kind="compose_templates", arity=2, result="strings"),
        ),
        labels=frozenset({"compose_templates"}),
        requires=("string.templatelib",),
        witnesses=("compose-template",),
    ),
    _p(
        id="compose-then-values",
        description="compose two templates and inspect their values",
        property_specs=(
            PropertySpec(kind="compose_templates", arity=2, result="values"),
        ),
        labels=frozenset({"compose_templates"}),
        requires=("string.templatelib",),
        witnesses=("compose-template",),
    ),
    _p(
        id="compose-then-interpolations",
        description="compose two templates and inspect their interpolations",
        property_specs=(
            PropertySpec(
                kind="compose_templates", arity=2, result="interpolations"
            ),
        ),
        labels=frozenset({"compose_templates"}),
        requires=("string.templatelib",),
        witnesses=("compose-template",),
    ),
    _p(
        id="compose-then-render",
        description="compose two templates and render the resulting template",
        property_specs=(
            PropertySpec(kind="compose_templates", arity=2, result="rendered"),
        ),
        labels=frozenset({"compose_templates"}),
        requires=("string.templatelib",),
        witnesses=("compose-template",),
    ),
    _p(
        id="construct-convert-s",
        description="apply an !s conversion with convert()",
        property_specs=(
            PropertySpec(kind="construct", operation="convert", conversion="s"),
        ),
        labels=frozenset({"construct"}),
        requires=("string.templatelib.convert",),
        witnesses=("construct-convert",),
    ),
    _p(
        id="construct-convert-a",
        description="apply an !a conversion with convert()",
        property_specs=(
            PropertySpec(kind="construct", operation="convert", conversion="a"),
        ),
        labels=frozenset({"construct"}),
        requires=("string.templatelib.convert",),
        witnesses=("construct-convert",),
    ),
    *tuple(
        _p(
            id=pattern_id,
            description=description,
            property_specs=(
                PropertySpec(
                    kind="construct",
                    operation="Interpolation",
                    conversion=conversion,
                    expression=expression,
                    format_spec=format_spec,
                ),
            ),
            labels=frozenset({"construct"}),
            requires=("string.templatelib.Interpolation",),
            witnesses=("construct-interpolation",),
        )
        for pattern_id, description, conversion, expression, format_spec in (
            (
                "construct-interpolation-basic",
                "construct an Interpolation with default metadata",
                None,
                "value",
                "",
            ),
            (
                "construct-interpolation-r",
                "construct an Interpolation with !r conversion metadata",
                "r",
                "value",
                "",
            ),
            (
                "construct-interpolation-s",
                "construct an Interpolation with !s conversion metadata",
                "s",
                "value",
                "",
            ),
            (
                "construct-interpolation-a",
                "construct an Interpolation with !a conversion metadata",
                "a",
                "value",
                "",
            ),
            (
                "construct-interpolation-format",
                "construct an Interpolation with a format spec",
                None,
                "value",
                ">8",
            ),
            (
                "construct-interpolation-expression",
                "construct an Interpolation preserving its source expression",
                None,
                "user.name",
                "",
            ),
            (
                "construct-interpolation-conversion-format",
                "construct an Interpolation with conversion and format metadata",
                "r",
                "value",
                ">8",
            ),
        )
    ),
    *tuple(
        _p(
            id=f"contrast-{outcome}",
            description=description,
            property_specs=(
                PropertySpec(kind="select_result", outcome=outcome),
            ),
            labels=frozenset({"select_result"}),
            requires=("string.templatelib",),
            witnesses=("contrastive-result",),
        )
        for outcome, description in (
            ("template", "return the Template object itself without rendering it"),
            ("strings", "return template.strings without rendering values"),
            ("values", "return template.values without returning static strings"),
            (
                "joined_static",
                "join template.strings while deliberately omitting interpolated values",
            ),
            (
                "rendered",
                "fully render the template with conversion and formatting semantics",
            ),
        )
    ),
    *tuple(
        _p(
            id=f"contrast-author-{outcome}",
            description=description,
            property_specs=(
                PropertySpec(kind="select_result", outcome=outcome),
            ),
            labels=frozenset({"select_result"}),
            role="author",
            requires=("string.templatelib",),
            witnesses=("contrastive-result",),
        )
        for outcome, description in (
            ("strings", "define a typed template function returning template.strings"),
            ("values", "define a typed template function returning template.values"),
            (
                "joined_static",
                "define a typed template function joining only template.strings",
            ),
            (
                "rendered",
                "define a typed template function that fully renders the template",
            ),
        )
    ),
    *tuple(
        _p(
            id=f"render-subskill-{stage}",
            description=description,
            property_specs=(
                PropertySpec(kind="render_subskill", stage=stage),
            ),
            labels=frozenset({"render_subskill"}),
            requires=("string.templatelib",),
            witnesses=("render-subskill",),
        )
        for stage, description in (
            ("iterate_parts", "iterate over the template and return its ordered parts"),
            (
                "classify_parts",
                "classify each template part as static text or an interpolation",
            ),
            (
                "convert_value",
                "apply the first interpolation's conversion with convert()",
            ),
            (
                "format_value",
                "convert and format the first interpolation using its format spec",
            ),
            (
                "render_interpolation",
                "define a typed function that converts and formats one interpolation",
            ),
            (
                "render_template",
                "fully render all static and interpolated template parts",
            ),
        )
    ),
    _p(
        id="render-subskill-author-template",
        description="define a typed template function that renders every template part",
        property_specs=(
            PropertySpec(kind="render_subskill", stage="render_template"),
        ),
        labels=frozenset({"render_subskill"}),
        role="author",
        requires=("string.templatelib",),
        witnesses=("render-subskill",),
    ),
)
