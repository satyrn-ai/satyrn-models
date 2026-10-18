"""Tests for the execution layer and structured outcome."""

import json
from pathlib import Path

from satyrn.tstrings.gate import (
    _EXECUTOR_TIMEOUT,
    Qualified,
    VacuityUntested,
    Vacuous,
    _append_drops,
    _subprocess_executor,
    degenerate_conversion_omission,
    degenerate_static_join,
    gate_tasks,
    qualify,
    run_candidate,
)
from satyrn.tstrings.types import Accepted, Check, InfrastructureFailure, Provenance, Rejection, Task

PROV = Provenance(source_id="cpython", path="x.py", line=1, license="PSF-2.0")

GOOD = Task(
    prompt="p",
    reference='from string.templatelib import Template\nprint(type(t"x").__name__)',
    checks=(
        Check(kind="uses_feature", expected="string.templatelib"),
        Check(kind="expected_stdout", expected="Template\n"),
    ),
    role="consumer",
    operation="render",
    provenance=PROV,
    task_id="a" * 64,
    semantic_id="b" * 64,
)

FSTRING_SOLVABLE = Task(
    prompt="p",
    reference='print(f"hello")',
    checks=(Check(kind="expected_stdout", expected="hello\n"),),
    role="consumer",
    operation="render",
    provenance=PROV,
    task_id="c" * 64,
    semantic_id="d" * 64,
)

INTERPOLATED = Task(
    prompt="p",
    reference=(
        "from string.templatelib import Template, Interpolation\n"
        "\n"
        "def _convert(value, conversion):\n"
        '    if conversion == "a":\n'
        "        return ascii(value)\n"
        '    if conversion == "r":\n'
        "        return repr(value)\n"
        '    if conversion == "s":\n'
        "        return str(value)\n"
        "    return value\n"
        "\n"
        "def _render(template):\n"
        "    parts = []\n"
        "    for item in template:\n"
        "        if isinstance(item, str):\n"
        "            parts.append(item)\n"
        "        elif isinstance(item, Interpolation):\n"
        "            parts.append(format(_convert(item.value, item.conversion), item.format_spec))\n"
        '    return "".join(parts)\n'
        "\n"
        'x = "42"\n'
        't = t"value={x!r}"\n'
        "print(_render(t))\n"
    ),
    checks=(
        Check(kind="uses_feature", expected="string.templatelib"),
        Check(kind="expected_stdout", expected="value='42'\n"),
    ),
    role="consumer",
    operation="render",
    provenance=PROV,
    task_id="g" * 64,
    semantic_id="h" * 64,
)


def test_subprocess_executor_returns_stdout() -> None:
    """The subprocess executor captures and returns a program's stdout."""
    assert _subprocess_executor(10)("print('hi')").strip() == "hi"


def test_subprocess_executor_timeout_returns_sentinel() -> None:
    """A subprocess executor that times out returns the timeout sentinel."""
    assert _subprocess_executor(1)("import time\ntime.sleep(2)") == _EXECUTOR_TIMEOUT


def test_known_good_accepted() -> None:
    """A candidate that uses t-strings and passes its checks is accepted."""
    code = 'x = t"Hello"\nprint("done")'
    checks = (Check(kind="uses_feature", expected="string.templatelib"),)
    outcome = run_candidate(code, checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Accepted)


def test_uses_feature_failure_rejected_semantically() -> None:
    """A candidate missing the required feature is rejected at the semantic stage."""
    code = 'print("no t-strings here")'
    checks = (Check(kind="uses_feature", expected="string.templatelib"),)
    outcome = run_candidate(code, checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "semantic_check"


def test_syntax_error_rejected() -> None:
    """A candidate that fails to parse is rejected at the syntax stage."""
    checks = (Check(kind="uses_feature", expected="string.templatelib"),)
    outcome = run_candidate("x =", checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "syntax"


def test_runtime_crash_rejected_at_runtime() -> None:
    """A candidate that raises at runtime is rejected at the runtime stage."""
    checks = (Check(kind="uses_feature", expected="string.templatelib"),)
    outcome = run_candidate("print(undefined_name)", checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "runtime"


def test_timeout_is_infrastructure_failure() -> None:
    """A candidate that exceeds the timeout is an infrastructure failure."""
    code = "import time\ntime.sleep(2)"
    checks = (Check(kind="uses_feature", expected="string.templatelib"),)
    outcome = run_candidate(code, checks, executor=_subprocess_executor(1))
    assert isinstance(outcome, InfrastructureFailure)


def test_mid_run_json_does_not_corrupt_verdict() -> None:
    """A candidate printing JSON mid-run cannot displace the final verdict."""
    code = 'print(\'{"x": 1}\')\nprint("done")'
    checks = (Check(kind="expected_stdout", expected='{"x": 1}\ndone\n'),)
    outcome = run_candidate(code, checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Accepted)


def test_good_task_qualifies() -> None:
    """A task whose degenerates all fail semantically qualifies."""
    qualification = qualify(GOOD, executor=_subprocess_executor(10))
    assert isinstance(qualification, Qualified)
    assert qualification.degenerates_run == 5


def test_interpolated_task_qualifies() -> None:
    """An interpolated t-string reference still defeats all five degenerates."""
    qualification = qualify(INTERPOLATED, executor=_subprocess_executor(10))
    assert isinstance(qualification, Qualified)
    assert qualification.degenerates_run == 5


def test_interpolated_static_join_drops_interpolation() -> None:
    """static_join keeps only static parts, dropping the interpolated value."""
    stdout = _subprocess_executor(10)(degenerate_static_join(INTERPOLATED))
    assert stdout == "value=\n"


def test_interpolated_conversion_omission_drops_conversion() -> None:
    """conversion_omission renders via str, dropping the !r conversion."""
    code = degenerate_conversion_omission(INTERPOLATED)
    assert _subprocess_executor(10)(code) == "value=42\n"
    outcome = run_candidate(code, INTERPOLATED.checks, executor=_subprocess_executor(10))
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "semantic_check"


def test_fstring_solvable_is_vacuous() -> None:
    """A task solvable by an f-string is rejected as vacuous."""
    assert isinstance(qualify(FSTRING_SOLVABLE, executor=_subprocess_executor(10)), Vacuous)


def test_import_crash_is_vacuity_untested() -> None:
    """A task whose reference crashes at import cannot be proven."""
    bad = Task(
        prompt="p",
        reference="import definitely_missing\n",
        checks=(Check(kind="uses_feature", expected="string.templatelib"),),
        role="consumer",
        operation="render",
        provenance=PROV,
        task_id="e" * 64,
        semantic_id="f" * 64,
    )
    assert isinstance(qualify(bad, executor=_subprocess_executor(10)), VacuityUntested)


def test_negative_control_no_templatestr_qualifies() -> None:
    """A negative_control reference without a TemplateStr qualifies."""
    nc = Task(
        prompt="p",
        reference='print(f"value={42}")',
        checks=(Check(kind="expected_stdout", expected="value=42\n"),),
        role="consumer",
        operation="negative_control",
        provenance=PROV,
        task_id="1" * 64,
        semantic_id="2" * 64,
    )
    qualification = qualify(nc, executor=_subprocess_executor(10))
    assert isinstance(qualification, Qualified)
    assert qualification.degenerates_run == 0


def test_negative_control_with_templatestr_rejected() -> None:
    """A negative_control reference containing a TemplateStr is rejected."""
    nc = Task(
        prompt="p",
        reference='print(type(t"x").__name__)',
        checks=(Check(kind="expected_stdout", expected="Template\n"),),
        role="consumer",
        operation="negative_control",
        provenance=PROV,
        task_id="3" * 64,
        semantic_id="4" * 64,
    )
    assert isinstance(qualify(nc, executor=_subprocess_executor(10)), VacuityUntested)


def test_gate_tasks_records_drops_with_reason() -> None:
    """gate_tasks splits qualified tasks from drops carrying a reason."""
    qualified, drops = gate_tasks([GOOD, FSTRING_SOLVABLE], executor=_subprocess_executor(10))
    assert qualified == [GOOD]
    assert len(drops) == 1
    assert "reason" in drops[0]


def test_drop_write_is_idempotent(tmp_path: Path) -> None:
    """Re-running the drop write does not duplicate task_ids."""
    _qualified, drops = gate_tasks([GOOD, FSTRING_SOLVABLE], executor=lambda code: "")
    path = tmp_path / "dropped.jsonl"
    _append_drops(path, drops)
    _append_drops(path, drops)
    lines = path.read_text().strip().splitlines()
    task_ids = [json.loads(line)["task_id"] for line in lines]
    assert len(lines) == len(drops)
    assert len(task_ids) == len(set(task_ids))
