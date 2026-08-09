"""Minimal SP5→provider bridge: converts a TaskIntent to a TaskRecord.

This is deliberately small — it maps one TaskIntent to one TaskRecord using
the provider contract types. It does NOT import the authoring pipeline or
seed/pattern code. The goal is to produce a real, valid DatasetSnapshot that
round-trips through the provider's ingest and exercises TStringPolicy.
"""

from __future__ import annotations

from satyrn_model.authoring.models import (
    ComposeTemplates,
    Construct,
    Introspect,
    JoinStaticParts,
    NegativeControl,
    PolicyIntent,
    RenderSubskill,
    RenderTemplate,
    Seed,
    SelectTemplateResult,
    TaskIntent,
)
from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    Raises,
    TaskRecord,
)


def build_task(intent: TaskIntent, seeds: tuple[Seed, ...] | None = None) -> TaskRecord:
    """Convert one TaskIntent to a provider TaskRecord.

    Derives reference code, checks, and policy config from the intent's
    properties and policy_intent. When *seeds* are supplied, the reference
    program is rendered from the seed literals and bindings (the generated
    path); otherwise a minimal self-contained reference is emitted.
    """
    checks = _build_checks(intent)
    return TaskRecord(
        prompt=intent.description,
        reference=_build_reference(intent, seeds),
        checks=checks,
        policy=PolicyRef(
            id="tstring",
            version=1,
            config={
                "requires_template": intent.policy_intent.requires_template,
                "templatelib_apis": sorted(intent.policy_intent.templatelib_apis_used),
            },
        ),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="sp5-task-builder",
            generator_version="0.1.0",
            seed_id=intent.id,
        ),
    )


def generated_intent(exercise, pattern) -> TaskIntent:
    """Project a GeneratedExercise + its Pattern into a canonical TaskIntent.

    Prompt and checks are both derived here — never independently rewritten
    from the exercise — so the cross-projection gate holds by construction.
    """
    from satyrn_model.authoring.patterns.registry import prompt_variants

    variants = {variant.id: variant for variant in prompt_variants(pattern)}
    variant = variants[exercise.prompt_family]
    return TaskIntent(
        id=exercise.id,
        description=_render_generated_prompt(
            variant.text,
            seeds=exercise.seeds,
            include_seed_context=variant.include_seed_context,
        ),
        properties=exercise.properties,
        policy_intent=policy_intent_from_properties(exercise.properties),
        role=pattern.role,
    )


def _render_generated_prompt(
    instruction: str,
    *,
    seeds: tuple[Seed, ...],
    include_seed_context: bool,
) -> str:
    """Render a reviewed instruction family with derivable task inputs."""
    if not include_seed_context:
        return instruction
    sections = [instruction]
    if seeds:
        binding_lines = [
            f"{name} = {expression}"
            for seed in seeds
            for name, expression in seed.bindings
        ]
        if binding_lines:
            sections.append(
                "Copy these input bindings exactly before using the template:\n"
                "```python\n"
                + "\n".join(binding_lines)
                + "\n```"
            )
        label = (
            "Template expression" if len(seeds) == 1 else "Template expressions"
        )
        expressions = "\n".join(f"- `{seed.literal}`" for seed in seeds)
        sections.append(f"{label}:\n{expressions}")
    sections.append("Assign the requested answer to module-level variable `result`.")
    return "\n\n".join(sections)


def policy_intent_from_properties(properties) -> PolicyIntent:
    """Derive the declarative policy intent from the property tuple."""
    requires_template = not all(
        isinstance(p, (Construct, NegativeControl)) for p in properties
    )
    apis: set[str] = set()
    for p in properties:
        if isinstance(p, Introspect):
            apis.add(p.target.lstrip(".").split(".")[0])
        elif isinstance(p, JoinStaticParts):
            apis.add("strings")
        elif isinstance(p, SelectTemplateResult):
            if p.outcome in {"strings", "joined_static"}:
                apis.add("strings")
            elif p.outcome == "values":
                apis.add("values")
            elif p.outcome == "rendered":
                apis.add("convert")
        elif isinstance(p, RenderSubskill) and p.stage in {
            "convert_value",
            "format_value",
            "render_interpolation",
            "render_template",
        }:
            apis.add("convert")
        elif isinstance(p, Construct) and p.operation == "convert":
            apis.add("convert")
    return PolicyIntent(
        requires_template=requires_template, templatelib_apis_used=frozenset(apis)
    )


def _build_reference(intent: TaskIntent, seeds: tuple[Seed, ...] | None) -> str:
    """Generate reference code from the intent properties."""
    props = intent.properties
    if not props:
        return "result = None\n"

    first = props[0]
    if intent.role == "author":
        return _ref_author(first, seeds)
    if isinstance(first, Introspect):
        return _ref_introspect(first, seeds)
    if isinstance(first, Construct):
        return _ref_construct(first)
    if isinstance(first, RenderTemplate):
        return _ref_render(first, seeds)
    if isinstance(first, JoinStaticParts):
        return _ref_join_static_parts(first, seeds)
    if isinstance(first, SelectTemplateResult):
        return _ref_select_result(first, seeds)
    if isinstance(first, RenderSubskill):
        return _ref_render_subskill(first, seeds)
    if isinstance(first, ComposeTemplates):
        return _ref_compose_templates(first, seeds)
    if isinstance(first, NegativeControl):
        return _ref_negative(first, seeds)
    return "result = None\n"


def _ref_author(prop, seeds: tuple[Seed, ...] | None) -> str:
    preamble = _template_lines(seeds[0]) if seeds else _fallback_template()
    if isinstance(prop, Introspect) and prop.target == ".strings":
        return (
            "from string.templatelib import Template\n\n"
            "def static_parts(template: Template) -> tuple[str, ...]:\n"
            "    return template.strings\n\n"
            f"{preamble}\nresult = static_parts(template)\n"
        )
    if isinstance(prop, Introspect) and prop.target == ".values":
        return (
            "from string.templatelib import Template\n\n"
            "def values_of(template: Template) -> tuple[object, ...]:\n"
            "    return template.values\n\n"
            f"{preamble}\nresult = values_of(template)\n"
        )
    if isinstance(prop, Introspect) and prop.target == ".interpolations":
        if prop.field in {"interpolations", ""}:
            return (
                "from string.templatelib import Interpolation, Template\n\n"
                "def interpolations_of(\n"
                "    template: Template,\n"
                ") -> tuple[Interpolation, ...]:\n"
                "    return template.interpolations\n\n"
                f"{preamble}\nresult = interpolations_of(template)\n"
            )
        return (
            "from string.templatelib import Interpolation, Template\n\n"
            "def interpolation_metadata(\n"
            "    template: Template,\n"
            f") -> tuple[object, ...]:\n"
            f"    return tuple(part.{prop.field} "
            "for part in template.interpolations)\n\n"
            f"{preamble}\nresult = interpolation_metadata(template)\n"
        )
    if isinstance(prop, RenderTemplate):
        return _ref_render(prop, seeds)
    if isinstance(prop, SelectTemplateResult):
        if prop.outcome == "rendered":
            return _ref_render(RenderTemplate(), seeds)
        function_name = {
            "template": "identity",
            "strings": "static_parts",
            "values": "values_of",
            "joined_static": "join_static_parts",
        }[prop.outcome]
        return_type = {
            "template": "Template",
            "strings": "tuple[str, ...]",
            "values": "tuple[object, ...]",
            "joined_static": "str",
        }[prop.outcome]
        expression = {
            "template": "template",
            "strings": "template.strings",
            "values": "template.values",
            "joined_static": '\"\".join(template.strings)',
        }[prop.outcome]
        return (
            "from string.templatelib import Template\n\n"
            f"def {function_name}(template: Template) -> {return_type}:\n"
            f"    return {expression}\n\n"
            f"{preamble}\nresult = {function_name}(template)\n"
        )
    if isinstance(prop, RenderSubskill) and prop.stage == "render_template":
        return _ref_render(RenderTemplate(), seeds)
    raise ValueError(f"unsupported authoring property {prop!r}")


def _bindings_lines(seed: Seed) -> str:
    """Render the seed's binding expressions as module-level assignments."""
    return "\n".join(f"{n} = {expr}" for n, expr in seed.bindings)


def _template_lines(seed: Seed) -> str:
    """Render the seed's binding assignments plus its template literal."""
    lines = _bindings_lines(seed)
    if lines:
        lines += "\n"
    return f"{lines}template = {seed.literal}"


def _fallback_template() -> str:
    return 'name = "World"\ntemplate = t"Hello {name}"'


def _ref_introspect(prop: Introspect, seeds: tuple[Seed, ...] | None) -> str:
    attr = prop.target.lstrip(".")
    if seeds:
        preamble = _template_lines(seeds[0])
    else:
        preamble = _fallback_template()
    if attr == "interpolations" and prop.field not in {"interpolations", ""}:
        return (
            f"{preamble}\n"
            f"result = tuple(part.{prop.field} for part in template.interpolations)\n"
        )
    return f"{preamble}\nresult = template.{attr}\n"


def _ref_select_result(
    prop: SelectTemplateResult, seeds: tuple[Seed, ...] | None
) -> str:
    preamble = _template_lines(seeds[0]) if seeds else _fallback_template()
    if prop.outcome == "template":
        return f"{preamble}\nresult = template\n"
    if prop.outcome == "strings":
        return f"{preamble}\nresult = template.strings\n"
    if prop.outcome == "values":
        return f"{preamble}\nresult = template.values\n"
    if prop.outcome == "joined_static":
        return f'{preamble}\nresult = "".join(template.strings)\n'
    return _ref_render(RenderTemplate(), seeds)


def _ref_render_subskill(
    prop: RenderSubskill, seeds: tuple[Seed, ...] | None
) -> str:
    preamble = _template_lines(seeds[0]) if seeds else _fallback_template()
    if prop.stage == "iterate_parts":
        return f"{preamble}\nresult = tuple(template)\n"
    if prop.stage == "classify_parts":
        return (
            "from string.templatelib import Interpolation\n\n"
            f"{preamble}\n"
            "result = tuple(\n"
            '    "static" if isinstance(part, str) else "interpolation"\n'
            "    for part in template\n"
            ")\n"
        )
    prefix = (
        "from string.templatelib import Interpolation, convert\n\n"
        + preamble
        + "\ninterpolation = template.interpolations[0]\n"
    )
    if prop.stage == "convert_value":
        return prefix + (
            "result = convert(interpolation.value, interpolation.conversion)\n"
        )
    if prop.stage == "format_value":
        return prefix + (
            "value = convert(interpolation.value, interpolation.conversion)\n"
            "result = format(value, interpolation.format_spec)\n"
        )
    if prop.stage == "render_interpolation":
        return prefix + (
            "def render_interpolation(interpolation: Interpolation) -> str:\n"
            "    value = convert(interpolation.value, interpolation.conversion)\n"
            "    return format(value, interpolation.format_spec)\n\n"
            "result = render_interpolation(interpolation)\n"
        )
    return _ref_render(RenderTemplate(), seeds)


def _ref_construct(prop: Construct) -> str:
    if prop.operation == "convert":
        conversion = prop.conversion or "r"
        return (
            "from string.templatelib import convert\n"
            "def apply_conversion(value: object) -> object:\n"
            f"    return convert(value, {conversion!r})\n"
            'result = apply_conversion("hello")\n'
        )
    # Interpolation constructor
    return (
        "from string.templatelib import Interpolation\n"
        "result = Interpolation(\n"
        f"    \"World\", {prop.expression!r}, {prop.conversion!r}, "
        f"{prop.format_spec!r}\n"
        ")\n"
    )


def _ref_render(prop: RenderTemplate, seeds: tuple[Seed, ...] | None) -> str:
    if seeds:
        preamble = _template_lines(seeds[0])
    else:
        preamble = _fallback_template()
    return (
        "from string.templatelib import Interpolation, Template, convert\n"
        "\n"
        "def render_template(template: Template) -> str:\n"
        "    parts: list[str] = []\n"
        "    for part in template:\n"
        "        if isinstance(part, str):\n"
        "            parts.append(part)\n"
        "        elif isinstance(part, Interpolation):\n"
        "            value = convert(part.value, part.conversion)\n"
        "            parts.append(format(value, part.format_spec))\n"
        '    return "".join(parts)\n'
        "\n"
        f"{preamble}\n"
        "result = render_template(template)\n"
    )


def _ref_join_static_parts(
    prop: JoinStaticParts, seeds: tuple[Seed, ...] | None
) -> str:
    preamble = _template_lines(seeds[0]) if seeds else _fallback_template()
    return f"{preamble}\nresult = {prop.separator!r}.join(template.strings)\n"


def _ref_compose_templates(
    prop: ComposeTemplates, seeds: tuple[Seed, ...] | None
) -> str:
    if seeds and len(seeds) >= 2:
        s1, s2 = seeds[0], seeds[1]
        preamble = (
            f"{_bindings_lines(s1)}\nt1 = {s1.literal}\n"
            f"{_bindings_lines(s2)}\nt2 = {s2.literal}\n"
        )
    else:
        preamble = 't1 = t"Hello "\nt2 = t"World"\n'
    if prop.result == "template":
        return preamble + "result = t1 + t2\n"
    if prop.result in {"strings", "values", "interpolations"}:
        return preamble + f"result = (t1 + t2).{prop.result}\n"
    return (
        "from string.templatelib import Interpolation, Template, convert\n\n"
        "def render_template(template: Template) -> str:\n"
        "    parts: list[str] = []\n"
        "    for part in template:\n"
        "        if isinstance(part, str):\n"
        "            parts.append(part)\n"
        "        elif isinstance(part, Interpolation):\n"
        "            value = convert(part.value, part.conversion)\n"
        "            parts.append(format(value, part.format_spec))\n"
        '    return "".join(parts)\n\n'
        f"{preamble}result = render_template(t1 + t2)\n"
    )


def _ref_negative(prop: NegativeControl, seeds: tuple[Seed, ...] | None) -> str:
    if seeds:
        literal = seeds[0].literal
        quote_pos = next(
            (i for i, ch in enumerate(literal) if ch in "'\""), None
        )
        if quote_pos is not None:
            prefix = literal[:quote_pos]
            fstring_prefix = prefix.replace("t", "f").replace("T", "F")
            fallback = fstring_prefix + literal[quote_pos:]
        else:
            fallback = literal
        preamble = _bindings_lines(seeds[0])
        if preamble:
            preamble += "\n"
        return f"{preamble}result = {fallback}\n"
    return 'name = "World"\nresult = f"Hello {name}"\n'


def _build_checks(intent: TaskIntent) -> tuple:
    """Derive CheckSpec entries from the intent."""
    checks: list[NameEquals | Raises] = []
    props = intent.properties

    if props and isinstance(props[0], NegativeControl):
        # Negative control: expect a NameEquals for result (it's an f-string
        # response used as a degenerate source)
        checks.append(NameEquals(name="result"))
        return tuple(checks)

    # Default: expect a successful NameEquals on 'result'
    checks.append(NameEquals(name="result"))
    return tuple(checks)


__all__ = ["build_task"]
