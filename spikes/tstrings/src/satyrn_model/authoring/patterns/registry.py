"""SP5 pattern registry: declarative patterns, classifier, and gates.

Patterns are reviewed source that lands in ``catalog.py``; they declare their
property specs, the composition labels they claim to contribute, and every
helper/template/renderer dependency they use. The classifier mechanically
derives labels from every ``Property`` variant — nothing self-declared is left
to game. ``validate_pattern`` enforces the cross-projection and classifier
gates; ``pattern_input_fingerprint`` feeds the approvals ledger and generated
cache, so editing any input invalidates both.
"""

import dataclasses
import hashlib
import json
from string.templatelib import Interpolation, Template, convert
from typing import Literal

from satyrn_model.domains.tstrings import render_fstring_equivalent

from ..models import (
    ComposeTemplates,
    Construct,
    Introspect,
    JoinStaticParts,
    NegativeControl,
    Property,
    RenderSubskill,
    RenderTemplate,
    SelectTemplateResult,
)

__all__ = [
    "Pattern",
    "PatternRegistry",
    "PatternValidationError",
    "PromptVariant",
    "PropertySpec",
    "build_properties",
    "classify",
    "classify_operation",
    "pattern_arity",
    "pattern_input_fingerprint",
    "prompt_variants",
    "validate_pattern",
]

GENERATOR_VERSION = "0.2.0"
POLICY_VERSION = 1
CONFIG_VERSION = 1
RENDER_CONTRACT_VERSION = 1

_SUBJECT_WORDS = ("strings", "values", "interpolations", "convert")


@dataclasses.dataclass(frozen=True)
class PropertySpec:
    """Declarative spec for one property the pattern will emit."""

    kind: Literal[
        "introspect",
        "render_template",
        "join_static_parts",
        "select_result",
        "render_subskill",
        "compose_templates",
        "construct",
        "negative",
    ]
    target: str = ".strings"  # Introspect
    index: int = 0  # Introspect
    field: str = "strings"  # Introspect
    separator: str = ""  # JoinStaticParts
    outcome: Literal[
        "template", "strings", "values", "joined_static", "rendered"
    ] = "template"  # SelectTemplateResult
    stage: Literal[
        "iterate_parts",
        "classify_parts",
        "convert_value",
        "format_value",
        "render_interpolation",
        "render_template",
    ] = "iterate_parts"  # RenderSubskill
    arity: Literal[2] = 2  # ComposeTemplates
    result: Literal[
        "template", "strings", "values", "interpolations", "rendered"
    ] = "template"  # ComposeTemplates
    operation: Literal["Interpolation", "convert"] = "Interpolation"  # Construct
    conversion: Literal["s", "r", "a"] | None = None  # Construct
    expression: str = "name"  # Construct
    format_spec: str = ""  # Construct


@dataclasses.dataclass(frozen=True)
class PromptVariant:
    """One reviewed instruction family for a generation pattern."""

    id: str
    text: str
    include_seed_context: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("PromptVariant.id must be non-empty")
        if not self.text or not self.text.strip():
            raise ValueError("PromptVariant.text must be non-empty")


@dataclasses.dataclass(frozen=True)
class Pattern:
    """A reviewed generation pattern: prompt + property specs + deps.

    ``labels`` are the composition strata this pattern claims to contribute;
    the classifier must derive the identical set from ``property_specs`` or
    validation fails. ``requires`` names every helper/template/renderer
    dependency the pattern uses; changing any of them changes the input
    fingerprint and invalidates approval and generated cache.
    """

    id: str
    description: str
    property_specs: tuple[PropertySpec, ...]
    labels: frozenset[str]
    role: Literal["consumer", "author"] = "consumer"
    requires: tuple[str, ...] = ()
    witnesses: tuple[str, ...] = ()
    prompt_variants: tuple[PromptVariant, ...] = ()

    def __post_init__(self) -> None:
        if not self.property_specs:
            raise ValueError("Pattern.property_specs must be non-empty")
        object.__setattr__(self, "property_specs", tuple(self.property_specs))
        object.__setattr__(self, "labels", frozenset(self.labels))
        object.__setattr__(self, "requires", tuple(self.requires))
        object.__setattr__(self, "witnesses", tuple(self.witnesses))
        object.__setattr__(self, "prompt_variants", tuple(self.prompt_variants))


def prompt_variants(pattern: Pattern) -> tuple[PromptVariant, ...]:
    """Return explicit families or the backward-compatible default family."""
    return pattern.prompt_variants or (
        PromptVariant(id="default", text=pattern.description),
    )


class PatternValidationError(ValueError):
    """A pattern failed a composition or cross-projection gate."""


def build_properties(specs: tuple[PropertySpec, ...]) -> tuple[Property, ...]:
    """Instantiate concrete ``Property`` variants from specs (Task 8 wires
    seed content into the reference; here properties are declarative)."""
    props: list[Property] = []
    for spec in specs:
        if spec.kind == "introspect":
            props.append(
                Introspect(target=spec.target, index=spec.index, field=spec.field)
            )
        elif spec.kind == "render_template":
            props.append(RenderTemplate())
        elif spec.kind == "join_static_parts":
            props.append(JoinStaticParts(separator=spec.separator))
        elif spec.kind == "select_result":
            props.append(SelectTemplateResult(outcome=spec.outcome))
        elif spec.kind == "render_subskill":
            props.append(RenderSubskill(stage=spec.stage))
        elif spec.kind == "compose_templates":
            props.append(ComposeTemplates(arity=spec.arity, result=spec.result))
        elif spec.kind == "construct":
            props.append(
                Construct(
                    operation=spec.operation,
                    conversion=spec.conversion,
                    expression=spec.expression,
                    format_spec=spec.format_spec,
                )
            )
        elif spec.kind == "negative":
            props.append(NegativeControl(expected_solution_kind="fstring"))
    return tuple(props)


def classify(properties: tuple[Property, ...]) -> frozenset[str]:
    """Mechanically derive composition labels from every Property variant."""
    labels: set[str] = set()
    for prop in properties:
        if isinstance(prop, Introspect):
            labels.add("introspect")
        elif isinstance(prop, RenderTemplate):
            labels.add("render_template")
        elif isinstance(prop, JoinStaticParts):
            labels.add("join_static_parts")
        elif isinstance(prop, SelectTemplateResult):
            labels.add("select_result")
        elif isinstance(prop, RenderSubskill):
            labels.add("render_subskill")
        elif isinstance(prop, ComposeTemplates):
            labels.add("compose_templates")
        elif isinstance(prop, Construct):
            labels.add("construct")
        elif isinstance(prop, NegativeControl):
            labels.add("negative")
    return frozenset(labels)


def classify_operation(properties: tuple[Property, ...]) -> str:
    """Return the concrete operation taught by a single-property task."""
    if len(properties) != 1:
        raise ValueError("pilot rows require exactly one concrete operation")
    prop = properties[0]
    if isinstance(prop, Introspect):
        return prop.target.lstrip(".")
    if isinstance(prop, RenderTemplate):
        return "render_template"
    if isinstance(prop, JoinStaticParts):
        return "joined_static"
    if isinstance(prop, SelectTemplateResult):
        return "render_template" if prop.outcome == "rendered" else prop.outcome
    if isinstance(prop, RenderSubskill):
        return prop.stage
    if isinstance(prop, ComposeTemplates):
        return "compose"
    if isinstance(prop, Construct):
        return "construct"
    return "negative"


def pattern_arity(pattern: Pattern) -> int:
    """The seed count every spec of the pattern consumes (uniform)."""
    arities = {
        spec.arity
        if spec.kind == "compose_templates"
        else 0
        if spec.kind == "construct"
        else 1
        for spec in pattern.property_specs
    }
    if len(arities) != 1:
        raise PatternValidationError(
            f"pattern {pattern.id!r} has mixed property arities: {arities}"
        )
    return next(iter(arities))


def _prompt_subjects(description: str) -> set[str]:
    return {w for w in _SUBJECT_WORDS if w in description.lower()}


def _check_subjects(specs: tuple[PropertySpec, ...]) -> set[str]:
    subjects: set[str] = set()
    for spec in specs:
        if spec.kind == "introspect":
            subjects.add(spec.target.lstrip(".").split(".")[0])
        elif spec.kind == "construct" and spec.operation == "convert":
            subjects.add("convert")
    return subjects


def validate_pattern(pattern: Pattern) -> None:
    """Enforce the gates: cross-projection, classifier, uniform arity.

    - Cross-projection: subject words claimed in the prompt must equal the
      subjects the checks introspect (``t"{v:{w}}"`` style precision).
    - Classifier: declared ``labels`` must equal the labels mechanically
      derived from the pattern's property specs.
    - Arity: all property specs must consume the same seed count.
    """
    # Uniform arity first (pattern_arity raises on mixed).
    pattern_arity(pattern)

    check_s = _check_subjects(pattern.property_specs)
    variants = prompt_variants(pattern)
    variant_ids = [variant.id for variant in variants]
    if len(set(variant_ids)) != len(variant_ids):
        raise PatternValidationError(
            f"pattern {pattern.id!r} has duplicate prompt-family IDs"
        )
    for variant in variants:
        prompt_s = _prompt_subjects(variant.text)
        if prompt_s and check_s and prompt_s != check_s:
            raise PatternValidationError(
                f"pattern {pattern.id!r} prompt family {variant.id!r} claims "
                f"{sorted(prompt_s)} but checks target {sorted(check_s)}"
            )

    derived = classify(build_properties(pattern.property_specs))
    if pattern.labels != derived:
        raise PatternValidationError(
            f"pattern {pattern.id!r} declares labels {sorted(pattern.labels)} "
            f"but its properties classify as {sorted(derived)}"
        )
    _validate_witnesses(pattern)


def _validate_witnesses(pattern: Pattern) -> None:
    """Execute the semantic fixtures required by each typed operation."""
    required_by_kind = {
        "render_template": {
            "render-conversion-format",
            "reject-template-str",
            "reject-static-join",
            "reject-omitted-conversion",
        },
        "join_static_parts": {"join-static-intent"},
        "select_result": {"contrastive-result"},
        "render_subskill": {"render-subskill"},
        "compose_templates": {"compose-template"},
        "negative": {"negative-control"},
    }
    introspect_witnesses = {
        ".strings": "introspect-strings",
        ".values": "introspect-values",
        ".interpolations": "introspect-interpolations",
    }
    construct_witnesses = {
        "convert": "construct-convert",
        "Interpolation": "construct-interpolation",
    }
    expected: set[str] = set()
    for spec in pattern.property_specs:
        if spec.kind == "introspect":
            try:
                expected.add(introspect_witnesses[spec.target])
            except KeyError:
                raise PatternValidationError(
                    f"pattern {pattern.id!r} has no witness for "
                    f"introspection target {spec.target!r}"
                ) from None
        elif spec.kind == "construct":
            try:
                expected.add(construct_witnesses[spec.operation])
            except KeyError:
                raise PatternValidationError(
                    f"pattern {pattern.id!r} has no witness for "
                    f"construction operation {spec.operation!r}"
                ) from None
        else:
            expected.update(required_by_kind[spec.kind])
    missing = expected - set(pattern.witnesses)
    if missing:
        raise PatternValidationError(
            f"pattern {pattern.id!r} lacks witness(es): {sorted(missing)}"
        )

    value = "x"
    template = t"<{value!r:>6}>"
    rendered = render_fstring_equivalent(template)
    interpolation = Interpolation(value, "value", "r", ">6")
    fstring_equivalent = f"<{value!r:>6}>"
    checks = {
        "render-conversion-format": rendered == "<   'x'>",
        "reject-template-str": str(template) != rendered,
        "reject-static-join": "".join(template.strings) != rendered,
        "reject-omitted-conversion": "".join(
            part if isinstance(part, str) else format(part.value, part.format_spec)
            for part in template
        )
        != rendered,
        "join-static-intent": "".join(template.strings) == "<>" and "<>" != rendered,
        "compose-template": isinstance(t"left" + t"{value}", Template),
        "introspect-strings": template.strings == ("<", ">"),
        "introspect-values": template.values == ("x",),
        "introspect-interpolations": template.interpolations
        == (template.interpolations[0],),
        "construct-convert": convert(value, "r") == repr(value),
        "construct-interpolation": (
            interpolation.value == value
            and interpolation.expression == "value"
            and interpolation.conversion == "r"
            and interpolation.format_spec == ">6"
        ),
        "negative-control": (
            fstring_equivalent == rendered
            and not isinstance(fstring_equivalent, Template)
        ),
        "contrastive-result": (
            template is not rendered
            and template.strings == ("<", ">")
            and template.values == ("x",)
            and "".join(template.strings) == "<>"
        ),
        "render-subskill": (
            tuple(template) == ("<", template.interpolations[0], ">")
            and convert(interpolation.value, interpolation.conversion) == repr(value)
            and format(repr(value), interpolation.format_spec) == "   'x'"
        ),
    }
    failed = [
        witness for witness in pattern.witnesses if not checks.get(witness, False)
    ]
    if failed:
        raise PatternValidationError(
            f"pattern {pattern.id!r} failed witness(es): {sorted(failed)}"
        )


def pattern_input_fingerprint(
    pattern: Pattern,
    *,
    generator_version: str = GENERATOR_VERSION,
    policy_version: int = POLICY_VERSION,
    config_version: int = CONFIG_VERSION,
    render_contract_version: int = RENDER_CONTRACT_VERSION,
) -> str:
    """Fingerprint of every generation input for this pattern.

    Includes pattern source (specs/labels/requires), generator version, policy
    and configuration versions, and render-contract version. Editing any input
    invalidates approval and generated cache.
    """
    material = {
        "id": pattern.id,
        "description": pattern.description,
        "specs": [dataclasses.asdict(s) for s in pattern.property_specs],
        "labels": sorted(pattern.labels),
        "role": pattern.role,
        "requires": list(pattern.requires),
        "witnesses": list(pattern.witnesses),
        "generator_version": generator_version,
        "policy_version": policy_version,
        "config_version": config_version,
        "render_contract_version": render_contract_version,
    }
    if pattern.prompt_variants:
        material["prompt_variants"] = [
            dataclasses.asdict(variant) for variant in pattern.prompt_variants
        ]
    payload = json.dumps(material, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class PatternRegistry:
    """Trusted registry of reviewed patterns, keyed by id."""

    def __init__(self) -> None:
        self._patterns: dict[str, Pattern] = {}

    def register(self, pattern: Pattern) -> None:
        validate_pattern(pattern)
        self._patterns[pattern.id] = pattern

    def get(self, pattern_id: str) -> Pattern:
        try:
            return self._patterns[pattern_id]
        except KeyError:
            raise KeyError(f"pattern {pattern_id!r} is not registered") from None

    def ids(self) -> tuple[str, ...]:
        return tuple(self._patterns)

    def __bool__(self) -> bool:
        return bool(self._patterns)
