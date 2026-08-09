"""Every seed's format_spec must be one Python's format() actually accepts.

The final whole-branch review executed the pipeline's real reference-render
code (task_builder.py's ``format(value, part.format_spec)``) against every
new seed and found 5 whose format_spec was a library-specific convention
(``:safe``, ``:%like%``) rather than a real Python format spec. Those raise
``ValueError: Invalid format specifier`` and would silently drop out at
build time (``reports/dropped.jsonl``), invisible to every other test. This
test reproduces that render step directly against every seed's actual
bindings, so a bad format_spec fails loudly here instead.
"""

from pathlib import Path

from satyrn_model.authoring.seeds import read_seeds_jsonl

ROOT = Path(__file__).resolve().parents[2]


def _build_template(literal: str, bindings: tuple[tuple[str, str], ...]):
    """Compile a seed's literal t-string with its bindings evaluated in order."""
    namespace: dict[str, object] = {}
    for name, expr in bindings:
        namespace[name] = eval(expr, {}, namespace)  # noqa: S307
    return eval(literal, {}, namespace)  # noqa: S307


def test_every_seed_format_spec_is_a_valid_python_format_spec() -> None:
    seeds = [
        seed
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for seed in read_seeds_jsonl(path)
    ]
    assert seeds, "expected seeds to be present"

    failures: list[str] = []
    for seed in seeds:
        try:
            template = _build_template(seed.literal, seed.bindings)
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(f"{seed.literal!r}: template construction failed: {exc}")
            continue

        for interpolation in template.interpolations:
            try:
                format(interpolation.value, interpolation.format_spec)
            except ValueError as exc:
                failures.append(
                    f"{seed.literal!r}: format_spec {interpolation.format_spec!r} "
                    f"is not a valid Python format spec: {exc}"
                )

    assert not failures, "\n".join(failures)
