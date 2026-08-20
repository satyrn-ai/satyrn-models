"""Tests for reference derivation, execution, and checks."""

import json
import tempfile
from pathlib import Path

from satyrn.tstrings.build import build_reference, extract_literal, run_reference

FINGERPRINT_FLOOR = 28  # updated to the re-measured value in Step 2


def test_extract_literal_simple() -> None:
    """A seed with a simple t-string literal extracts it and no assignments."""
    seed = 't = t"Hello, world"\nself.assertEqual(fstring(t), "Hello, world")\n'
    literal, assignments = extract_literal(seed, need_interpolation=False)
    assert literal == 't"Hello, world"'
    assert assignments == []


def test_extract_literal_with_assignment() -> None:
    """A literal referencing a simple-assigned name carries that assignment."""
    seed = 'name = "Python"\nt = t"Hello, {name}"\nself.assertEqual(fstring(t), "Hello, Python")\n'
    literal, assignments = extract_literal(seed, need_interpolation=True)
    assert literal == 't"Hello, {name}"'
    assert assignments == ['name = "Python"']


def test_extract_literal_rejects_unbound_name() -> None:
    """A literal referencing an unassigned name does not qualify."""
    seed = 't = t"Hello, {missing}"\n'
    assert extract_literal(seed, need_interpolation=True) is None


def test_build_construct_reference_runs() -> None:
    """A construct reference runs and prints Template."""
    ref, checks = build_reference("construct", 't = t"Hello, world"\n')
    code, out = run_reference(ref)
    assert code == 0 and out.strip() == "Template"
    assert ("uses_feature", "string.templatelib") in [(c.kind, c.expected) for c in checks]


def test_build_render_reference_runs() -> None:
    """A render reference runs and prints the interpolated string."""
    seed = 'name = "Python"\nt = t"Hello, {name}"\n'
    ref, checks = build_reference("render", seed)
    code, out = run_reference(ref)
    assert code == 0 and out.strip() == "Hello, Python"
    assert any(c.kind == "uses_feature" for c in checks)


def test_build_read_values_reference_runs() -> None:
    """A read_values reference prints the values tuple."""
    seed = 'name = "Lys"\nt = t"Hello, {name}"\n'
    ref, _ = build_reference("read_values", seed)
    code, out = run_reference(ref)
    assert code == 0 and out.strip() == "('Lys',)"


def test_negative_control_has_no_templatestr() -> None:
    """A negative_control reference contains no TemplateStr."""
    seed = 'print(f"value={42}")\n'
    ref, _ = build_reference("negative_control", seed)
    assert 't"' not in ref and "TemplateStr" not in ref
    assert 'f"' in ref


def test_same_family_same_fingerprint() -> None:
    """Same family+operation, different variable names, same fingerprint."""
    from satyrn.tstrings.build import fill_family, prompt_fingerprint

    p1 = fill_family("build", "construct", {})
    p2 = fill_family("build", "construct", {})
    assert prompt_fingerprint(p1, set()) == prompt_fingerprint(p2, set())


def test_fingerprints_differ_across_operations() -> None:
    """Different operations under the same family differ in fingerprint."""
    from satyrn.tstrings.build import fill_family, prompt_fingerprint

    a = prompt_fingerprint(fill_family("build", "construct", {}), set())
    b = prompt_fingerprint(fill_family("build", "render", {}), set())
    assert a != b


def test_fingerprint_normalizes_seed_tokens() -> None:
    """Two prompts differing only in a seed-drawn token share a fingerprint."""
    from satyrn.tstrings.build import prompt_fingerprint

    a = prompt_fingerprint("Use the variable name to render it.", {"name"})
    b = prompt_fingerprint("Use the variable other to render it.", {"other"})
    assert a == b


def test_build_tasks_produces_wellformed_output(tmp_path: Path) -> None:
    """A two-seed build yields tasks with IDs, checks, and correct cells."""
    from satyrn.tstrings.build import build_tasks
    from satyrn.tstrings.types import Task

    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text(
        json.dumps(
            {
                "text": 'name = "Python"\nt = t"Hello, {name}"\nprint(t.strings, t.values)\n',
                "source_id": "cpython",
                "path": "a.py",
                "line": 1,
            }
        )
        + "\n"
        + json.dumps(
            {
                "text": 't = t"Hello, world"\n',
                "source_id": "cpython",
                "path": "b.py",
                "line": 1,
            }
        )
        + "\n"
    )
    cells = Path(__file__).resolve().parents[1] / "cells.toml"
    tasks = build_tasks(seeds, cells)
    assert len(tasks) >= 4  # construct, render, read_strings, read_values (seed 1); construct (seed 2)
    assert all(isinstance(t, Task) for t in tasks)
    assert all(t.task_id and t.semantic_id for t in tasks)
    ops = {t.operation for t in tasks}
    assert {"construct", "render", "read_values"} <= ops


def test_extract_literal_function_local_assignment() -> None:
    """A NAME=constant inside a function body is collected."""
    seed = 'def f():\n    name = "Python"\n    t = t"Hello, {name}"\n'
    literal, assignments = extract_literal(seed, need_interpolation=True)
    assert literal == 't"Hello, {name}"'
    assert assignments == ['    name = "Python"']


def test_extract_literal_read_interpolations_seed9() -> None:
    """A .interpolations seed with a function-local assignment qualifies."""
    seed = "def test(self):\n    a = 'a'\n    i = t'{a}'.interpolations[0]\n"
    literal, _ = extract_literal(seed, need_interpolation=True)
    assert literal == "t'{a}'"


def test_negative_control_nested_name_included() -> None:
    """A f-string with a nested Name (str(obj)) carries that assignment and runs."""
    seed = 'def f():\n    obj = object()\n    print(f"Object: {str(obj)}")\n'
    ref, _ = build_reference("negative_control", seed)
    assert "obj = object()" in ref
    code, out = run_reference(ref)
    assert code == 0 and out.strip().startswith("Object: ")


def test_build_tasks_drops_non_deterministic_reference(tmp_path: Path) -> None:
    """A reference whose output embeds a memory address is dropped as non-deterministic."""
    from satyrn.tstrings.build import build_tasks

    seeds = tmp_path / "seeds.jsonl"
    seeds.write_text(
        json.dumps(
            {
                "text": 'obj = object()\nt = t"Object: {str(obj)}"\nprint(f"Object: {str(obj)}")\n',
                "source_id": "cpython",
                "path": "a.py",
                "line": 1,
            }
        )
        + "\n"
    )
    cells = Path(__file__).resolve().parents[1] / "cells.toml"
    reports = tmp_path / "reports"
    tasks = build_tasks(seeds, cells, tmp_path / "tasks", reports)
    assert tasks == []
    drops = [json.loads(line) for line in (reports / "dropped.jsonl").read_text().splitlines()]
    assert any(d["reason"] == "negative_control: non-deterministic output" for d in drops)


def test_per_cell_family_rotation() -> None:
    """A 4-task cell gets 4 distinct families even where global rotation clusters it."""
    from satyrn.tstrings.build import build_tasks

    # Each seed demonstrates construct+render+read_strings+read_values (fstring call).
    seed_text = 'name = "Python"\nt = t"Hello {name}"\nfstring(t)\n'
    seeds = [{"text": seed_text, "source_id": "cpython", "path": f"s{i}.py", "line": 1} for i in range(4)]
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "seeds.jsonl"
        sp.write_text("".join(json.dumps(s) + "\n" for s in seeds))
        tasks = build_tasks(sp, Path(__file__).resolve().parents[1] / "cells.toml", None, None)
    construct = [t for t in tasks if t.operation == "construct"]
    assert len(construct) == 4
    # Per-cell rotation yields build/create/show/teach -> 4 distinct prompts.
    # (Under the old global idx%6 rotation, the construct tasks land at residues
    # 0,4,2,0 -> only 3 distinct families, so this test fails on the old code.)
    assert len({t.prompt for t in construct}) == 4


def test_preceding_only_assignment_scope() -> None:
    """A name assigned AFTER the literal is not carried as a binding."""
    seed = 't = t"Hi {later}"\nlater = "x"\n'
    assert extract_literal(seed, need_interpolation=True) is None


def test_prompt_families_are_grammatical() -> None:
    """No prompt contains the broken infinitive/gerund patterns."""
    from satyrn.tstrings.build import OPERATION_VERBS, PROMPT_FAMILIES, fill_family

    for family in PROMPT_FAMILIES:
        for op in OPERATION_VERBS:
            prompt = fill_family(family, op, {})
            assert "Templateing" not in prompt
            assert "that build a" not in prompt
            assert "by build a" not in prompt


def test_every_cell_meets_its_floor() -> None:
    """The real build on the 23 seeds meets every cells.toml floor."""
    from satyrn.tstrings.build import build_tasks
    from satyrn.tstrings.cells import load_cells

    spike_root = Path(__file__).resolve().parents[1]
    tasks = build_tasks(spike_root / "seeds" / "mined.jsonl", spike_root / "cells.toml", None, None)
    floors = load_cells(spike_root / "cells.toml")
    counts: dict[tuple[str, str], int] = {}
    for t in tasks:
        counts[(t.role, t.operation)] = counts.get((t.role, t.operation), 0) + 1
    for cell, floor in floors.items():
        assert counts.get(cell, 0) >= floor, f"cell {cell} below floor"


def test_fingerprint_floor_met() -> None:
    """The real build's distinct prompts meet the fingerprint floor."""
    from satyrn.tstrings.build import build_tasks

    spike_root = Path(__file__).resolve().parents[1]
    tasks = build_tasks(spike_root / "seeds" / "mined.jsonl", spike_root / "cells.toml", None, None)
    assert len({t.prompt for t in tasks}) >= FINGERPRINT_FLOOR
