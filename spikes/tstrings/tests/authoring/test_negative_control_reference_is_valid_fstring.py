"""Every seed's negative-control reference must be a real f-string, not a t-string.

The final whole-branch review found that ``task_builder._ref_negative`` only
recognized the bare ``t"..."``/``t'...'`` prefixes when converting a seed's
t-string literal into its negative-control f-string reference. The seed
``rt"{path}\\Documents"`` added in this branch has an ``rt`` prefix, which fell
through to the ``else`` branch and left the literal unchanged — so the
negative-control task's gold answer was the t-string itself (a ``Template``
object), not an f-string (a ``str``), and it still qualified and shipped. This
test reproduces the reference-build step directly against every seed's actual
literal and bindings, so a prefix shape that isn't handled fails loudly here.
"""

import ast
from pathlib import Path

from satyrn_model.authoring.models import NegativeControl
from satyrn_model.authoring.seeds import read_seeds_jsonl
from satyrn_model.authoring.task_builder import _ref_negative

ROOT = Path(__file__).resolve().parents[2]


def test_every_seed_negative_control_reference_is_a_valid_fstring() -> None:
    seeds = [
        seed
        for path in (ROOT / "seeds/authored.jsonl", ROOT / "seeds/extracted.jsonl")
        for seed in read_seeds_jsonl(path)
    ]
    assert seeds, "expected seeds to be present"

    prop = NegativeControl(expected_solution_kind="fstring")

    failures: list[str] = []
    for seed in seeds:
        reference = _ref_negative(prop, (seed,))

        tree = ast.parse(reference)
        if any(isinstance(node, ast.TemplateStr) for node in ast.walk(tree)):
            failures.append(
                f"{seed.literal!r}: reference still contains a t-string:\n{reference}"
            )
            continue

        namespace: dict[str, object] = {}
        try:
            exec(reference, namespace)  # noqa: S102
        except Exception as exc:  # pragma: no cover - diagnostic path
            failures.append(f"{seed.literal!r}: reference failed to execute: {exc}")
            continue

        result = namespace.get("result")
        if not isinstance(result, str):
            failures.append(
                f"{seed.literal!r}: reference result is {type(result)!r}, not str"
            )

    assert not failures, "\n".join(failures)
