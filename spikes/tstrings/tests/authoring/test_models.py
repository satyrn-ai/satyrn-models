"""SP5 Task 2: local model for occurrences, seeds, and task intent.

Focused command: ``uv run python -m pytest tests/authoring/test_models.py -q``.
"""

import json
from pathlib import Path

import pytest

from satyrn_model.authoring.models import (
    Seed,
    SeedOccurrence,
    SourceOrigin,
    occurrence_id,
    seed_id,
)


def test_same_seed_two_origins_is_not_lost() -> None:
    """A seed extracted from two different source locations preserves both."""
    from satyrn_model.authoring.seeds import normalize_seeds

    literal = 't"Hello {name}"'
    bindings = (("name", '"world"'),)
    sid = seed_id(literal, bindings)

    origin_a = SourceOrigin(
        source_id="cpython-v3.14.5",
        path="Lib/test/test_templatelib.py",
        line_start=10,
        line_end=10,
        license="PSF-2.0",
    )
    origin_b = SourceOrigin(
        source_id="cpython-v3.14.5",
        path="Lib/test/test_templatelib.py",
        line_start=50,
        line_end=50,
        license="PSF-2.0",
    )

    occ_a = SeedOccurrence(
        id=occurrence_id("cpython-v3.14.5", "Lib/test/test_templatelib.py", 10, 10),
        seed_id=sid,
        literal=literal,
        free_names=("name",),
        bindings=bindings,
        kind="extracted",
        origin=origin_a,
    )
    occ_b = SeedOccurrence(
        id=occurrence_id("cpython-v3.14.5", "Lib/test/test_templatelib.py", 50, 50),
        seed_id=sid,
        literal=literal,
        free_names=("name",),
        bindings=bindings,
        kind="extracted",
        origin=origin_b,
    )

    seeds = normalize_seeds([occ_a, occ_b])

    assert len(seeds) == 1, "same seed from two origins must produce one Seed"
    seed = seeds[0]
    assert seed.id == sid
    assert seed.literal == literal
    assert seed.bindings == bindings
    assert set(seed.occurrence_ids) == {occ_a.id, occ_b.id}


def test_construct_property_is_representable() -> None:
    """``Construct(Interpolation)`` and ``Construct(convert)`` are valid properties."""
    from satyrn_model.authoring.models import (
        Construct,
        PolicyIntent,
        TaskIntent,
    )

    interpolation_intent = TaskIntent(
        id="construct-interpolation",
        description="construct an Interpolation object",
        properties=(Construct(operation="Interpolation"),),
        policy_intent=PolicyIntent(
            requires_template=False,
            templatelib_apis_used=frozenset({"interpolations"}),
        ),
    )
    assert interpolation_intent.properties[0].operation == "Interpolation"

    convert_intent = TaskIntent(
        id="construct-convert",
        description="call convert()",
        properties=(Construct(operation="convert"),),
        policy_intent=PolicyIntent(
            requires_template=False,
            templatelib_apis_used=frozenset({"convert"}),
        ),
    )
    assert convert_intent.properties[0].operation == "convert"


def test_contrastive_and_render_subskill_properties_are_representable() -> None:
    from satyrn_model.authoring.models import RenderSubskill, SelectTemplateResult

    assert SelectTemplateResult(outcome="strings").outcome == "strings"
    assert RenderSubskill(stage="render_interpolation").stage == (
        "render_interpolation"
    )


def test_negative_control_is_not_template_required() -> None:
    """Negative-control tasks must not require a template in the solution."""
    from satyrn_model.authoring.models import (
        NegativeControl,
        PolicyIntent,
        TaskIntent,
    )

    nc = NegativeControl(expected_solution_kind="f-string")
    assert nc.requires_template is False, (
        "negative-control property must carry requires_template=False"
    )

    intent = TaskIntent(
        id="neg-ctrl",
        description="task where a t-string is the wrong answer",
        properties=(nc,),
        policy_intent=PolicyIntent(
            requires_template=False,
            templatelib_apis_used=frozenset(),
        ),
    )
    assert intent.policy_intent.requires_template is False


def test_generated_exercise_enforces_arity() -> None:
    """Each property's arity must match the number of seeds."""
    from satyrn_model.authoring.models import (
        ComposeTemplates,
        GeneratedExercise,
        RenderTemplate,
    )

    seed_one = Seed(
        id="s1",
        literal="t'{x}'",
        free_names=("x",),
        bindings=(("x", "1"),),
        occurrence_ids=("occ1",),
        kind="authored",
    )
    seed_two = Seed(
        id="s2",
        literal="t'{y}'",
        free_names=("y",),
        bindings=(("y", "2"),),
        occurrence_ids=("occ2",),
        kind="authored",
    )

    # Full rendering requires 1 seed — ok.
    GeneratedExercise(
        id="ex-ok",
        pattern_id="p",
        seeds=(seed_one,),
        properties=(RenderTemplate(),),
    )

    # Composition requires >=2 seeds — fails with 1.
    with pytest.raises(ValueError, match=r"ComposeTemplates.*arity"):
        GeneratedExercise(
            id="ex-bad",
            pattern_id="p",
            seeds=(seed_one,),
            properties=(ComposeTemplates(),),
        )

    # Composition with 2 seeds — ok.
    GeneratedExercise(
        id="ex-ok2",
        pattern_id="p",
        seeds=(seed_one, seed_two),
        properties=(ComposeTemplates(),),
    )


def test_source_candidate_preserves_all_check_intents() -> None:
    """A source candidate must preserve every assertion, never just one."""

    from satyrn_model.authoring.models import (
        LocalCheckIntent,
        PolicyIntent,
        RenderTemplate,
        SourceEvidence,
        SourceExerciseCandidate,
        SourceOrigin,
        TaskIntent,
    )

    origin = SourceOrigin(
        source_id="cpython-v3.14.5",
        path="Lib/test/test_templatelib.py",
        line_start=10,
        line_end=12,
        license="PSF-2.0",
    )
    evidence = SourceEvidence(function_name="test_thing")
    intent = TaskIntent(
        id="multi-check",
        description="a task with two checks",
        properties=(RenderTemplate(),),
        policy_intent=PolicyIntent(
            requires_template=True,
            templatelib_apis_used=frozenset({"strings", "values"}),
        ),
    )

    # Two independent checks from the same method — preserved.
    candidate = SourceExerciseCandidate(
        id="c1",
        origin=origin,
        evidence=evidence,
        intent=intent,
        check_intents=(
            LocalCheckIntent(kind="equals", target="template.strings[0]"),
            LocalCheckIntent(kind="equals", target="template.values[0]"),
        ),
    )
    assert len(candidate.check_intents) == 2


def test_seed_jsonl_round_trip_preserves_tuples_and_origins(tmp_path: Path) -> None:
    """Seeds serialized to JSONL and back keep tuples and all occurrence ids."""

    from satyrn_model.authoring.seeds import read_seeds_jsonl, write_seeds_jsonl

    seed = Seed(
        id="abc123",
        literal="t'Hello {name}'",
        free_names=("name",),
        bindings=(("name", "'world'"),),
        occurrence_ids=("occ-a", "occ-b"),
        kind="authored",
    )
    path = tmp_path / "seeds.jsonl"
    write_seeds_jsonl([seed], path)

    raw = path.read_text(encoding="utf-8")
    assert raw.count("\n") == 1  # one line per seed
    data = json.loads(raw.splitlines()[0])
    assert isinstance(data["bindings"], list)  # JSON arrays, not tuples
    assert isinstance(data["occurrence_ids"], list)

    loaded = read_seeds_jsonl(path)
    assert len(loaded) == 1
    assert loaded[0] == seed  # tuple fields restored in __post_init__


def test_seed_id_is_stable() -> None:
    """Content-derived IDs are deterministic — same input, same output."""
    assert seed_id("t'{x}'", (("x", "1"),)) == seed_id("t'{x}'", (("x", "1"),))
    assert len(seed_id("t'{x}'", ())) == 64

    oid = occurrence_id("s", "p.py", 1, 1)
    assert oid == occurrence_id("s", "p.py", 1, 1)
    assert oid != occurrence_id("s", "p.py", 2, 1)
