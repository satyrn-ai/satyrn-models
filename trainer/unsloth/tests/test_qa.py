"""The MLflow finalizer patch in eval/qa.py."""

from mlflow.tracing import provider

import satyrn.trainer.unsloth.eval.qa  # noqa: F401


def test_isolated_id_generator_finalizer_is_patched() -> None:
    """Fails if MLflow renames the class, which makes the patch in eval/qa.py skip silently."""
    assert provider._IsolatedRandomIdGenerator.__del__(object()) is None
