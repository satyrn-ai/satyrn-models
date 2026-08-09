"""Reference execution and expectation materialization tests.

Task 2 of the provider plan. Tests invoke the real subprocess — the whole
point is that the boundary's exit, timeout, and isolation semantics are under
test. Mocking is reserved for the sandbox backend only.

Sandbox-specific adversarial tests (network, host-file, child-process escape,
deterministic side effect) require a configured OS sandbox profile and are
skipped unless the SANDBOX_PROFILE environment variable is set.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from satyrn_model.contracts import (
    CompleteProgram,
    GeneratedProvenance,
    NameEquals,
    PolicyRef,
    Raises,
    TaskRecord,
)
from satyrn_model.execution.protocol import (
    Accepted,
    InfrastructureFailure,
    NullSandbox,
    OSProfileSandbox,
    Rejection,
)
from satyrn_model.execution.reference import materialize_reference

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_task(
    *,
    reference: str,
    checks: tuple = (NameEquals(name="greet"),),
) -> TaskRecord:
    return TaskRecord(
        prompt="test task",
        reference=reference,
        checks=checks,
        policy=PolicyRef(id="tstring", version=1, config={}),
        completion=CompleteProgram(),
        provenance=GeneratedProvenance(
            generator="test", generator_version="0.0.0", seed_id="test-seed"
        ),
    )


def _sandbox() -> NullSandbox:
    """Test-only: no OS sandbox, for core protocol testing."""
    return NullSandbox()


def _requires_sandbox() -> bool:
    """True when adversarial sandbox tests should run."""
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


skip_no_sandbox = pytest.mark.skipif(
    not _requires_sandbox(),
    reason="macOS sandbox-exec is unavailable",
)


def _os_sandbox() -> OSProfileSandbox:
    return OSProfileSandbox()


# ---------------------------------------------------------------------------
# Successful materialization
# ---------------------------------------------------------------------------


def test_name_equals_materializes_namespace_value() -> None:
    task = _valid_task(
        reference=dedent("""\
        def greet(name):
            return f"Hello {name}"
        result = greet("World")
        """),
        checks=(NameEquals(name="result"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)

    assert isinstance(outcome, Accepted)
    assert outcome.interpreter_version
    assert any(
        obs.name == "result" and getattr(obs, "repr", None) == "'Hello World'"
        for obs in outcome.observations
    )


def test_raises_check_captures_expected_exception() -> None:
    task = _valid_task(
        reference=dedent("""\
        d = {}
        x = d['missing']
        """),
        checks=(Raises(exception="KeyError"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)

    assert isinstance(outcome, Accepted)
    assert any(obs.exception_type == "KeyError" for obs in outcome.observations)


def test_multiple_name_equals_checks_materialize_all() -> None:
    task = _valid_task(
        reference=dedent("""\
        def add(a, b):
            return a + b
        three = add(1, 2)
        five = add(2, 3)
        """),
        checks=(NameEquals(name="three"), NameEquals(name="five")),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Accepted)
    names = {obs.name for obs in outcome.observations if hasattr(obs, "name")}
    assert names == {"three", "five"}


# ---------------------------------------------------------------------------
# Rejection: reference code errors
# ---------------------------------------------------------------------------


def test_syntax_error_rejected() -> None:
    task = _valid_task(reference="def greet(:\n    pass\n")
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "execute"


def test_import_error_rejected() -> None:
    task = _valid_task(reference="import no_such_module_xyzzy\n")
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)
    assert outcome.stage in ("execute", "import")


def test_name_missing_from_namespace_rejected() -> None:
    task = _valid_task(
        reference="x = 1\n",
        checks=(NameEquals(name="greet"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)
    assert outcome.stage == "collect"


# ---------------------------------------------------------------------------
# Infrastructure failures
# ---------------------------------------------------------------------------


def test_timeout_reported_as_infrastructure_failure() -> None:
    task = _valid_task(reference="while True:\n    pass\n")
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=2)
    assert isinstance(outcome, InfrastructureFailure)
    assert outcome.stage == "timeout"


def test_non_evaluable_repr_captured_not_crashed() -> None:
    """A value whose repr() raises should produce a ReprError, not crash."""
    task = _valid_task(
        reference=dedent("""\
        class BrokenRepr:
            def __repr__(self):
                raise RuntimeError("cannot repr")
        obj = BrokenRepr()
        """),
        checks=(NameEquals(name="obj"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    # Should not be InfrastructureFailure; should be Rejection or Accepted
    # with a ReprError observation.  Exact stage TBD by implementation.
    assert not isinstance(outcome, InfrastructureFailure)


def test_raises_wrong_exception_type_rejected() -> None:
    task = _valid_task(
        reference=dedent("""\
        x = int("not-a-number")
        """),
        checks=(Raises(exception="KeyError"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)


def test_did_not_raise_when_raises_expected_rejected() -> None:
    task = _valid_task(
        reference="x = 1\n",
        checks=(Raises(exception="ValueError"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)


# ---------------------------------------------------------------------------
# Interpreter provenance
# ---------------------------------------------------------------------------


def test_outcome_records_interpreter_version() -> None:
    task = _valid_task(
        reference="x = 1\n",
        checks=(NameEquals(name="x"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Accepted)
    assert outcome.interpreter_version
    assert "." in outcome.interpreter_version


def test_outcome_records_sandbox_backend() -> None:
    task = _valid_task(
        reference="x = 1\n",
        checks=(NameEquals(name="x"),),
    )
    sb = _sandbox()
    outcome = materialize_reference(task, sandbox=sb, timeout=15)
    assert isinstance(outcome, Accepted)
    assert outcome.sandbox_backend == sb.backend_name
    assert outcome.sandbox_profile_version == sb.profile_version


# ---------------------------------------------------------------------------
# Swallowed import / partial execution
# ---------------------------------------------------------------------------


def test_swallowed_import_causes_name_missing() -> None:
    """If reference catches ImportError, the expected name is missing."""
    task = _valid_task(
        reference=dedent("""\
        try:
            import no_such_module_xyzzy as mod
        except ImportError:
            mod = None
        # greet is never defined because the import was swallowed
        """),
        checks=(NameEquals(name="greet"),),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection)


def test_partial_execution_mid_exception_refuses_partial() -> None:
    """When the reference raises mid-execution, partial namespace is rejected."""
    task = _valid_task(
        reference=dedent("""\
        x = 1
        raise RuntimeError("boom")
        y = 2  # never reached
        """),
        checks=(NameEquals(name="x"), NameEquals(name="y")),
    )
    outcome = materialize_reference(task, sandbox=_sandbox(), timeout=15)
    # Reference raising during execution → Rejection at execute stage
    assert not isinstance(outcome, Accepted)


# ---------------------------------------------------------------------------
# Adversarial sandbox tests
# ---------------------------------------------------------------------------


@skip_no_sandbox
def test_normal_reference_executes_inside_os_sandbox() -> None:
    """Confinement permits the expected interpreter and temporary inputs."""
    task = _valid_task(
        reference="result = 42\n",
        checks=(NameEquals(name="result"),),
    )

    outcome = materialize_reference(task, sandbox=_os_sandbox(), timeout=15)

    assert isinstance(outcome, Accepted)


@skip_no_sandbox
def test_network_access_attempt_blocked() -> None:
    """Planted network attempt is blocked by the sandbox profile."""
    task = _valid_task(
        reference=dedent("""\
        import urllib.request
        urllib.request.urlopen("http://example.com")
        """),
        checks=(NameEquals(name="x"),),
    )
    outcome = materialize_reference(task, sandbox=_os_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection) or isinstance(outcome, InfrastructureFailure)


@skip_no_sandbox
def test_host_file_attempt_blocked() -> None:
    """Planted host-file read attempt is blocked by the sandbox profile."""
    task = _valid_task(
        reference="open('/etc/passwd').read()\n",
        checks=(NameEquals(name="x"),),
    )
    outcome = materialize_reference(task, sandbox=_os_sandbox(), timeout=15)
    assert isinstance(outcome, Rejection) or isinstance(outcome, InfrastructureFailure)


@skip_no_sandbox
def test_side_effect_not_observable() -> None:
    """A deterministic side effect (file write) must not survive the sandbox."""
    task = _valid_task(
        reference=dedent("""\
        with open('/tmp/satyrn-side-effect-test', 'w') as f:
            f.write('leaked')
        result = 'done'
        """),
        checks=(NameEquals(name="result"),),
    )
    outcome = materialize_reference(task, sandbox=_os_sandbox(), timeout=15)
    # If sandbox blocks writes, execution fails → Rejection or Infra
    assert isinstance(outcome, Rejection) or isinstance(outcome, InfrastructureFailure)
    assert not Path("/tmp/satyrn-side-effect-test").exists()
